#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AXS Self-Healing Engine v3.0
----------------------------------------
- مراقبة تلقائية لكل الحاويات
- إعادة تشغيل باستخدام أحدث الصور
- تكامل مع طبقة AI/ML للتنبؤ بالأعطال
- متوافق بالكامل مع بيئة sky_axs_initial
"""

import os
import subprocess
import time
import datetime
import json
import random

# =========================
# إعدادات عامة
# =========================
CHECK_INTERVAL = 15  # كل كم ثانية يتم التحقق
CONTAINERS = {
    "sky_axs_initial-api": "sky_axs_initial-api",
    "sky_axs_initial-worker": "sky_axs_initial-worker",
    "sky_axs_initial-orchestrator": "sky_axs_initial-orchestrator",
    "sky_axs_initial-redis": "redis:latest"
}

# =========================
# طبقة التنبؤ الذكي AI/ML
# =========================
def ai_predict_failure(container_name: str) -> bool:
    """
    محاكاة بسيطة للتنبؤ باحتمال فشل الحاوية.
    مستقبلاً يمكن استبدالها بذكاء حقيقي يعتمد على بيانات التشغيل.
    """
    # افتراضياً: احتمالية عشوائية للفشل (كمثال)
    probability = random.random()
    risk = "HIGH" if probability > 0.85 else "LOW"
    print(f"[AI/ML] ⚙️  تقييم {container_name}: احتمالية الفشل = {probability:.2f} ({risk})")
    return probability > 0.9


# =========================
# إعادة التشغيل الذكية
# =========================
def restart_container(container_name: str, image_name: str):
    ts = datetime.datetime.utcnow().isoformat()
    print(f"[{ts}] 🔄 إعادة تشغيل {container_name} باستخدام أحدث صورة ({image_name})...")

    try:
        # تحديث الصورة أو إعادة بناءها
        if "sky_axs_initial" in image_name:
            subprocess.run(["docker-compose", "build", container_name], check=True)
        else:
            subprocess.run(["docker", "pull", image_name], check=True)

        # إعادة التشغيل من جديد
        subprocess.run(["docker", "stop", container_name], check=False)
        subprocess.run(["docker", "rm", container_name], check=False)
        subprocess.run(["docker-compose", "up", "-d", container_name], check=True)

        print(f"[{ts}] ✅ تم تحديث وإعادة تشغيل {container_name} بنجاح.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[{ts}] ❌ فشل إعادة تشغيل {container_name}: {e}")
        return False


# =========================
# فحص الحالة الحالية
# =========================
def get_container_status(name: str) -> str:
    try:
        output = subprocess.getoutput(f"docker inspect -f '{{{{.State.Status}}}}' {name}")
        return output.strip()
    except Exception:
        return "unknown"


# =========================
# المعالج الرئيسي
# =========================
def monitor():
    print("[🚑] Self-Healing Engine بدأ العمل بنجاح...\n")
    while True:
        for name, image in CONTAINERS.items():
            status = get_container_status(name)
            ts = datetime.datetime.utcnow().isoformat()

            if status != "running":
                print(f"[{ts}] ⚠️  {name} متوقفة (الحالة = {status}) -> محاولة إصلاح...")
                restart_container(name, image)

            elif ai_predict_failure(name):
                print(f"[{ts}] 🤖 الذكاء الاصطناعي توقع فشل قريب في {name} -> إجراء وقائي.")
                restart_container(name, image)

            else:
                print(f"[{ts}] ✅ {name} تعمل بشكل طبيعي.")

        print("---------------------------------------------------")
        time.sleep(CHECK_INTERVAL)


# =========================
# نقطة التشغيل الرئيسية
# =========================
if __name__ == "__main__":
    try:
        monitor()
    except KeyboardInterrupt:
        print("\n[🛑] تم إيقاف الـ Self-Healing Engine يدوياً.")
