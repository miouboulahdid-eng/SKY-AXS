import logging
import numpy as np
from datetime import datetime
from core.ai_engine.axs_baseline import BaselineModel
from core.ai_engine.feature_extractor import FeatureExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class AxsAIEngine:
    def __init__(self):
        self.extractor = FeatureExtractor()
        self.baseline = BaselineModel()

    def analyze_target(self, text):
        """تحليل نص الهدف وإرجاع درجة الشذوذ ومستوى الخطر"""
        logging.info("🚀 بدء تحليل الهدف...")
        try:
            features = self.extractor.extract_features(text)
            if not self.baseline.is_fitted:
                self.baseline.fit(features)
            scores = self.baseline.predict(features)
            avg_score = float(np.mean(scores))
            risk = self._risk_level(avg_score)
            result = {
                "target": text,
                "score": round(avg_score, 2),
                "risk": risk,
                "timestamp": datetime.utcnow().isoformat()
            }
            logging.info(f"✅ تحليل مكتمل: {result}")
            return result
        except Exception as e:
            logging.error(f"❌ خطأ أثناء التحليل: {e}")
            return {"error": str(e)}

    def _risk_level(self, score):
        if score < 0.3:
            return "LOW"
        elif score < 0.6:
            return "MEDIUM"
        else:
            return "HIGH"
