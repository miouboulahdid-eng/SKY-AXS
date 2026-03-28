from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Any, Dict

from core.ai_engine.axs_ai_engine import AxsAIEngine
from core.ai_engine.behavior_engine import get_behavior_engine

app = FastAPI(title="AXS AI API", version="1.1")

ai_basic = AxsAIEngine()
behavior = get_behavior_engine()

class TargetIn(BaseModel):
    target: str

class EventsIn(BaseModel):
    events: List[Any]  # list[str|dict]

@app.get("/health")
def health():
    return {"status": "healthy", "engine": "AxsAIEngine+BehavioralEngine"}

@app.post("/predict")
def predict(payload: TargetIn):
    """نموذج الذكاء الأساسي (سابقاً)."""
    result = ai_basic.process(payload.target)
    return {"target": payload.target, "analysis": result, "status": "ok"}

@app.post("/behavior/ingest")
def behavior_ingest(payload: EventsIn):
    """
    تغذية baseline لتعلّم الأنماط (غير مراقَب).
    مثال حدث: {"target": "sub.example.com", "method":"GET","path":"/a","timestamp":1690000000}
    """
    info = behavior.ingest(payload.events)
    return {"status": "ok", **info}

@app.post("/behavior/score")
def behavior_score(payload: EventsIn):
    """
    إرجاع درجة الشذوذ لكل حدث.
    إذا الموديل لم يُدرّب بعد، سيخزن الأحداث كـ baseline ويرجع note.
    """
    out = behavior.score(payload.events)
    return {"status": "ok", **out}
