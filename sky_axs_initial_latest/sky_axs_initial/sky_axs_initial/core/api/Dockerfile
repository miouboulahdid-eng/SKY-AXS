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
