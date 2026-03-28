#!/usr/bin/env python3
import os
import re
import json
from typing import Optional, Literal
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from redis import Redis
from rq import Queue
from rq.job import Job

APP_TITLE = "AXS Decision Engine"
APP_VERSION = "1.0"

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB", "0"))

# نستخدم PYTHONPATH=/app بحيث worker يقدر يحل import لمسار core.*
DEFAULT_QUEUE = os.getenv("DEFAULT_QUEUE", "default")
DECISION_QUEUE = os.getenv("DECISION_QUEUE", "decision")
SANDBOX_FUNC = "core.worker.sandbox_task_run_in_sandbox"

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

def get_redis() -> Redis:
    return Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

def get_queue(name: str) -> Queue:
    return Queue(name, connection=get_redis())

class DecisionRequest(BaseModel):
    target: str = Field(..., description="الهدف")
    task_type: Optional[Literal["auto","web_scan","network_scan","train","analyze"]] = "auto"
    priority: Optional[int] = 0
    extra: Optional[str] = ""

class DecisionResponse(BaseModel):
    status: str
    decision: dict
    job_id: Optional[str] = None
    queue: Optional[str] = None
    timestamp: str

def infer_target_type(target: str) -> str:
    # بسيط: URL -> WEB، IP -> NET، غيرها TEXT
    if target.startswith("http://") or target.startswith("https://"):
        return "WEB"
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", target):
        return "NET"
    return "TEXT"

@app.get("/health")
def health():
    try:
        get_redis().ping()
        return {"status": "ok", "redis": True, "queues": [DEFAULT_QUEUE, DECISION_QUEUE]}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}

@app.post("/decide", response_model=DecisionResponse)
def decide(req: DecisionRequest):
    ttype = req.task_type or "auto"
    inferred = infer_target_type(req.target)

    # اختيار الإستراتيجية
    strategy = []
    if ttype == "auto":
        if inferred == "WEB":
            strategy = ["dirb", "xss", "sqlmap"]
        elif inferred == "NET":
            strategy = ["nmap", "banner-grab"]
        else:
            strategy = ["text-analyze"]
    elif ttype == "web_scan":
        strategy = ["dirb", "xss", "sqlmap"]
    elif ttype == "network_scan":
        strategy = ["nmap", "banner-grab"]
    elif ttype in ("train","analyze"):
        strategy = [ttype]
    else:
        strategy = ["unknown"]

    decision = {
        "target": req.target,
        "inferred_type": inferred,
        "task_type": ttype,
        "priority": req.priority,
        "strategy": strategy,
        "extra": req.extra or "",
    }

    # توزيع إلى الطابور المناسب
    queue_name = DEFAULT_QUEUE
    func_path = SANDBOX_FUNC
    job_kwargs = {
        "result_ttl": 24 * 3600,   # احتفاظ 24 ساعة
        "ttl": 3600,               # يبقى بالصف ساعة إن لم يُلتقط
        "job_timeout": 600,        # 10 دقائق للتنفيذ
        "failure_ttl": 24 * 3600,  # فشل يُحتفظ به 24 ساعة
        "description": f"decision:{json.dumps(decision, ensure_ascii=False)}"
    }

    try:
        q = get_queue(queue_name)
        # sandbox_task_run_in_sandbox(target, extra)
        j = q.enqueue(func_path, req.target, req.extra or "", **job_kwargs)
        return DecisionResponse(
            status="queued",
            decision=decision,
            job_id=j.id,
            queue=queue_name,
            timestamp=datetime.utcnow().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"enqueue failed: {e}")

@app.get("/status/{job_id}")
def status(job_id: str):
    try:
        job = Job.fetch(job_id, connection=get_redis())
    except Exception:
        raise HTTPException(status_code=404, detail=f"No such job: {job_id}")

    resp = {
        "id": job.id,
        "status": job.get_status(),
        "enqueued_at": str(job.enqueued_at) if job.enqueued_at else None,
        "started_at": str(job.started_at) if job.started_at else None,
        "ended_at": str(job.ended_at) if job.ended_at else None,
        "meta": job.meta or {},
    }
    if job.is_finished:
        try:
            resp["result"] = job.result
        except Exception:
            resp["result"] = None
    elif job.is_failed:
        resp["exc_info"] = job.exc_info
    return resp
