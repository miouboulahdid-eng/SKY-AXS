from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Any, Dict, Optional
import logging
import os
from datetime import datetime
from redis import Redis
from rq import Queue

from core.ai_engine.axs_ai_engine import AxsAIEngine
from core.ai_engine.behavior_engine import BehaviorEngine

app = FastAPI(title="AXS AI API", version="2.0")

ai_basic = AxsAIEngine()
behavior = BehaviorEngine()

# ========== Redis / RQ helpers ==========
def _get_redis():
    return Redis(host=os.getenv("REDIS_HOST", "redis"), port=int(os.getenv("REDIS_PORT", "6379")), db=0)

def _get_queue():
    return Queue("default", connection=_get_redis())

# ========== Models ==========
class TargetIn(BaseModel):
    target: str

class EventsIn(BaseModel):
    events: List[Any]  # list[str|dict]

class AnalyzeRequest(BaseModel):
    input_text: str

class SandboxRequest(BaseModel):
    target: str
    extra: str = ""

class EndpointAnalysisRequest(BaseModel):
    method: str = "GET"
    url: str
    params: Optional[Dict] = {}
    headers: Optional[Dict] = {}
    cookies: Optional[Dict] = {}
    response_body: Optional[str] = ""

# ========== Existing Endpoints ==========
@app.get("/health")
def health():
    return {"status": "healthy", "engine": "AxsAIEngine+BehavioralEngine"}

@app.post("/predict")
def predict(payload: TargetIn):
    """نموذج الذكاء الأساسي (سابقاً)."""
    result = ai_basic.analyze_target(payload.target)
    return {"target": payload.target, "analysis": result, "status": "ok"}

@app.post("/behavior/ingest")
def behavior_ingest(payload: EventsIn):
    info = behavior.ingest(payload.events)
    return {"status": "ok", **info}

@app.post("/behavior/score")
def behavior_score(payload: EventsIn):
    out = behavior.score(payload.events)
    return {"status": "ok", **out}

# ========== New Endpoints ==========
@app.post("/analyze")
def analyze_text(req: AnalyzeRequest):
    try:
        result = ai_basic.analyze_target(req.input_text)
        return {
            "input": req.input_text,
            "ai_analysis": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logging.error(f"Analyze failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sandbox/run")
def sandbox_run(req: SandboxRequest):
    q = _get_queue()
    job = q.enqueue(
        "core.worker.sandbox_task.sandbox_task_run_in_sandbox",
        req.target,
        req.extra,
        job_timeout=600,
        result_ttl=-1
    )
    logging.info(f"Sandbox task queued: {req.target}")
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

@app.post("/analyze/llm")
def analyze_with_llm(req: EndpointAnalysisRequest):
    """تحليل endpoint باستخدام LLM لاكتشاف IDOR/BAC"""
    from core.ai_models.llm_analyzer import analyze_endpoint_with_llm
    
    data = {
        "method": req.method,
        "url": req.url,
        "params": req.params,
        "headers": req.headers,
        "cookies": req.cookies,
        "response_body": req.response_body
    }
    result = analyze_endpoint_with_llm(data)
    return result

@app.get("/")
def root():
    return {"status": "ok", "message": "AXS AI Smart Analyzer Active"}