FROM python:3.11-slim

WORKDIR /app

# نسخ ملفات الـ API
COPY core /app/core
# تثبيت المتطلبات
COPY core/api/requirements.txt /app/core/api/requirements.txt
RUN pip install --no-cache-dir -r /app/core/api/requirements.txt

# تشغيل خدمة FastAPI
CMD ["uvicorn", "core.api.ai_service:app", "--host", "0.0.0.0", "--port", "8000"]
