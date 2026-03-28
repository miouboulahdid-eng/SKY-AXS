#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# CONFIG - عدّل هنا إذا أردت
REGION="${REGION:-eu-north-1}"
BUCKET="${BUCKET:-my-sky-axs-bucket-yourname}"
S3_KEY="${S3_KEY:-core/legacy/sky.sh}"
LOCAL_SKY="./core/legacy/sky.sh"
INSTANCE_ID="${INSTANCE_ID:-i-073815d079f010ce6}"   # ضع هنا instance المطلوب
TARGET="${TARGET:-example.com}"
OUTDIR_LOCAL="/tmp/sky_run_local"
SSM_PARAMS_FILE=$(mktemp -t ssm_params.XXXX.json)
TMP_B64=$(mktemp -t urlb64.XXXX)
CMD_TIMEOUT="${CMD_TIMEOUT:-3600}"

echo "[%] Region: $REGION"
echo "[%] Bucket: $BUCKET"
echo "[%] S3 key: $S3_KEY"
echo "[%] Local sky.sh: $LOCAL_SKY"
echo "[%] Instance: $INSTANCE_ID"
echo "[%] Target: $TARGET"

# 1) تأكد الملف محلياً
if [ ! -f "$LOCAL_SKY" ]; then
  echo "ERROR: $LOCAL_SKY not found. Place sky.sh there or change LOCAL_SKY."
  exit 2
fi

# 2) ارفع الملف إلى S3 (حاول، وتابع إن كان موجود)
echo "[%] Uploading to s3://$BUCKET/$S3_KEY (will overwrite if allowed)"
aws s3 cp "$LOCAL_SKY" "s3://$BUCKET/$S3_KEY" --region "$REGION" || {
  echo "[!] Warning: upload to S3 failed (check s3:PutObject permission). Continuing if object already exists."
}

# 3) أنشئ presigned URL
echo "[%] Generating presigned URL (1h)..."
PRESIGNED_URL=$(aws s3 presign "s3://${BUCKET}/${S3_KEY}" --region "$REGION" --expires-in 3600)
echo "[%] PRESIGNED_URL=$PRESIGNED_URL"

# 4) اختبر التنزيل محلياً
echo "[%] Testing presigned URL locally..."
mkdir -p "$OUTDIR_LOCAL"
if curl -fsSL --fail -o "${OUTDIR_LOCAL}/sky.sh.download" "$PRESIGNED_URL"; then
  echo "[OK] Downloaded presigned URL locally into ${OUTDIR_LOCAL}/sky.sh.download"
else
  echo "[WARN] Local curl failed on presigned URL. Outputting verbose for debugging:"
  curl -vI "$PRESIGNED_URL" || true
  echo "Proceeding to attempt on-instance fetch regardless..."
fi

# 5) جهّز base64-encoded URL لتفادي مشاكل الاقتباسات أثناء إرسال SSM
echo "[%] Base64-encoding presigned URL for safe transport"
echo -n "$PRESIGNED_URL" | base64 -w0 > "$TMP_B64"
B64_CONTENT=$(cat "$TMP_B64")

