import os
import time
import logging
import socket
import redis
from rq import Worker, Queue
import uuid, json, datetime, requests

logging.basicConfig(level=logging.INFO, format='[Mobile Worker] %(message)s')

def resolve_redis_host(host):
    """تحقق من إمكانية ترجمة اسم Redis"""
    try:
        socket.gethostbyname(host)
        return True
    except socket.error:
        return False

def get_redis_connection():
    """يحاول الاتصال بـ Redis حتى ينجح"""
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))

    for attempt in range(1, 6):  # نحاول 5 مرات
        if not resolve_redis_host(redis_host):
            logging.warning(f"⚠️ DNS فشل في إيجاد {redis_host}. المحاولة {attempt}/5 ...")
            time.sleep(3)
            continue

        try:
            conn = redis.Redis(host=redis_host, port=redis_port)
            conn.ping()
            logging.info(f"🚀 تم الاتصال بـ Redis في {redis_host}:{redis_port}")
            return conn
        except redis.ConnectionError as e:
            logging.warning(f"❌ فشل الاتصال بـ Redis ({e}). المحاولة {attempt}/5 ...")
            time.sleep(5)

    raise ConnectionError("❌ لم يتم الاتصال بـ Redis بعد 5 محاولات.")

def start_mobile_worker():
    redis_conn = get_redis_connection()
    queue_name = os.getenv("MOBILE_QUEUE", "mobile")
    queue = Queue(queue_name, connection=redis_conn)
    worker = Worker([queue])
    logging.info(f"💼 Mobile Worker يعمل على الطابور: {queue_name}")
    worker.work(with_scheduler=True)

# ==========================
# 📱 Mobile Scan Function
# ==========================

MOBILE_DECISIONS_DIR = os.path.join("/app/data", "mobile_decisions")
os.makedirs(MOBILE_DECISIONS_DIR, exist_ok=True)

def _write_mobile_result(job_id: str, result: dict):
    path = os.path.join(MOBILE_DECISIONS_DIR, f"{job_id}.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logging.info(f"[Mobile Worker] 📝 Result written to {path}")
    return path

def run_mobile_scan(target: str, extra: str = "", job_id: str = None):
    """دالة تنفيذ الفحص الأساسي لتطبيق الهاتف"""
    job_id = job_id or uuid.uuid4().hex
    job_id = str(job_id).strip()
    logging.info(f"[Mobile Worker] 📌 Using job_id={job_id}")

    start_time = datetime.datetime.utcnow().isoformat()

    result = {
        "job_id": job_id,
        "target": target,
        "extra": extra,
        "status": "running",
        "started": start_time,
        "output": None,
        "notes": [],
    }

    _write_mobile_result(job_id, result)

    try:
        logging.info(f"[Mobile Worker] 🔍 Starting mobile scan for {target}")
        resp = requests.get(target, timeout=10)
        result["status"] = "ok"
        result["output"] = {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body_snippet": resp.text[:500],
        }
        logging.info(f"[Mobile Worker] ✅ Scan completed for {target}")
    except Exception as e:
        result["status"] = "failed"
        result["notes"].append(str(e))

    result["ended"] = datetime.datetime.utcnow().isoformat()
    _write_mobile_result(job_id, result)
    return job_id

if __name__ == "__main__":
    start_mobile_worker()
