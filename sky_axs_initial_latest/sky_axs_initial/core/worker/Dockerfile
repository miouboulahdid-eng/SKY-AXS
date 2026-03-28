FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r /app/requirements.txt
CMD ["rq", "worker", "-u", "redis://redis:6379", "default"]
