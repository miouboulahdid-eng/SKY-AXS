FROM python:3.11-slim
WORKDIR /app

# أقل الحزم الممكنة للتجميع (لا نريد رسائل كثيرة)
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends gcc build-essential libffi-dev python3-dev curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ننسخ فقط ما نحتاجه لبناء طبقة الاعتمادات بسرعة
# (requirements قد تكون في core/api/requirements.txt — ننسخها مكان متوقع /app/requirements.txt)
COPY core/api/requirements.txt /app/requirements.txt

# انسخ بقية المشروع لجعل starter يستطيع إيجاد ملف التطبيق
COPY . /app

# ثبت الاعتمادات من المسار المعروف
RUN pip install --no-cache-dir -r /app/requirements.txt

# نضع سكربت بداية ذكي
RUN mkdir -p /app && cat > /app/start_uvicorn.sh <<'SH' && chmod +x /app/start_uvicorn.sh
#!/usr/bin/env bash
set -euo pipefail
cd /app

# حاول تشغيل uvicorn كأمر مباشر أو عبر python -m لتجنّب مشكلات PATH
start_uvicorn(){
  local mod="$1"
  echo "[start_uvicorn] trying module: ${mod}:app"
  exec python -m uvicorn "${mod}:app" --host 0.0.0.0 --port ${PORT:-8081}
}

# قائمة أسماء/مسارات محتملة لملف FastAPI داخل المشروع
CANDIDATES=(
  "core.api_server"
  "core.api"
  "api"
  "main"
  "app"
  "core.api.main"
  "core.api.app"
)

for m in "${CANDIDATES[@]}"; do
  python - <<PY 2>/dev/null
try:
    import importlib, sys
    importlib.import_module("$m")
    print("OK")
except Exception:
    raise SystemExit(1)
PY
  if [ $? -eq 0 ]; then
    start_uvicorn "$m"
  fi
done

# إذا لم نجد، افتح صدف للمراجعة وابقَ حياً للحَلّ
echo "[start_uvicorn] No FastAPI module found in /app — dropping to sleep for debug"
sleep infinity
SH

# ENTRYPOINT هو سكربت البداية
ENTRYPOINT ["/app/start_uvicorn.sh"]
CMD []
