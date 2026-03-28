import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class FeatureExtractor:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=300)

    def extract_features(self, text_data):
        """تحويل النصوص إلى ميزات عددية قابلة للتحليل"""
        if isinstance(text_data, str):
            text_data = [text_data]
        logging.info("🧠 استخراج الميزات النصية...")
        features = self.vectorizer.fit_transform(text_data).toarray()
        return features

    def transform_existing(self, text_data):
        if isinstance(text_data, str):
            text_data = [text_data]
        return self.vectorizer.transform(text_data).toarray()
