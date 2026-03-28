# ==========================
# AXS AI Self-Healer (v4.0 – Docker SDK Native)
# ==========================
FROM python:3.11-slim

WORKDIR /app

# تثبيت مكتبات النظام
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    gcc python3-dev libffi-dev curl iputils-ping procps \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# نسخ كود الذكاء الذاتي
COPY monitor.py /app/monitor.py

# تثبيت المكتبات المطلوبة
RUN pip install --no-cache-dir docker psutil redis requests numpy tenacity

# ضبط متغيرات البيئة
ENV WATCH="sky_axs_initial-api,sky_axs_initial-worker,sky_axs_initial-orchestrator,sky_axs_initial-redis" \
    INTERVAL=10 \
    MAX_UNHEALTHY=3 \
    LOG_LEVEL=INFO \
    PYTHONUNBUFFERED=1

# منح صلاحية الوصول إلى Docker socket
VOLUME ["/var/run/docker.sock"]

CMD ["python", "/app/monitor.py"]
