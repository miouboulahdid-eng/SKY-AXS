cat > core/ai_ops/metrics_collector/Dockerfile <<'DOCKER'
FROM python:3.11-slim
WORKDIR /app
COPY core/ai_ops/metrics_collector/requirements.txt /app/requirements.txt
RUN apt-get update -y >/dev/null && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    pip install --no-cache-dir -r /app/requirements.txt && \
    apt-get purge -y && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
COPY core/ai_ops/metrics_collector/metrics_collector.py /app/metrics_collector.py
ENV REDIS_HOST=redis REDIS_PORT=6379 API_URL=http://api:8000/health INTERVAL=10 STREAM_KEY=metrics
CMD ["python","/app/metrics_collector.py"]
