import json
import time
import requests
from core.ai_engine.axs_ai_engine import AxsAIEngine

class AIBridge:
    """
    جسر الربط بين الذكاء الاصطناعي AxsAIEngine والـ Worker لتنفيذ قرارات تصحيحية ذاتية.
    """

    def __init__(self, worker_endpoint="http://worker:8083/action"):
        self.ai_engine = AxsAIEngine()
        self.worker_endpoint = worker_endpoint

    def analyze_and_act(self, target: str):
        """تحليل الهدف وتنفيذ الإجراء إذا لزم الأمر"""
        analysis_json = self.ai_engine.process(target)
        analysis = json.loads(analysis_json)
        risk = analysis.get("risk", "LOW")
        trend = analysis.get("trend", "")

        print(f"[AIBridge] تحليل الهدف {target}: {risk} | الاتجاه: {trend}")

        # قرارات تصحيحية تلقائية
        if risk == "HIGH":
            action = {
                "target": target,
                "action": "isolate",
                "reason": "خطر مرتفع تم اكتشافه تلقائيًا"
            }
            self._send_to_worker(action)

        elif "ارتفاع في المخاطر" in trend:
            action = {
                "target": target,
                "action": "increase_monitoring",
                "reason": "توجه خطير متزايد"
            }
            self._send_to_worker(action)

        elif risk == "LOW":
            print(f"[AIBridge] الهدف {target} آمن — لا حاجة لإجراء.")
        else:
            print(f"[AIBridge] مراقبة مستمرة للهدف {target}.")

        return analysis

    def _send_to_worker(self, action_data: dict):
        """إرسال القرار إلى الـ Worker"""
        try:
            print(f"[AIBridge] تنفيذ الإجراء: {action_data}")
            response = requests.post(self.worker_endpoint, json=action_data, timeout=5)
            print(f"[AIBridge] استجابة الـ Worker: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[AIBridge] خطأ أثناء إرسال القرار إلى الـ Worker: {e}")