# 6) أنشئ ملف JSON مع أوامر SSM (آمنة، تقوم بمحاولات متعددة)
cat > "$SSM_PARAMS_FILE" <<JSON
{
  "commands": [
    "set -euo pipefail",
    "echo '== SSM runner start ==' > /tmp/sky_ssm_runner.log",
    "echo 'Writing base64 to /tmp/url.b64' >> /tmp/sky_ssm_runner.log",
    "cat > /tmp/url.b64 <<'B64' && echo 'wrote b64' >> /tmp/sky_ssm_runner.log || true",
    "$B64_CONTENT",
    "B64",
    "base64 -d /tmp/url.b64 > /tmp/sky_presigned_url || true",
    "URL=\$(cat /tmp/sky_presigned_url || true)",
    "echo 'URL length:' \${#URL} >> /tmp/sky_ssm_runner.log",
    "echo 'Trying aws s3 cp fallback (if instance role allows)...' >> /tmp/sky_ssm_runner.log",
    "aws s3 cp s3://$BUCKET/$S3_KEY /tmp/sky.sh --region $REGION && echo 'got_via_s3cp' >> /tmp/sky_ssm_runner.log || true",
    "if [ -f /tmp/sky.sh ]; then echo 'S3 CP worked' >> /tmp/sky_ssm_runner.log; else echo 'S3 CP failed - trying curl presigned URL' >> /tmp/sky_ssm_runner.log; curl -fSL --retry 3 --max-time 60 \"\$URL\" -o /tmp/sky.sh 2>>/tmp/sky_ssm_runner.log || echo 'curl_presign_failed' >> /tmp/sky_ssm_runner.log; fi",
    "ls -l /tmp/sky.sh >> /tmp/sky_ssm_runner.log 2>&1 || true",
    "head -n 1 /tmp/sky.sh >> /tmp/sky_ssm_runner.log || true",
    "chmod +x /tmp/sky.sh || true",
    "echo 'Running sky.sh (dry-run) ...' >> /tmp/sky_ssm_runner.log",
    "timeout $CMD_TIMEOUT /tmp/sky.sh -t \"$TARGET\" --dry-run --outbase /tmp/sky_out || echo 'sky_exited_nonzero' >> /tmp/sky_ssm_runner.log || true",
    "echo 'Packing results...' >> /tmp/sky_ssm_runner.log",
    "tar czf /tmp/sky_out_bundle.tar.gz -C /tmp/sky_out . || echo 'no_results_to_package' >> /tmp/sky_ssm_runner.log",
    "echo 'Attempting upload results to s3' >> /tmp/sky_ssm_runner.log",
    "aws s3 cp /tmp/sky_out_bundle.tar.gz s3://$BUCKET/results/\$(hostname)_\$(date -u +%Y%m%dT%H%M%SZ).tar.gz --region $REGION || echo 'upload_failed' >> /tmp/sky_ssm_runner.log",
    "echo '== SSM runner end ==' >> /tmp/sky_ssm_runner.log",
    "cat /tmp/sky_ssm_runner.log"
  ]
}
JSON

echo "[%] SSM params file created: $SSM_PARAMS_FILE (commands count: $(jq '.commands|length' "$SSM_PARAMS_FILE"))"

# 7) إرسال الأمر عبر SSM
echo "[%] Sending SSM command..."
CMD_ID=$(aws ssm send-command \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters "file://$SSM_PARAMS_FILE" \
  --timeout-seconds  "$((CMD_TIMEOUT + 120))" \
  --query "Command.CommandId" --output text)

echo "[%] CommandId: $CMD_ID"
echo "[%] Polling for completion..."

# Polling helper
while true; do
  sleep 3
  STATUS=$(aws ssm get-command-invocation --region "$REGION" --instance-id "$INSTANCE_ID" --command-id "$CMD_ID" --query "Status" --output text 2>/dev/null || echo "Unknown")
  echo "[%] status: $STATUS"
  case "$STATUS" in
    Success|Failed|Cancelled|TimedOut|Completed)
      break
      ;;
    *)
      ;;
  esac
done

echo "[%] Fetching outputs..."
STDOUT=$(aws ssm get-command-invocation --region "$REGION" --instance-id "$INSTANCE_ID" --command-id "$CMD_ID" --query "StandardOutputContent" --output text 2>/dev/null || true)
STDERR=$(aws ssm get-command-invocation --region "$REGION" --instance-id "$INSTANCE_ID" --command-id "$CMD_ID" --query "StandardErrorContent" --output text 2>/dev/null || true)

echo "---- SSM STDOUT ----"
printf '%s\n' "$STDOUT"
echo "---- SSM STDERR ----"
printf '%s\n' "$STDERR"

echo "[%] Attempt to list results in s3://$BUCKET/results/"
aws s3 ls "s3://$BUCKET/results/" --region "$REGION" || echo "[!] Could not list results (no permission or empty)."

# cleanup
rm -f "$SSM_PARAMS_FILE" "$TMP_B64"
echo "[%] Done."
