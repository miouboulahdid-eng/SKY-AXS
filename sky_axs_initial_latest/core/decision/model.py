import os, json, math, time
from datetime import datetime

# نقطة حفظ نموذج (إن استخدمنا sklearn)
MODEL_PATH = "/app/data/models/decision_meta.pkl"
os.makedirs("/app/data/models", exist_ok=True)

def _infer_target_type(target: str) -> str:
    t = (target or "").lower()
    if t.startswith(("http://", "https://")):
        return "WEB"
    if t.endswith((".apk", ".ipa")):
        return "MOBILE"
    if any(c.isalpha() for c in t) and "/" in t:
        return "API"
    if all(ch.isdigit() or ch == "." for ch in t):
        return "NETWORK"
    return "GENERIC"

def _rule_based(features: dict) -> dict:
    """بديل بدون sklearn: قرار بسيط قائم على قواعد مرجّحة."""
    ml_score = float(features.get("ml_score", 0.5))
    has_history = int(features.get("has_history", 0))
    n_results = int(features.get("recent_files", 0))
    entropy = float(features.get("avg_entropy", 0.0))
    target_type = str(features.get("target_type", "GENERIC"))

    # وزن بسيط
    w = 0.45*ml_score + 0.15*has_history + 0.15*min(n_results/5, 1.0) + 0.25*min(entropy/4.0, 1.0)

    if target_type in ("WEB", "API") and ml_score >= 0.6:
        w = min(1.0, w + 0.15)

    if w >= 0.75:
        priority = 2
        queue = "default"   # يمكن تغييره لـ "decision" لاحقاً
        strategy_boost = True
    elif w >= 0.45:
        priority = 1
        queue = "default"
        strategy_boost = False
    else:
        priority = 0
        queue = "default"
        strategy_boost = False

    return {
        "priority": priority,
        "queue": queue,
        "confidence": round(w, 3),
        "strategy_boost": strategy_boost,
    }

def decide(features: dict) -> dict:
    """
    يُرجع:
      {priority, queue, confidence, strategy_boost}
    """
    # نحاول sklearn إن موجود:
    try:
        from sklearn.linear_model import LogisticRegression  # noqa: F401
        # في هذه النسخة نستخدم fallback لحين تدريب فعلي
        return _rule_based(features)
    except Exception:
        return _rule_based(features)

def build_features(target: str,
                   ml_score: float = 0.5,
                   recent_files: int = 0,
                   avg_entropy: float = 0.0,
                   has_history: int = 0) -> dict:
    return {
        "target": target,
        "target_type": _infer_target_type(target),
        "ml_score": float(ml_score),
        "recent_files": int(recent_files),
        "avg_entropy": float(avg_entropy),
        "has_history": int(has_history),
        "ts": datetime.utcnow().isoformat()
    }
