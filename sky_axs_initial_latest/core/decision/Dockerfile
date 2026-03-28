FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update -y && \
    apt-get install -y --no-install-recommends gcc build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# المتطلبات
COPY core/decision/requirements.txt /app/core/decision/requirements.txt
RUN pip install --no-cache-dir -r /app/core/decision/requirements.txt

# ننسخ المشروع كله (مطلوب لأننا نستدعي core.worker.* من الـ worker)
COPY . /app

EXPOSE 8083
RUN mkdir -p /app/data/decisions
CMD ["uvicorn", "core.decision.decision_service:app", "--host", "0.0.0.0", "--port", "8083"]
