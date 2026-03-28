#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-Adapt Layer
الطبقة الذكية التي تحلل الهدف وتحدد نوع الفحص المناسب (Web/API/Mobile/...).
"""

import re
import json

class AutoAdaptEngine:
    """
    تقوم هذه الطبقة بتحليل الهدف وتحديد نوعه، لتوجيهه إلى المنهج الأنسب للفحص.
    """

    def __init__(self):
        # أنماط لتصنيف الأهداف
        self.patterns = {
            "web": re.compile(r"(https?://|www\.)", re.IGNORECASE),
            "api": re.compile(r"/api/v\d+|api\.|\.json|\.rest", re.IGNORECASE),
            "mobile": re.compile(r"\.apk$|\.ipa$", re.IGNORECASE),
            "network": re.compile(r"^\d{1,3}(\.\d{1,3}){3}$"),  # IP
        }

    def detect_type(self, target: str) -> str:
        """
        يحدد نوع الهدف بناءً على الأنماط المعرفة أعلاه.
        """
        for name, pattern in self.patterns.items():
            if pattern.search(target):
                return name.upper()
        return "GENERIC"

    def adapt_strategy(self, target: str) -> dict:
        """
        يعيد تهيئة الاستراتيجية بناءً على نوع الهدف.
        """
        target_type = self.detect_type(target)

        strategies = {
            "WEB": ["dirb", "xss", "sqlmap"],
            "API": ["postman-tests", "jwt-audit"],
            "MOBILE": ["apktool", "frida", "mobSF"],
            "NETWORK": ["nmap", "portscan"],
            "GENERIC": ["info-gather", "passive-scan"]
        }

        chosen = strategies.get(target_type, strategies["GENERIC"])
        return {
            "target": target,
            "type": target_type,
            "strategy": chosen,
            "status": "adapted"
        }


if __name__ == "__main__":
    engine = AutoAdaptEngine()
    samples = ["https://example.com", "api.example.com/v1/users", "10.0.0.5", "app.apk", "unknown-target"]
    results = [engine.adapt_strategy(t) for t in samples]
    print(json.dumps(results, indent=2, ensure_ascii=False))
