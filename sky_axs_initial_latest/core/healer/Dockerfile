FROM python:3.11-slim

WORKDIR /app

COPY monitor.py /app/monitor.py

# تثبيت docker CLI حتى تتمكن الحاوية من مراقبة وإعادة تشغيل غيرها
RUN apt-get update -y && \
    apt-get install -y docker-cli && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

CMD ["python", "/app/monitor.py"]
