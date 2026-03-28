from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import os, json
from redis import Redis
from rq import Queue, Job

from core.decision.model import decide, build_features

app = FastAPI(title="AXS Decision Engine", version="1.0")

# إعدادات
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
RQ_QUEUE_DEFAULT = os.getenv("RQ_QUEUE_DEFAULT", "default")
DECISIONS_DIR = "/app/data/decisions"
os.makedirs(DECISIONS_DIR, exist_ok=True)

def get_redis():
    return Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def get_queue(name=RQ_QUEUE_DEFAULT):
    return Queue(name, connection=get_redis())

class DecideRequest(BaseModel):
    target: str
    task_type: str = "auto"
    extra: str = ""

@app.get("/health")
def health():
    try:
        r = get_redis()
        ok = r.ping()
        return {"status": "ok" if ok else "degraded",
                "redis": ok,
                "queues": [RQ_QUEUE_DEFAULT, "decision"]}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}

def _infer_strategy(target_type: str) -> list[str]:
    if target_type == "WEB":
        return ["dirb", "xss", "sqlmap"]
    if target_type == "API":
        return ["jwt-audit", "postman-tests"]
    if target_type == "MOBILE":
        return ["apktool", "frida", "mobSF"]
    if target_type == "NETWORK":
        return ["nmap", "portscan"]
    return ["info-gather", "passive-scan"]

@app.post("/decide")
def decide_and_enqueue(req: DecideRequest):
    t = req.target.strip()
    if not t:
        raise HTTPException(status_code=400, detail="target is required")

    # بناء ميزات أولية — مكان ممتاز للتوسع فيما بعد
    feats = build_features(target=t, ml_score=0.5, recent_files=0,
                           avg_entropy=0.0, has_history=0)
    verdict = decide(feats)
    inferred_type = feats.get("target_type", "GENERIC")
    strategy = _infer_strategy(inferred_type)

    decision = {
        "target": t,
        "inferred_type": inferred_type,
        "task_type": req.task_type,
        "priority": verdict["priority"],
        "queue": verdict["queue"],     # حالياً default
        "strategy": strategy,
        "extra": req.extra,
        "confidence": verdict["confidence"],
        "timestamp": datetime.utcnow().isoformat()
    }

    # إرسال التنفيذ للـ worker الحالي (sandbox stub) عبر RQ default
    q = get_queue(name=verdict["queue"])
    try:
        job = q.enqueue(
            "core.worker.sandbox_task_run_in_sandbox",
            t,
            req.extra,
            job_timeout=600,
            result_ttl=-1,  # لا ينتهي تلقائياً
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"enqueue failed: {e}")

    # حفظ القرار على القرص
    out_path = os.path.join(DECISIONS_DIR, f"{job.id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"decision": decision, "job_id": job.id}, f, ensure_ascii=False, indent=2)

    return {
        "status": "queued",
        "decision": {k: decision[k] for k in ["target","inferred_type","task_type","priority","strategy","extra"]},
        "job_id": job.id,
        "queue": verdict["queue"],
        "timestamp": decision["timestamp"]
    }

@app.get("/status/{job_id}")
def job_status(job_id: str):
    try:
        r = get_redis()
        job = Job.fetch(job_id, connection=r)
        return {
            "id": job.id,
            "status": job.get_status(),
            "enqueued_at": str(job.enqueued_at),
            "started_at": str(job.started_at) if job.started_at else None,
            "ended_at": str(job.ended_at) if job.ended_at else None,
            "meta": job.meta,
            "result": job.result,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
