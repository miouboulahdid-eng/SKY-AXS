#!/usr/bin/env python3
import os, time, json, datetime
import requests
import redis
from dateutil import tz

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
API_URL    = os.getenv("API_URL",  "http://api:8000/health")
INTERVAL   = int(os.getenv("INTERVAL", "10"))  # seconds
STREAM_KEY = os.getenv("STREAM_KEY", "metrics")

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def utc_ts():
    return int(time.time())

def safe_get(url, timeout=3):
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.status_code, resp.elapsed.total_seconds()*1000.0
    except Exception:
        return 599, None

def redis_info():
    try:
        info = r.info()
        return {
            "used_memory": info.get("used_memory", 0),
            "connected_clients": info.get("connected_clients", 0),
            "blocked_clients": info.get("blocked_clients", 0),
            "ops": info.get("instantaneous_ops_per_sec", 0)
        }
    except Exception:
        return {}

def rq_stats():
    try:
        # عدّ عناصر طابور RQ الافتراضي
        size = r.llen("rq:queue:default")
        return {"rq_queue_default_len": size or 0}
    except Exception:
        return {"rq_queue_default_len": 0}

def main():
    print(f"[collector] start interval={INTERVAL}s stream={STREAM_KEY}", flush=True)
    while True:
        ts = utc_ts()
        status, latency_ms = safe_get(API_URL)
        payload = {
            "ts": ts,
            "service": "api",
            "api_status": status,
            "api_latency_ms": latency_ms if latency_ms is not None else -1,
        }
        payload.update(redis_info())
        payload.update(rq_stats())
        r.xadd(STREAM_KEY, payload, maxlen=5000, approximate=True)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
