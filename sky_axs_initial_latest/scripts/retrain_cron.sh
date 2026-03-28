#!/bin/bash
set -euo pipefail

# --- ضبط المسارات (عدّل إذا لزم) ---
ROOT="/home/ubuntu/projects/sky_axs_initial"
SCRIPT_DIR="$ROOT/scripts"
LOCK="/tmp/axs_retrain.lock"
LOG_DIR="$ROOT/logs"
LOG="$LOG_DIR/retrain.log"
LAST_MARK="$ROOT/data/models/.last_retrain_marker"

mkdir -p "$LOG_DIR" "$ROOT/data/models" "$ROOT/data/results"

# Acquire exclusive lock to avoid concurrent runs
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [INFO] Another retrain in progress, exiting." >> "$LOG"
  exit 0
fi

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [INFO] Retrain wrapper start" >> "$LOG"

# find newest result JSON (if none, exit)
newest_file=$(find "$ROOT/data/results" -maxdepth 1 -type f -name "*.json" -printf "%T@ %p\n" 2>/dev/null | sort -n | tail -1 | awk '{print $2}')
if [ -z "$newest_file" ]; then
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [INFO] No results found, skipping." >> "$LOG"
  exit 0
fi

# If last marker exists and is newer or equal to newest result -> nothing to do
if [ -f "$LAST_MARK" ]; then
  last_ts=$(cat "$LAST_MARK" 2>/dev/null || echo "")
  newest_ts=$(stat -c %Y "$newest_file" 2>/dev/null || echo 0)
  if [ -n "$last_ts" ] && [ "$newest_ts" -le "$last_ts" ]; then
    echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [INFO] No new results since last retrain, skipping." >> "$LOG"
    exit 0
  fi
fi

# Run extraction + training + analysis (best-effort; errors logged)
cd "$ROOT" || exit 1
{
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [INFO] Running extract_features.py"
  PYTHONPATH=. python3 core/ai_engine/extract_features.py

  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [INFO] Running train_baseline.py"
  PYTHONPATH=. python3 core/ai_engine/train_baseline.py

  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [INFO] Running analyzer.py"
  PYTHONPATH=. python3 core/ai_engine/analyzer.py

} >> "$LOG" 2>&1 || {
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [ERROR] One or more steps failed; check log." >> "$LOG"
}

# update marker to newest file mtime so we know we've processed up to this point
if [ -f "$newest_file" ]; then
  newest_epoch=$(stat -c %Y "$newest_file" 2>/dev/null || date +%s)
  printf "%s\n" "$newest_epoch" > "$LAST_MARK"
fi

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [INFO] Retrain wrapper finished" >> "$LOG"
# release lock (happens automatically on script exit)
