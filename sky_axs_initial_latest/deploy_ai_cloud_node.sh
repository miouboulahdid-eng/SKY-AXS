#!/usr/bin/env bash
# =====================================================
# SKY-AXS :: AI Cloud Node Bootstrap (temporary version)
# =====================================================
# النسخة المؤقتة الذكية - v2.0
# تقوم بالتحقق من instance جاهزة أو إطلاق واحدة جديدة
# مع إعادة المحاولة التلقائية وتفادي التكلفة.
# =====================================================

set -euo pipefail
IFS=$'\n\t'

REGION="eu-north-1"
BUCKET="my-sky-axs-bucket-yourname"
ROLE_NAME="sky-axs-ec2-ssm-role"
INSTANCE_TYPE="t3.large"
AMI_ID="ami-0aadcf405dcb7d041"
KEY_NAME="sky-axs-key"
SEC_GRP_NAME="sky-axs-sg-no-inbound"
TAG_PROJECT="sky-axs"
AI_TAG="sky-axs-ai-spot"
AUTO_TERMINATE="true"

log() {
    echo "[${1:-INFO}] $(date -u '+%Y-%m-%dT%H:%M:%SZ') ${2:-}"
}

# =====================================================
# تحقق من IAM
# =====================================================
log INFO "التحقق من هوية AWS..."
aws sts get-caller-identity --output text >/dev/null
log OK "تم التحقق من هوية AWS"

# =====================================================
# البحث عن instance AI نشطة
# =====================================================
EXISTING_INSTANCE=$(aws ec2 describe-instances \
  --region "$REGION" \
  --filters "Name=tag:Name,Values=${AI_TAG}" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[0].InstanceId" \
  --output text 2>/dev/null || true)

if [[ "$EXISTING_INSTANCE" != "None" && -n "$EXISTING_INSTANCE" ]]; then
    INSTANCE_ID="$EXISTING_INSTANCE"
    log INFO "تم العثور على instance نشطة: $INSTANCE_ID"
else
    log INFO "لم يتم العثور على instance نشطة، سيتم إنشاء واحدة جديدة..."
    SG_ID=$(aws ec2 describe-security-groups \
        --region "$REGION" \
        --filters "Name=group-name,Values=$SEC_GRP_NAME" \
        --query "SecurityGroups[0].GroupId" --output text)

    INSTANCE_ID=$(aws ec2 run-instances \
        --region "$REGION" \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --iam-instance-profile Name="$ROLE_NAME" \
        --security-group-ids "$SG_ID" \
        --instance-market-options "MarketType=spot" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$AI_TAG},{Key=project,Value=$TAG_PROJECT}]" \
        --query "Instances[0].InstanceId" \
        --output text)
    log OK "تم إطلاق instance جديدة: $INSTANCE_ID"
fi

# =====================================================
# انتظار SSM agent
# =====================================================
log INFO "انتظار تسجيل الـ instance في SSM..."
for i in {1..15}; do
    STATE=$(aws ssm describe-instance-information \
      --region "$REGION" \
      --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
      --query "InstanceInformationList[0].PingStatus" \
      --output text 2>/dev/null || echo "pending")
    [[ "$STATE" == "Online" ]] && break
    log INFO "في الانتظار... (الحالة: $STATE)"
    sleep 10
done

if [[ "$STATE" != "Online" ]]; then
    log ERR "الـ Instance لم تُسجّل في SSM بعد. إيقاف."
    exit 1
fi
log OK "SSM Agent جاهز للعمل."

# =====================================================
# رفع ملفات الذكاء الاصطناعي المؤقتة
# =====================================================
log INFO "رفع ملفات ai_engine والـ sky.sh..."
tar czf /tmp/ai_engine.tar.gz -C ./core/legacy sky.sh || true
aws s3 cp /tmp/ai_engine.tar.gz "s3://$BUCKET/ai_engine/ai_engine.tar.gz" --region "$REGION" >/dev/null
aws s3 cp ./core/legacy/sky.sh "s3://$BUCKET/core/legacy/sky.sh" --region "$REGION" >/dev/null
log OK "تم رفع الملفات بنجاح."

# =====================================================
# تنفيذ مهمة الذكاء الاصطناعي عبر SSM
# =====================================================
log INFO "تشغيل أمر SSM..."
COMMAND_ID=$(aws ssm send-command \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "Run temporary AI bootstrap + dry-run" \
  --parameters 'commands=["echo == AI node bootstrap start ==","mkdir -p /tmp/ai_node","aws s3 cp s3://'"$BUCKET"'/core/legacy/sky.sh /tmp/ai_node/sky.sh","chmod +x /tmp/ai_node/sky.sh","timeout 300 /tmp/ai_node/sky.sh -t example.com --dry-run || true","echo == AI node bootstrap end =="]' \
  --query "Command.CommandId" \
  --output text)

log OK "SSM CommandId: $COMMAND_ID"

# =====================================================
# مراقبة تنفيذ SSM
# =====================================================
for i in {1..20}; do
    STATUS=$(aws ssm list-commands \
      --region "$REGION" \
      --command-id "$COMMAND_ID" \
      --query "Commands[0].Status" --output text)
    [[ "$STATUS" == "Success" || "$STATUS" == "Failed" ]] && break
    log INFO "SSM قيد التنفيذ ($STATUS)..."
    sleep 10
done

log INFO "SSM Status: $STATUS"
aws ssm get-command-invocation \
  --region "$REGION" \
  --instance-id "$INSTANCE_ID" \
  --command-id "$COMMAND_ID" \
  --query "StandardOutputContent" --output text || true

# =====================================================
# عرض النتائج + إنهاء التكلفة
# =====================================================
log INFO "محاولة استعراض النتائج من S3..."
aws s3 ls "s3://$BUCKET/results/" --region "$REGION" || echo "لا توجد نتائج بعد."

if [[ "$AUTO_TERMINATE" == "true" ]]; then
    log INFO "Auto-terminate مفعّل، سيتم إنهاء instance لتفادي التكاليف."
    aws ec2 terminate-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null
else
    log INFO "ترك الـ instance تعمل (AUTO_TERMINATE=false)."
fi

log OK "تم تنفيذ جميع المهام بنجاح."

