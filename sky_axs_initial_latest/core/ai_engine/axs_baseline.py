import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler
from sklearn.ensemble import IsolationForest
import joblib
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASELINE_MODEL_PATH = "/app/data/models/baseline_model.pkl"

class BaselineModel:
    def __init__(self):
        self.scaler = RobustScaler()
        self.detector = IsolationForest(contamination=0.05, random_state=42)
        self.is_fitted = False

    def fit(self, data):
        logging.info("📊 تدريب نموذج الخط الأساسي (Baseline)...")
        scaled = self.scaler.fit_transform(data)
        self.detector.fit(scaled)
        self.is_fitted = True
        self.save()
        return self

    def predict(self, data):
        if not self.is_fitted:
            self.load()
        scaled = self.scaler.transform(data)
        score = -self.detector.score_samples(scaled)
        return score

    def save(self):
        os.makedirs(os.path.dirname(BASELINE_MODEL_PATH), exist_ok=True)
        joblib.dump((self.scaler, self.detector), BASELINE_MODEL_PATH)
        logging.info(f"💾 تم حفظ النموذج في {BASELINE_MODEL_PATH}")

    def load(self):
        if os.path.exists(BASELINE_MODEL_PATH):
            self.scaler, self.detector = joblib.load(BASELINE_MODEL_PATH)
            self.is_fitted = True
            logging.info("✅ تم تحميل النموذج الأساسي.")
        else:
            logging.warning("⚠️ لم يتم العثور على نموذج محفوظ — سيُعاد التدريب عند الحاجة.")
