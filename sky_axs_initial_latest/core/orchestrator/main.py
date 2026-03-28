#!/usr/bin/env python3
from fastapi import FastAPI, Request
from pydantic import BaseModel
import json, redis, time
from core.ai_engine.axs_ai_engine import AxsAIEngine

# إنشاء تطبيق FastAPI
app = FastAPI(title="AXS Orchestrator with AI", version="2.0")
from core.orchestrator.dynamic_threat_discovery import router as discovery_router
app.include_router(discovery_router)
from core.orchestrator.dynamic_threat_discovery import router as discovery_router
app.include_router(discovery_router)
# إنشاء كائن من الذكاء الاصطنع
ai_engine = AxsAIEngine()

# إعداد Redis للربط
r = redis.Redis(host="redis", port=6379, decode_responses=True)

# تعريف الموديل المستخدم في الطلب
class Target(BaseModel):
    target: str

@app.get("/health")
async def health():
    """التحقق من صحة النظام والاتصال بالذكاء الاصطناعي"""
    try:
        ai_test = ai_engine.process("healthcheck.com")
        redis_status = r.ping()
        return {"status": "ok", "ai": True, "redis": redis_status, "analysis": ai_test}
    except Exception as e:
        return {"status": "error", "details": str(e)}

@app.post("/enqueue")
async def enqueue_task(data: Target):
    """
    استقبال هدف وتحليله وإضافته للطابور مع نتيجة الذكاء الاصطناعي.
    """
    target = data.target.strip()
    if not target:
        return {"error": "Missing target"}

    print(f"[Orchestrator] استقبال الهدف: {target}")
    analysis = ai_engine.process(target)
    print(f"[AI] تحليل الهدف {target}: {analysis}")

    # تخزين النتيجة في Redis
    r.hset(f"analysis:{target}", mapping=json.loads(analysis))
    r.lpush("task_queue", target)

    return {"target": target, "analysis": json.loads(analysis), "status": "queued"}

@app.get("/analysis/{target}")
async def get_analysis(target: str):
    """جلب نتيجة التحليل من Redis"""
    data = r.hgetall(f"analysis:{target}")
    if not data:
        return {"error": "No analysis found for this target"}
    return {"target": target, "analysis": data}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
try:
    from core.orchestrator.dynamic_threat_discovery import router as discovery_router
    app.include_router(discovery_router)
except Exception as _e:
    print(f"[orchestrator] warning: couldn't include discovery router: {_e}")
