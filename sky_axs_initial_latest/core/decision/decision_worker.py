#!/usr/bin/env python3
import os
from redis import Redis
from rq import Worker, Queue

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB", "0"))

QUEUE_NAME = os.getenv("DECISION_QUEUE", "decision")

def main():
    conn = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    q = Queue(QUEUE_NAME, connection=conn)
    Worker([q]).work(with_scheduler=True)

if __name__ == "__main__":
    main()
