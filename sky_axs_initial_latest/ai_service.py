from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Any, Dict, Optional
import logging
import os
import json
from datetime import datetime
from redis import Redis
from rq import Queue

from core.ai_engine.axs_ai_engine import AxsAIEngine
from core.ai_engine.behavior_engine import BehaviorEngine
from core.db.database import get_connection, init_db
from core.collectors.endpoint_collector import collect_endpoints
from core.ai_engine.idor_detector import detect_idor
from core.auth.session_manager_redis import RedisSessionManager
app = FastAPI(title="AXS AI API", version="2.0")

ai_basic = AxsAIEngine()
behavior = BehaviorEngine()

# تهيئة قاعدة البيانات عند بدء التشغيل
init_db()

# ========== Redis / RQ helpers ==========
def _get_redis():
    return Redis(host=os.getenv("REDIS_HOST", "redis"), port=int(os.getenv("REDIS_PORT", "6379")), db=0)

def _get_queue():
    return Queue("default", connection=_get_redis())

# ========== Models ==========
class TargetIn(BaseModel):
    target: str

class EventsIn(BaseModel):
    events: List[Any]

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

class TargetUrl(BaseModel):
    target: str
class ManualEndpoint(BaseModel):
    target: str
    method: str = "GET"
    url: str
    params: Optional[Dict] = {}
    headers: Optional[Dict] = {}
    cookies: Optional[Dict] = {}
    response_body: Optional[str] = ""
    status_code: int = 0
    content_type: str = ""
    sensitive: bool = False
class LoginRequest(BaseModel):
    target: str
    username: str
    password: str    
# ========== Endpoint Collection & Listing ==========
redis_client = _get_redis()
session_manager = RedisSessionManager(redis_client)
@app.post("/collect/endpoints")
def collect_endpoints_endpoint(req: TargetUrl):
    """جمع endpoints لهدف معين (استطلاع سلبي) وتخزينها في قاعدة البيانات"""
    try:
        endpoints = collect_endpoints(req.target)
        with get_connection() as conn:
            for ep in endpoints:
                conn.execute(
                    """INSERT INTO endpoints 
                       (target, method, url, params, headers, cookies, response_body, status_code, content_type, sensitive)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (req.target, ep.get('method','GET'), ep.get('url'),
                     json.dumps(ep.get('params', {})),
                     json.dumps(ep.get('headers', {})),
                     json.dumps(ep.get('cookies', {})),
                     ep.get('response_body', ''),
                     ep.get('status_code', 0),
                     ep.get('content_type', ''),
                     1 if ep.get('sensitive', False) else 0)
                )
            conn.commit()
        return {"status": "ok", "collected": len(endpoints)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/endpoints/manual")
def add_manual_endpoint(ep: ManualEndpoint):
    """إضافة endpoint يدوياً إلى قاعدة البيانات"""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO endpoints 
               (target, method, url, params, headers, cookies, response_body, status_code, content_type, sensitive)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (ep.target, ep.method, ep.url,
             json.dumps(ep.params), json.dumps(ep.headers),
             json.dumps(ep.cookies), ep.response_body,
             ep.status_code, ep.content_type, 1 if ep.sensitive else 0)
        )
        conn.commit()
    return {"status": "ok", "endpoint": ep.dict()}        

@app.get("/endpoints")
def list_endpoints(target: str = None):
    """عرض endpoints المخزنة، مع إمكانية التصفية حسب الهدف"""
    with get_connection() as conn:
        if target:
            rows = conn.execute("SELECT * FROM endpoints WHERE target=?", (target,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM endpoints").fetchall()
        return [dict(row) for row in rows]

# ========== IDOR Detection ==========
@app.post("/detect/idor")
def run_idor_detection(req: LoginRequest):
    try:
        results = detect_idor(req.target, session_manager, req.username, req.password)
        return {"status": "ok", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== Existing Endpoints ==========
@app.get("/health")
def health():
    return {"status": "healthy", "engine": "AxsAIEngine+BehavioralEngine"}

@app.post("/predict")
def predict(payload: TargetIn):
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