#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(pwd)"
echo "[*] Project dir: $PROJECT_DIR"

# تأكد أنك داخل المجلد الصحيح
if [ ! -f "docker-compose.yml" ]; then
echo "ERROR: docker-compose.yml not found in current directory. cd to ~/projects/sky_axs_initial and run again."
exit 1
fi

API_DIR="./core/api"
OVERRIDE_FILE="./docker-compose.api.override.yml"

mkdir -p "$API_DIR"

echo "[*] Ensuring core/api/Dockerfile exists..."
cat > "$API_DIR/Dockerfile" <<'DOCK'
FROM python:3.11-slim
WORKDIR /app

# Copy project files (only what's needed for API)
COPY . /app

# Install runtime dependencies
# requirements.txt should exist in build context
RUN apt-get update -y >/dev/null && apt-get install -y --no-install-recommends gcc build-essential libffi-dev python3-dev >/dev/null || true
RUN pip install --no-cache-dir -r requirements.txt

# helper starter that tries common FastAPI entrypoints
RUN cat > /app/start_uvicorn.sh <<'SH' && chmod +x /app/start_uvicorn.sh
#!/bin/bash
set -euo pipefail
cd /app || exit 1

# try import-able modules
for mod in ai_service api main app; do
python - <<PY 2>/dev/null || true
try:
import importlib, sys
importlib.import_module("$mod")
print("OK")
except Exception:
raise SystemExit(1)
PY
if [ $? -eq 0 ]; then
echo "[start_uvicorn] starting uvicorn $mod:app"
exec uvicorn ${mod}:app --host 0.0.0.0 --port 8080
fi
done

# try files
for f in ./ai_service.py ./api.py ./main.py ./app.py; do
if [ -f "$f" ]; then
name=$(basename "$f" .py)
echo "[start_uvicorn] found file $f -> starting uvicorn ${name}:app"
exec uvicorn ${name}:app --host 0.0.0.0 --port 8080
fi
done

echo "[start_uvicorn] No FastAPI app found in /app. Sleeping to keep container for debug."
sleep infinity
SH

# default entrypoint to the starter
ENTRYPOINT ["bash","/app/start_uvicorn.sh"]
DOCK

echo "[*] Ensuring core/api/requirements.txt exists..."
# only write default file if not exists
if [ ! -f "$API_DIR/requirements.txt" ]; then
cat > "$API_DIR/requirements.txt" <<'REQ'
fastapi
uvicorn[standard]
redis
rq
requests
REQ
echo "[+] Wrote default core/api/requirements.txt"
else
echo "[+] core/api/requirements.txt already exists — leaving it."
fi

echo "[*] Creating docker-compose override (won't overwrite original compose file)..."
cat > "$OVERRIDE_FILE" <<YML
version: "3.9"
services:
api:
build: ./core/api
image: sky_axs_initial-api
depends_on:
- redis
environment:
- REDIS_HOST=redis
# Use the image's ENTRYPOINT which runs start_uvicorn.sh
restart: unless-stopped
YML

echo "[*] Building api image (no cache)..."
docker-compose build --no-cache api

echo "[*] Bringing up api service..."
docker-compose up -d api

echo "[*] Waiting 3s for container to initialize..."
sleep 3

echo "[*] Showing last 200 lines of api logs:"
docker-compose logs --tail=200 api || true

echo
echo "[DONE] If the container failed to start check logs above. Common fixes:"
echo " - Make sure a FastAPI app is present in core/api (ai_service.py, api.py, app.py or main.py) with variable 'app = FastAPI()'"
echo " - If the API file is elsewhere, move or symlink it under core/api so the Dockerfile copies it"
echo " - To inspect container shell: docker-compose exec api bash"
echo
echo "[TIP] If uvicorn not found error persists, open core/api/requirements.txt and ensure uvicorn[standard] is listed then re-run this script."
