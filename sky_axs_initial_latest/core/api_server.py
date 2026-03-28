#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import sys
from datetime import datetime

try:
    from redis import Redis
    from rq import Queue
except Exception as e:
    print("Missing redis/rq:", e, file=sys.stderr)
    raise

# حاول استخدام دالة العامل إن كانت متاحة
HAVE_TASK = False
try:
    from core.worker.tasks import run_sky
    HAVE_TASK = True
except Exception:
    HAVE_TASK = False

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
QUEUE_NAME = os.environ.get("RQ_QUEUE", "default")

def get_redis() -> Redis:
    return Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_connect_timeout=5)

app = FastAPI(title="Sky AXS API", version="0.1")

class EnqueueRequest(BaseModel):
    target: str
    extra: Optional[str] = None

@app.get("/health")
def health():
    try:
        r = get_redis()
        pong = r.ping()
        return {"status": "ok", "redis": pong, "queue": QUEUE_NAME}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"redis error: {e}")

@app.get("/jobs")
def list_jobs():
    try:
        r = get_redis()
        q = Queue(QUEUE_NAME, connection=r)
        jobs = []
        for j in q.jobs:
            jobs.append({
                "id": j.id,
                "status": j.get_status(),
                "enqueued_at": j.enqueued_at.isoformat() if j.enqueued_at else None,
                "func_name": getattr(j, "func_name", None),
                "args": getattr(j, "args", None)
            })
        return {"count": len(jobs), "jobs": jobs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/enqueue")
def enqueue(req: EnqueueRequest):
    if not req.target:
        raise HTTPException(status_code=400, detail="target is required")

    try:
        r = get_redis()
        q = Queue(QUEUE_NAME, connection=r)

        if HAVE_TASK:
            job = q.enqueue(run_sky, req.target, req.extra or "", job_timeout=3600)
        else:
            job = q.enqueue("core.worker.tasks.run_sky", req.target, req.extra or "", job_timeout=3600)

        return {
            "job_id": job.id,
            "queued_at": datetime.utcnow().isoformat() + "Z",
            "target": req.target,
            "extra": req.extra or ""
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
