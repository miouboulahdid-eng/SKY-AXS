import sys, os, json, time
sys.path.append("/app")
sys.path.append("/app/core")
from fastapi import FastAPI, Body, Request
from pydantic import BaseModel
from rq import Queue
from redis import Redis

# === إصلاح المسار ليتمكن من الوصول إلى core ===
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.ai_engine.behavior_engine import BehaviorEngine
from core.ai_engine.axs_ai_engine import AxsAIEngine
from worker.sandbox_task import sandbox_task_run_in_sandbox

# === إعداد FastAPI ===
app = FastAPI(title="AXS AI Orchestrator", version="2.0")

ai_engine = AxsAIEngine()
behavior_engine = BehaviorEngine()

class PredictRequest(BaseModel):
    input_text: str

@app.get("/health")
async def health():
    return {"status": "healthy", "ai_engine": "AxsAIEngine", "behavior_engine": "BehaviorEngine"}

# === إعداد RQ/Redis ===
try:
    redis_conn = Redis(host="redis", port=6379, db=0)
    q = Queue("default", connection=redis_conn)
    HAVE_RQ = True
except Exception:
    HAVE_RQ = False

@app.post("/sandbox/run")
def sandbox_run(payload: dict = Body(...)):
    """
    لتشغيل مهمة sandbox معزولة
    """
    if not HAVE_RQ:
        return {"status": "error", "detail": "RQ/Redis not available"}

    target = (payload or {}).get("target", "").strip()
    extra = (payload or {}).get("extra", "").strip()
    if not target:
        return {"status": "error", "detail": "target required"}

    job = q.enqueue(
        "core.worker.sandbox_task_run_in_sandbox",
        target,
        extra,
        job_timeout=600,
        result_ttl=-1   # ✅ الاحتفاظ الدائم بالنتائج
    )
    return {"status": "queued", "job_id": job.id, "queue": q.name}

@app.get("/sandbox/result/{job_id}")
def sandbox_result(job_id: str):
    from rq.job import Job
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        if job.is_finished:
            return {"status": "finished", "result": job.result}
        elif job.is_failed:
            return {"status": "failed", "error": str(job.exc_info)}
        else:
            return {"status": job.get_status()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
