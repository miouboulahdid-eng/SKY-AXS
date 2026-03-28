FROM python:3.11-slim
WORKDIR /app

# نسخ ملف المتطلبات
COPY core/worker/requirements.txt /app/requirements.txt

# تثبيت الأدوات الأساسية
RUN apt-get update -y && apt-get install -y --no-install-recommends gcc build-essential libffi-dev python3-dev

# تثبيت مكتبات Python المطلوبة
RUN pip install --no-cache-dir -r /app/requirements.txt

# نسخ كل المشروع
COPY . /app

# تشغيل العامل RQ
CMD ["rq", "worker", "-u", "redis://redis:6379", "default"]
