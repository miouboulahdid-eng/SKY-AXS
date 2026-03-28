from fastapi import FastAPI, Request
from pydantic import BaseModel
from core.ai_engine.behavior_engine import BehaviorEngine
from core.ai_engine.axs_ai_engine import AxsAIEngine
import json
import time
import sys, os
sys.path.append("/app")
app = FastAPI(title="AXS AI Orchestrator", version="2.0")

# تهيئة المحركات الذكية
ai_engine = AxsAIEngine()
behavior_engine = BehaviorEngine()

class PredictRequest(BaseModel):
    input_text: str

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "ai_engine": "AxsAIEngine",
        "behavior_engine": "BehaviorEngine"
    }

@app.post("/predict")
async def predict(request: PredictRequest):
    """
    نقطة رئيسية لتحليل الهدف عبر محرك الذكاء الاصطناعي والسلوك.
    """
    try:
        input_data = request.input_text.strip()
        if not input_data:
            return {"error": "المدخل فارغ"}

        # تحليل أولي بالذكاء الاصطناعي
        ai_result = ai_engine.analyze_target(input_data)

        # تحويل نتيجة الذكاء الاصطناعي إلى ميزات عددية للسلوك
        features = {
            "risk_score": ai_result.get("risk_score", 0),
            "confidence": ai_result.get("confidence", 0.5),
            "complexity": ai_result.get("complexity", 1.0),
            "timestamp": time.time() % 1000
        }

        # تحليل السلوك
        behavior_result = behavior_engine.analyze_behavior(features)

        # تحديث baseline عند السلوك الطبيعي
        if behavior_result.get("status") == "NORMAL":
            behavior_engine.update_baseline(features)

        response = {
            "input": input_data,
            "ai_analysis": ai_result,
            "behavior_analysis": behavior_result,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        print(f"[API] ✅ تحليل مكتمل: {json.dumps(response, ensure_ascii=False)}")
        return response

    except Exception as e:
        print(f"[API] ⚠️ خطأ أثناء التحليل: {e}")
        return {"status": "error", "detail": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
# ====== Sandbox enqueue endpoint ======
try:
    from rq import Queue
    from redis import Redis
    HAVE_RQ = True
except Exception:
    HAVE_RQ = False

def _get_queue():
    from redis import Redis
    from rq import Queue
    redis_conn = Redis(host="redis", port=6379, db=0)
    return Queue("default", connection=redis_conn)

from fastapi import Body

@app.post("/sandbox/run")
def sandbox_run(payload: dict = Body(...)):
    """
    استدعاء Sandbox لتشغيل مهمة معزولة
    مثال:
    {
      "target": "example.com",
      "extra": "--dry-run"
    }
    """
    if not HAVE_RQ:
        return {"status": "error", "detail": "RQ/Redis not available"}

    target = (payload or {}).get("target", "").strip()
    extra = (payload or {}).get("extra", "")

    if not target:
        return {"status": "error", "detail": "target required"}

    q = _get_queue()
    from core.worker.sandbox_task import sandbox_task_run_in_sandbox
    job = q.enqueue(
        "core.worker.sandbox_task_run_in_sandbox",
        target,
        extra,
        job_timeout=600,
        result_ttl=1,
    )
    return {"status": "queued", "job_id": job.id, "queue": q.name}
# =====================[ Sandbox Result Endpoint ]=====================

from typing import Optional

try:
    from rq import Queue
    from rq.job import Job
    from redis import Redis
    HAVE_RQ = True
except Exception:
    HAVE_RQ = False


@app.get("/sandbox/result/{job_id}")
def sandbox_result(job_id: str):
    """
    استرجاع حالة/نتيجة مهمة الساندبوكس من RQ عبر job_id.
    """
    if not HAVE_RQ:
        return {"status": "error", "detail": "RQ/Redis not available"}

    host = os.environ.get("REDIS_HOST", "redis")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    conn = Redis(host=host, port=port)

    try:
        job = Job.fetch(job_id, connection=conn)
        return {
            "status": job.get_status(refresh=True),
            "enqueued_at": str(job.enqueued_at) if job.enqueued_at else None,
            "ended_at": str(job.ended_at) if job.ended_at else None,
            "result": job.result,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

# =====================================================================
# --- Patch Redis connection fallback (fix for internal server error) ---
import os
from redis import Redis

def get_redis_connection():
    """
    تصحيح اتصال Redis داخل الـ Docker: إذا كان host=localhost
    فاستبدله بـ redis حتى يعمل الربط الداخلي.
    """
    host = os.environ.get("REDIS_HOST", "redis")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    if host in ("localhost", "127.0.0.1"):
        host = "redis"
    return Redis(host=host, port=port)
# -----------------------------------------------------------------------
