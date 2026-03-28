#!/usr/bin/env python3
import subprocess, time, datetime, logging, os

# إعدادات السجل
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [Redis Guardian] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

REDIS_CONTAINER = "sky_axs_initial-redis"
CHECK_INTERVAL = 30  # ثانية

def is_container_running(name):
    """يتحقق إن كانت الحاوية تعمل"""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True, text=True, check=True
        )
        return "true" in result.stdout.strip()
    except subprocess.CalledProcessError:
        return False

def restart_redis():
    """إعادة تشغيل Redis باستخدام docker-compose"""
    logging.warning("🚨 Redis متوقف — إعادة تشغيل الآن...")
    try:
        subprocess.run(
            ["docker-compose", "up", "-d", "redis"],
            check=True
        )
        logging.info("✅ Redis تمت إعادة تشغيله بنجاح.")
    except Exception as e:
        logging.error(f"❌ فشل في إعادة تشغيل Redis: {e}")

def monitor_redis():
    """مراقبة Redis بشكل دوري"""
    logging.info("🚀 Redis Guardian بدأ العمل بنجاح.")
    while True:
        if not is_container_running(REDIS_CONTAINER):
            logging.warning("⚠️  Redis غير متصل — بدء إجراء الإصلاح...")
            restart_redis()
        else:
            logging.info("💚 Redis يعمل بشكل طبيعي.")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor_redis()
