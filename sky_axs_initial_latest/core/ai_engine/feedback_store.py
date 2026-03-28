import os, json, threading, time
from typing import Dict, Any, Optional

DATA_DIR = "/app/data/models"
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.jsonl")

_lock = threading.Lock()

class FeedbackStore:
    """
    تخزين التغذية الراجعة (نتائج/تحليلات) في JSONL + ذاكرة تجميعية في الذاكرة.
    بنية السجل:
    { "timestamp": 1699999999.123, "target": "...", "risk": "LOW/MEDIUM/HIGH", "score": 0.0-1.0, "context": {...} }
    """
    def __init__(self, path: str = FEEDBACK_FILE):
        self.path = path
        self.stats = {
            "total": 0,
            "by_domain": {},   # domain -> counts
            "by_risk": {"LOW":0, "MEDIUM":0, "HIGH":0},
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        self._accumulate(rec)
                    except Exception:
                        continue
        except Exception:
            pass

    def _accumulate(self, rec: Dict[str, Any]):
        self.stats["total"] += 1
        risk = str(rec.get("risk", "MEDIUM")).upper()
        if risk not in self.stats["by_risk"]:
            self.stats["by_risk"][risk] = 0
        self.stats["by_risk"][risk] += 1

        target = rec.get("target","")
        domain_key = self._normalize_target_to_key(target)
        self.stats["by_domain"].setdefault(domain_key, {"LOW":0,"MEDIUM":0,"HIGH":0,"total":0})
        self.stats["by_domain"][domain_key]["total"] += 1
        self.stats["by_domain"][domain_key].setdefault(risk, 0)
        self.stats["by_domain"][domain_key][risk] += 1

    @staticmethod
    def _normalize_target_to_key(target: str) -> str:
        t = target.strip().lower()
        t = t.replace("https://","").replace("http://","")
        t = t.replace("/", "_")
        return t

    def add_feedback(self, target: str, risk: str, score: float, context: Optional[Dict[str,Any]]=None):
        ts = time.time()
        rec = {
            "timestamp": ts,
            "target": target,
            "risk": str(risk).upper(),
            "score": float(score),
            "context": context or {}
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with _lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._accumulate(rec)
        return rec

    def summary(self) -> Dict[str, Any]:
        with _lock:
            return {
                "total": self.stats["total"],
                "by_risk": dict(self.stats["by_risk"]),
                "domains": {
                    k: dict(v) for k, v in list(self.stats["by_domain"].items())[:200]
                }
            }

    def domain_profile(self, target: str) -> Dict[str, Any]:
        key = self._normalize_target_to_key(target)
        with _lock:
            return dict(self.stats["by_domain"].get(key, {"LOW":0,"MEDIUM":0,"HIGH":0,"total":0}))
