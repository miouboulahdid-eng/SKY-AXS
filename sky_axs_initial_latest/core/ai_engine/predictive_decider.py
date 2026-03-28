import re
from typing import Dict, Any, List
from .feedback_store import FeedbackStore

def infer_target_type(target: str) -> str:
    t = target.lower()
    if t.endswith(".apk") or t.endswith(".ipa"):
        return "MOBILE"
    if re.match(r"^https?://", t) or "." in t:
        return "WEB"
    return "GENERIC"

def default_strategy_for(t: str) -> List[str]:
    if t == "WEB":
        return ["dirb", "xss", "sqlmap"]
    if t == "MOBILE":
        return ["apktool", "static-scan", "dynamic-frida"]
    return ["nmap", "fingerprint"]

class PredictiveDecider:
    """
    يقرأ التغذية الراجعة ويعدّل:
      - inferred_type
      - strategy
      - priority
      - route_queue (default/decision/ml)
    """
    def __init__(self, store: FeedbackStore):
        self.store = store

    def decide(self, target: str, task_type: str="auto", extra: str="") -> Dict[str, Any]:
        ttype = infer_target_type(target)
        base_strategy = default_strategy_for(ttype)
        profile = self.store.domain_profile(target)
        total = profile.get("total", 0)
        high = profile.get("HIGH", 0)
        medium = profile.get("MEDIUM", 0)
        low = profile.get("LOW", 0)

        # أولوية ديناميكية
        priority = 0
        if high >= 2:
            priority = 2
        elif medium >= 2:
            priority = 1

        # توجيه ذكي للطوابير
        route_queue = "default"
        if task_type == "train" or (total >= 5 and high >= 1):
            route_queue = "ml"

        # تكثيف الإستراتيجية إذا المخاطر مرتفعة مسبقًا
        strategy = list(base_strategy)
        if high >= 2 and ttype == "WEB":
            extra_tools = ["ffuf", "sqli-deep", "authz-check"]
            for tool in extra_tools:
                if tool not in strategy:
                    strategy.append(tool)

        return {
            "target": target,
            "inferred_type": ttype,
            "task_type": task_type,
            "priority": priority,
            "strategy": strategy,
            "route_queue": route_queue,
            "profile": profile,
            "extra": extra
        }
