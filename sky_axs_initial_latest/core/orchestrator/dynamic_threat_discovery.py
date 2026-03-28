#!/usr/bin/env python3
"""
📘 Dynamic Threat Discovery Router
الملف: core/orchestrator/dynamic_threat_discovery.py
وظيفته: ربط Orchestrator مع AutoAdaptEngine لتوليد استراتيجيات ذكية حسب الهدف.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import json, os, redis
from rq import Queue

# نحاول استيراد المحرك الذكي
try:
    from core.ai_engine.auto_adapt import AutoAdaptEngine
    HAVE_ADAPT = True
except Exception as e:
    HAVE_ADAPT = False
    print(f"[Discovery] ⚠️ لم يتم تحميل AutoAdaptEngine: {e}")

# تهيئة الراوتر
router = APIRouter(prefix="/discovery", tags=["discovery"])

# إعداد Redis / RQ
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
RQ_QUEUE_NAME = os.environ.get("RQ_QUEUE", "default")

rconn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
queue = Queue(RQ_QUEUE_NAME, connection=rconn)

# موديلات الإدخال والإخراج
class AdaptRequest(BaseModel):
    target: str
    extra: Optional[Dict[str, Any]] = {}

class AdaptResult(BaseModel):
    target: str
    type: str
    strategy: List[str]
    status: str

# نقطة تنفيذ التحليل الذكي
@router.post("/adapt")
async def run_auto_adapt(req: AdaptRequest):
    """تحليل الهدف وإرجاع استراتيجية الفحص المناسبة."""
    if not HAVE_ADAPT:
        raise HTTPException(status_code=500, detail="AutoAdaptEngine غير متاح")

    engine = AutoAdaptEngine()

    try:
        result = engine.adapt_strategy(req.target)
        # حفظ النتيجة في Redis
        rconn.hset("adapt:results", req.target, json.dumps(result, ensure_ascii=False))
        # إرسال المهمة إلى الـ Worker عبر RQ
        queue.enqueue("core.worker.sandbox_task_run_in_sandbox", req.target, "--auto-adapt", job_timeout=600)
        return {"status": "adapted", "target": req.target, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ملخص آخر التحليلات المخزّنة
@router.get("/summary")
async def get_adapt_summary():
    """عرض أحدث نتائج التحليل الذكي."""
    try:
        data = rconn.hgetall("adapt:results")
        parsed = {k: json.loads(v) for k, v in data.items()}
        return {
            "processed": len(parsed),
            "last_jobs": list(parsed.values())[-5:],
            "queue": RQ_QUEUE_NAME,
            "redis": f"{REDIS_HOST}:{REDIS_PORT}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis error: {e}")
