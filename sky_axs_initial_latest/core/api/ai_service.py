from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
import os
from datetime import datetime
from redis import Redis
from rq import Queue

# استيراد المحرك الذكي
from core.ai_engine.axs_ai_engine import AxsAIEngine

# تعريف التطبيق
app = FastAPI(title="AXS AI Smart API", version="2.0")

# إعداد Redis Queue
def _get_queue():
    redis_conn = Redis(host="redis", port=6379, db=0)
    return Queue("default", connection=redis_conn)

# نموذج الإدخال للتحليل
class AnalyzeRequest(BaseModel):
    input_text: str

# نقطة تحليل الذكاء الاصطناعي
@app.post("/analyze")
def analyze_text(req: AnalyzeRequest):
    try:
        engine = AxsAIEngine()
        result = engine.analyze_target(req.input_text)
        return {
            "input": req.input_text,
            "ai_analysis": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logging.error(f"❌ تحليل فشل: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# نقطة اختبار Sandbox
class SandboxRequest(BaseModel):
    target: str
    extra: str = ""

@app.post("/sandbox/run")
def sandbox_run(req: SandboxRequest):
    q = _get_queue()
    job = q.enqueue(
        "core.worker.sandbox_task_run_in_sandbox",
        req.target,
        req.extra,
        job_timeout=600,
        result_ttl=-1
    )
    logging.info(f"🚀 تم إرسال مهمة Sandbox: {req.target}")
    return {"status": "queued", "job_id": job.id, "queue": job.origin}

@app.get("/sandbox/result/{job_id}")
def sandbox_result(job_id: str):
    q = _get_queue()
    job = q.fetch_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"No such job: {job_id}")
    return {
        "status": job.get_status(),
        "enqueued_at": str(job.enqueued_at),
        "ended_at": str(job.ended_at),
        "result": job.result
    }

@app.get("/")
def root():
    return {"status": "ok", "message": "AXS AI Smart Analyzer Active"}
