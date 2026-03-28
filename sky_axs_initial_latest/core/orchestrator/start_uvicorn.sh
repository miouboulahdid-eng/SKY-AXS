#!/bin/sh
set -e

echo "[start_uvicorn] launching AXS AI API..."
exec uvicorn core.orchestrator.main:app --host 0.0.0.0 --port 8081
