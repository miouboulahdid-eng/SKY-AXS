import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler
from sklearn.ensemble import IsolationForest
import time

class BehaviorEngine:
    """
    محرك تحليل السلوك لتحديد الأنماط الشاذة ومقارنة baseline بالسلوك الحالي.
    """

    def __init__(self):
        self.scaler = RobustScaler()
        self.model = IsolationForest(contamination=0.1, random_state=42)
        self.is_fitted = False
        self.baseline = pd.DataFrame(columns=["score", "risk_value"])

    def update_baseline(self, features: dict):
        """
        تحديث السلوك الطبيعي baseline ببيانات جديدة.
        """
        risk_map = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        new_data = pd.DataFrame([{
            "score": features.get("score", 0.5),
            "risk_value": risk_map.get(features.get("risk", "MEDIUM"), 1)
        }])

        self.baseline = pd.concat([self.baseline, new_data], ignore_index=True)

        # إعادة تدريب الـ scaler والنموذج
        if len(self.baseline) > 5:
            scaled = self.scaler.fit_transform(self.baseline)
            self.model.fit(scaled)
            self.is_fitted = True
            print("[BehaviorEngine] ✅ baseline updated & model fitted")

    def analyze_behavior(self, features: dict):
        """
        تحليل السلوك الحالي ومقارنته بخط الأساس baseline.
        """
        try:
            if not self.is_fitted:
                # تهيئة تلقائية أول مرة
                print("[BehaviorEngine] ⚙️ Initial fit triggered...")
                self.update_baseline(features)

            risk_map = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
            data_point = pd.DataFrame([{
                "score": features.get("score", 0.5),
                "risk_value": risk_map.get(features.get("risk", "MEDIUM"), 1)
            }])

            scaled_point = self.scaler.transform(data_point)
            prediction = self.model.predict(scaled_point)[0]

            status = "ANOMALY" if prediction == -1 else "NORMAL"
            return {
                "status": status,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception as e:
            return {"status": "ERROR", "detail": str(e)}
