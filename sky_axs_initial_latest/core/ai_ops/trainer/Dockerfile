FROM python:3.11-slim
WORKDIR /app
COPY core/ai_ops/trainer/requirements.txt /app/requirements.txt
RUN apt-get update -y >/dev/null && apt-get install -y --no-install-recommends \
    gcc g++ make && \
    pip install --no-cache-dir -r /app/requirements.txt && \
    apt-get purge -y gcc g++ make && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
COPY core/ai_ops/trainer/trainer.py /app/trainer.py
ENV REDIS_HOST=redis REDIS_PORT=6379 STREAM_KEY=metrics WINDOW_SEC=1800 TRAIN_EVERY_SEC=300 MODEL_DIR=/data/models
VOLUME ["/data/models"]
CMD ["python","/app/trainer.py"]
