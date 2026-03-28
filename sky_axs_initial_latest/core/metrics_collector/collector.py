import os
import time
import logging
import redis
import requests

logging.basicConfig(level=logging.INFO)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
API_URL = os.getenv("API_URL", "http://api:8000/health")
INTERVAL = int(os.getenv("INTERVAL", "10"))
STREAM_KEY = os.getenv("STREAM_KEY", "metrics")

def main():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    while True:
        try:
            resp = requests.get(API_URL, timeout=5)
            data = {
                "status": resp.json().get("status", "unknown"),
                "timestamp": time.time(),
                "cpu": 0.0,
                "mem": 0.0
            }
            r.xadd(STREAM_KEY, data, maxlen=1000)
            logging.info("Metrics sent")
        except Exception as e:
            logging.error(f"Error: {e}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()