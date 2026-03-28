FROM python:3.11-slim
WORKDIR /app
COPY core /app/core
COPY data /app/data
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    curl build-essential gcc libffi-dev python3-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy source
COPY . /app

ENV PYTHONPATH=/app
EXPOSE 8084
CMD ["uvicorn", "core.mobile.api:app", "--host", "0.0.0.0", "--port", "8084"]
