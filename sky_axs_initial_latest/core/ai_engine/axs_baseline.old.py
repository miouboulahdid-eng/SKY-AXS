import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler
import joblib
import os
import json
import time

class AxsBaseline:
    """
    نموذج baseline الذكي لتعلم السلوك الطبيعي وتحديثه ديناميكيًا.
    يستخدم IsolationForest للكشف عن السلوك الشاذ،
    و RobustScaler لموازنة البيانات.
    """

    def __init__(self, baseline_path="core/ai_engine/baseline_model.joblib"):
        self.baseline_path = baseline_path
        self.scaler = RobustScaler()
        self.model = None
        self.last_update = None
        self._load_or_initialize()

    def _load_or_initialize(self):
        """تحميل النموذج إذا كان محفوظًا أو إنشاء جديد"""
        if os.path.exists(self.baseline_path):
            try:
                self.model, self.scaler, self.last_update = joblib.load(self.baseline_path)
                print(f"[Baseline] نموذج محمل بنجاح من {self.baseline_path}")
            except Exception as e:
                print(f"[Baseline] فشل في تحميل النموذج: {e}")
                self._initialize_new()
        else:
            print("[Baseline] لم يتم العثور على نموذج سابق — إنشاء نموذج جديد.")
            self._initialize_new()

    def _initialize_new(self):
        """تهيئة نموذج جديد عند عدم وجود واحد سابق"""
        self.model = IsolationForest(
            n_estimators=150,
            contamination=0.02,
            random_state=42
        )
        self.scaler = RobustScaler()
        self.last_update = time.time()

    def fit_baseline(self, data: pd.DataFrame):
        """بناء baseline من بيانات نظيفة (تعلم غير مراقب)"""
        if data.empty:
            print("[Baseline] البيانات فارغة — لم يتم التدريب.")
            return False

        scaled = self.scaler.fit_transform(data)
        self.model.fit(scaled)
        self.last_update = time.time()
        self._save_model()
        print("[Baseline] تم بناء baseline جديد وتحديث النموذج بنجاح ✅")
        return True

    def score(self, features: pd.DataFrame):
        """حساب درجة الشذوذ (anomaly score)"""
        scaled = self.scaler.transform(features)
        scores = -self.model.decision_function(scaled)
        return float(np.mean(scores))

    def detect_anomaly(self, features: pd.DataFrame):
        """إرجاع نتيجة الكشف عن السلوك"""
        score = self.score(features)
        status = "NORMAL" if score < 0.5 else "ANOMALY"
        return {
            "score": score,
            "status": status,
            "last_update": self.last_update
        }

    def _save_model(self):
        """حفظ النموذج محليًا"""
        try:
            joblib.dump((self.model, self.scaler, self.last_update), self.baseline_path)
            print(f"[Baseline] النموذج محفوظ في {self.baseline_path}")
        except Exception as e:
            print(f"[Baseline] فشل حفظ النموذج: {e}")
