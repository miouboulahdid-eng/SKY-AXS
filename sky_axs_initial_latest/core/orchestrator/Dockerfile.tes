FROM python:3.11-slim
WORKDIR /app

# تثبيت الأدوات الأساسية فقط
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends gcc build-essential libffi-dev python3-dev curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# نسخ ملف الاعتمادات إلى المسار الصحيح داخل الصورة
COPY core/orchestrator/requirements.txt /app/requirements.txt

# تثبيت جميع الاعتمادات (بما فيها numpy)
RUN pip install --no-cache-dir -r /app/requirements.txt

# نسخ باقي ملفات المشروع
COPY . /app

# تشغيل orchestrator
CMD ["python3", "-m", "core.orchestrator.main"]
