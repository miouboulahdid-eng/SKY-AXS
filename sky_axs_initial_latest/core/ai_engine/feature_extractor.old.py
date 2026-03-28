#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
وحدة استخراج الخصائص (Feature Extractor)
تُستخدم لتحويل الأهداف إلى تمثيل رقمي يفهمه الذكاء الاصطناعي.
"""

import numpy as np
import pandas as pd

def extract_features(target: str) -> pd.DataFrame:
    """
    استخراج خصائص بسيطة من اسم أو عنوان الهدف.
    """
    # نحسب خصائص مبدئية (قابلة للتوسع لاحقًا)
    features = {
        "length": len(target),
        "upper_case_count": sum(1 for c in target if c.isupper()),
        "digit_count": sum(1 for c in target if c.isdigit()),
        "has_dot": 1 if "." in target else 0,
        "has_dash": 1 if "-" in target else 0
    }

    # نرجع DataFrame حتى تكون متوافقة مع موديلات ML
    return pd.DataFrame([features])

if __name__ == "__main__":
    # اختبار سريع إذا تم تنفيذ الملف مباشرة
    df = extract_features("Example123-Test.com")
    print(df)
