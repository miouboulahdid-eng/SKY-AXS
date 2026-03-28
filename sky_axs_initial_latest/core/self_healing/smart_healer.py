#!/usr/bin/env python3
"""
Smart Healer (Proactive)
- يقرأ قياسات الأداء من Redis Stream: metrics:system  (fields: cpu, mem, qlen, latency)
- يبني نموذج بسيط للتنبؤ بالمشاكل (EWMA + Z-score) بدون أي مكتبات ثقيلة
- عند ارتفاع احتمال الفشل => ينفذ إجراء استباقي:
  * يكتب حدث في stream: healer:events
  * يدفع أمر في قائمة Redis: healer:actions  (مثلاً "restart:worker" أو "safe-mode:on")
- لا يعتمد على Docker SDK (لتفادي http+docker issue)
"""

import os, sys, time, json, math
from datetime import datetime
from collections import deque

try:
    import redis
except Exception as e:
    print("[healer] missing redis package:", e, file=sys.stderr)
    sys.exit(2)

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
STREAM_IN  = os.environ.get("METRICS_STREAM", "metrics:system")
STREAM_OUT = os.environ.get("HEALER_EVENTS", "healer:events")
ACTIONS_Q  = os.environ.get("HEALER_ACTIONS", "healer:actions")

# عتبات وضبط
CHECK_INTERVAL = float(os.environ.get("HEALER_CHECK_INTERVAL", "5"))   # ثواني
RISK_THRESHOLD = float(os.environ.get("HEALER_RISK_THRESHOLD", "0.85"))
WINDOW         = int(os.environ.get("HEALER_WINDOW", "30"))            # عدد نقاط تاريخية صغيرة

# مؤشرات نحسب لها المخاطر
METRIC_FIELDS = ["cpu", "mem", "qlen", "latency"]  # كلها اختيارية؛ إذا غاب واحد نتجاهله

def now_iso():
    return datetime.utcnow().isoformat() + "Z"

class EWMAModel:
    """ نموذج خفيف: متوسط متحرك أسي + انحراف معياري تقريبي => z-score => خطر من 0..1 """
    def __init__(self, alpha=0.2):
        self.alpha = alpha
        self.mean = None
        self.var = None
        self.n = 0

    def update(self, x):
        if x is None:
            return
        self.n += 1
        if self.mean is None:
            self.mean = x
            self.var = 0.0
        else:
            prev_mean = self.mean
            self.mean = self.alpha * x + (1 - self.alpha) * self.mean
            self.var = self.alpha * (x - prev_mean) ** 2 + (1 - self.alpha) * self.var

    def zscore(self, x):
        if x is None or self.mean is None or self.var is None or self.var == 0:
            return 0.0
        std = math.sqrt(self.var)
        return abs((x - self.mean) / (std if std > 1e-6 else 1e-6))

    def risk(self, x):
        z = self.zscore(x)
        return 1 - math.exp(-min(z, 6.0))

class RiskAggregator:
    """ يدمج مخاطر عدة مؤشرات إلى قيمة واحدة """
    def __init__(self):
        self.models = {k: EWMAModel(alpha=0.2) for k in METRIC_FIELDS}

    def update_and_score(self, metrics: dict):
        risks = []
        for k, model in self.models.items():
            val = metrics.get(k)
            try:
                if val is not None:
                    val = float(val)
            except:
                val = None
            model.update(val)
            risks.append(model.risk(val))
        if not risks:
            return 0.0
        avg = sum(risks) / len(risks)
        mx  = max(risks)
        return round((0.6 * mx + 0.4 * avg), 3)

def connect_redis():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_connect_timeout=3)
    r.ping()
    return r

def read_latest_metrics(r, last_id="$"):
    try:
        resp = r.xread({STREAM_IN: last_id}, count=1, block=1000)
        if not resp:
            return last_id, None
        stream, entries = resp[0]
        msg_id, fields = entries[0]
        data = {}
        for f in METRIC_FIELDS:
            if f in fields:
                data[f] = fields[f]
        if "cpu" not in data and "cpu_percent" in fields:
            data["cpu"] = fields["cpu_percent"]
        if "mem" not in data and "mem_percent" in fields:
            data["mem"] = fields["mem_percent"]
        if "qlen" not in data and "queue_len" in fields:
            data["qlen"] = fields["queue_len"]
        if "latency" not in data and "p95" in fields:
            data["latency"] = fields["p95"]
        return msg_id, data
    except redis.RedisError as e:
        print("[healer] redis read error:", e, file=sys.stderr)
        return last_id, None

def emit_event(r, level, msg, extra=None):
    payload = {"ts": now_iso(), "level": level, "msg": msg}
    if extra:
        payload.update(extra)
    try:
        r.xadd(STREAM_OUT, payload, maxlen=1000, approximate=True)
    except Exception as e:
        print("[healer] xadd error:", e, file=sys.stderr)

def enqueue_action(r, action, reason=None):
    item = {"ts": now_iso(), "action": action}
    if reason:
        item["reason"] = reason
    try:
        r.rpush(ACTIONS_Q, json.dumps(item))
    except Exception as e:
        print("[healer] rpush action error:", e, file=sys.stderr)

def main():
    try:
        r = connect_redis()
    except Exception as e:
        print("[healer] cannot connect to redis:", e, file=sys.stderr)
        sys.exit(1)

    agg = RiskAggregator()
    last_id = "$"
    idle = 0

    emit_event(r, "info", "smart_healer started", {"stream": STREAM_IN})

    while True:
        last_id, metrics = read_latest_metrics(r, last_id)
        if metrics:
            idle = 0
            risk = agg.update_and_score(metrics)
            emit_event(r, "debug", "metrics_read", {"metrics": json.dumps(metrics), "risk": risk})

            if risk >= RISK_THRESHOLD:
                emit_event(r, "warn", "high_risk_detected", {"risk": risk})
                qlen = float(metrics.get("qlen", 0) or 0)
                lat  = float(metrics.get("latency", 0) or 0)
                if qlen >= 50 or lat >= 2.0:
                    enqueue_action(r, "safe-mode:on", reason=f"qlen={qlen},lat={lat},risk={risk}")
                    enqueue_action(r, "restart:worker", reason="proactive_heal")
                else:
                    enqueue_action(r, "restart:api", reason=f"risk={risk}")
        else:
            idle += 1

        if idle >= int(60 / max(CHECK_INTERVAL, 1)):
            emit_event(r, "info", "no_metrics_recently")
            idle = 0

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
