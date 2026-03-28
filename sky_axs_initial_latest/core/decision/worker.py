import os
import redis
from rq import Queue, Worker

# إعداد الاتصال بـ Redis
redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_conn = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

def start_decision_worker():
    """تشغيل Worker لطابور القرارات (decision)."""
    print(f"[Decision Worker] 🚀 بدأ التشغيل وربط Redis في {redis_host}")
    queue_name = os.getenv("RQ_QUEUE", "decision")
    worker = Worker([queue_name], connection=redis_conn)
    worker.work(with_scheduler=True)

if __name__ == "__main__":
    start_decision_worker()
