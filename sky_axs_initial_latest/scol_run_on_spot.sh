#!/usr/bin/env bash
# scol_run_on_spot.sh
# Smart Cloud Offloading Launcher (تصحيح/تثبيت)
# - يخلق/يستخدم موارد AWS Spot EC2 بطريقة آمنة ومُحكَمة
# - يضمن استخراج Security Group ID نظيفًا (بدون طباعة نص زائد)
# - يدعم استخدام sky.sh محليًا أو عبر S3 presigned URL
#
# Usage:
#   export AWS_REGION=eu-north-1
#   export INSTANCE_TYPE=t3.large
#   export TARGET=example.com
#   # Optional: export SKI_SH_S3_KEY="https://...presigned..."
#   ./scol_run_on_spot.sh

set -euo pipefail
IFS=$'\n\t'

# ---------- CONFIG (يمكنك تغيير القيم هنا) ----------
AWS_REGION="${AWS_REGION:-eu-north-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.large}"
TARGET="${TARGET:-example.com}"
KEY_NAME="${KEY_NAME:-sky-axs-key}"
SG_NAME="${SG_NAME:-sky-axs-sg-no-inbound}"
ROLE_NAME="${ROLE_NAME:-sky-axs-ec2-ssm-role}"
INSTANCE_PROFILE_NAME="${INSTANCE_PROFILE_NAME:-sky-axs-ec2-instance-profile}"
S3_BUCKET="${S3_BUCKET:-my-sky-axs-bucket-yourname}"
SKI_SH_S3_KEY="${SKI_SH_S3_KEY:-}"   # إذا أردت تحميل sky.sh من S3 ضع الرابط هنا (presigned URL)
CORE_LEGACY_LOCAL="./core/legacy/sky.sh"
AMI_LOOKUP_NAME="${AMI_LOOKUP_NAME:-amzn2-ami-hvm-2.0.*-x86_64-gp2}" # افتراضي Amazon Linux 2
COUNT=1
# ----------------------------------------------------

aws_cmd() { aws --region "${AWS_REGION}" "$@"; }

log(){ echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
err(){ echo "ERROR: $*" >&2; }

# sanitize function (تزيل أي أحرف زائدة/أسطر جديدة)
sanitize(){ printf '%s' "$1" | tr -d '\r\n' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'; }

# ensure aws cli available
if ! command -v aws >/dev/null 2>&1; then
  err "aws CLI not found. قم بتثبيت awscli وتهيئته (aws configure)."
  exit 2
fi

log "SCOL runner starting: region=${AWS_REGION} instance_type=${INSTANCE_TYPE} target=${TARGET}"

# check identity
IDENTITY=$(aws_cmd sts get-caller-identity --output text 2>/dev/null || true)
if [ -z "$IDENTITY" ]; then
  err "Unable to call STS; check AWS credentials/permissions."
  exit 2
fi
log "AWS identity: ${IDENTITY}"

# ensure S3 bucket exists or try to create (may fail on permissions; handle gracefully)
if aws_cmd s3api head-bucket --bucket "${S3_BUCKET}" >/dev/null 2>&1; then
  log "S3 bucket ${S3_BUCKET} exists"
else
  log "S3 bucket ${S3_BUCKET} not found — attempting to create (if permitted)..."
  if aws_cmd s3api create-bucket --bucket "${S3_BUCKET}" --create-bucket-configuration LocationConstraint="${AWS_REGION}" >/dev/null 2>&1; then
    log "Created bucket ${S3_BUCKET}"
  else
    log "Could not create bucket ${S3_BUCKET} (insufficient permissions?). Continuing — require SKI_SH_S3_KEY or local sky.sh."
  fi
fi

# verify IAM role / instance profile existence
ROLE_ID=$(aws_cmd iam get-role --role-name "${ROLE_NAME}" --query "Role.RoleName" --output text 2>/dev/null || true)
if [ -n "$ROLE_ID" ]; then
  log "IAM role ${ROLE_NAME} exists"
else
  log "IAM role ${ROLE_NAME} not present (ensure you created role with EC2/SSM permissions)."
fi

IPROF=$(aws_cmd iam get-instance-profile --instance-profile-name "${INSTANCE_PROFILE_NAME}" --query "InstanceProfile.InstanceProfileName" --output text 2>/dev/null || true)
if [ -n "$IPROF" ]; then
  log "Instance profile ${INSTANCE_PROFILE_NAME} exists"
else
  log "Instance profile ${INSTANCE_PROFILE_NAME} not present (ensure instance profile exists and has role attached)."
fi

# ensure keypair exists (create if allowed)
if aws_cmd ec2 describe-key-pairs --key-names "${KEY_NAME}" --query "KeyPairs[0].KeyName" --output text >/dev/null 2>&1; then
  log "KeyPair ${KEY_NAME} exists"
else
  log "KeyPair ${KEY_NAME} not found — attempting to create key-pair (will write ${KEY_NAME}.pem to cwd if allowed)"
  if aws_cmd ec2 create-key-pair --key-name "${KEY_NAME}" --query "KeyMaterial" --output text > "${KEY_NAME}.pem" 2>/dev/null; then
    chmod 600 "${KEY_NAME}.pem"
    log "Keypair created and saved to ./${KEY_NAME}.pem"
  else
    log "Could not create keypair (permissions?). Continuing — if you need SSH you'll need to provide a key."
  fi
fi

# --- SECURITY GROUP: find or create, but ensure extraction returns only the ID ---
SG_ID=$(aws_cmd ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" --query "SecurityGroups[0].GroupId" --output text 2>/dev/null || true)
SG_ID=$(sanitize "$SG_ID")
if [ -z "$SG_ID" ] || [ "$SG_ID" = "None" ]; then
  log "Security group ${SG_NAME} not found — creating in default VPC..."
  VPC_ID=$(aws_cmd ec2 describe-vpcs --query "Vpcs[0].VpcId" --output text 2>/dev/null || true)
  VPC_ID=$(sanitize "$VPC_ID")
  if [ -z "$VPC_ID" ] || [ "$VPC_ID" = "None" ]; then
    err "Unable to determine default VPC. Cannot create security group automatically."
    exit 3
  fi
  # create SG and capture only GroupId
  SG_ID_RAW=$(aws_cmd ec2 create-security-group --group-name "${SG_NAME}" --description "no inbound for sky-axs" --vpc-id "${VPC_ID}" --query "GroupId" --output text 2>/dev/null || true)
  SG_ID=$(sanitize "$SG_ID_RAW")
  if [ -n "$SG_ID" ] && [ "$SG_ID" != "None" ]; then
    log "Created SG: ${SG_ID}"
    # ensure no inbound rules (explicitly revoke any)
    aws_cmd ec2 revoke-security-group-ingress --group-id "${SG_ID}" --ip-permissions "$(printf '[]')" 2>/dev/null || true
  else
    err "Failed to create security group (permission issue?)."
    exit 4
  fi
else
  log "Security group ${SG_NAME} exists: ${SG_ID}"
fi

# ensure SG_ID is strictly like 'sg-...'
if ! printf '%s' "${SG_ID}" | grep -E -q '^sg-[0-9a-fA-F]+'; then
  err "Security Group ID seems invalid: '${SG_ID}'"
  exit 5
fi

# --- determine AMI (simple lookup for Amazon Linux 2) ---
log "Querying latest AMI..."
AMI_ID=$(aws_cmd ec2 describe-images --owners amazon --filters "Name=name,Values=${AMI_LOOKUP_NAME}" "Name=state,Values=available" --query "Images | sort_by(@,&CreationDate) | [-1].ImageId" --output text 2>/dev/null || true)
AMI_ID=$(sanitize "$AMI_ID")
if [ -z "$AMI_ID" ] || [ "$AMI_ID" = "None" ]; then
  err "Failed to find AMI automatically. Please set AMI_ID manually."
  exit 6
fi
log "Using AMI: ${AMI_ID}"

# --- ensure we have a sky.sh target: local or via presigned URL ---
if [ -f "${CORE_LEGACY_LOCAL}" ]; then
  log "Found local ${CORE_LEGACY_LOCAL} — will bundle/upload it to S3 bucket if needed."
  SKY_SH_S3_KEY=""
  if aws_cmd s3api head-bucket --bucket "${S3_BUCKET}" >/dev/null 2>&1; then
    UPLOAD_KEY="core/legacy/sky.sh"
    log "Uploading local sky.sh to s3://${S3_BUCKET}/${UPLOAD_KEY} (if permitted)..."
    if aws_cmd s3 cp "${CORE_LEGACY_LOCAL}" "s3://${S3_BUCKET}/${UPLOAD_KEY}" >/dev/null 2>&1; then
      # create presigned URL for retrieval by instance/user-data
      PRESIGNED=$(aws_cmd s3 presign "s3://${S3_BUCKET}/${UPLOAD_KEY}" --expires-in 3600 2>/dev/null || true)
      PRESIGNED=$(sanitize "$PRESIGNED")
      if [ -n "$PRESIGNED" ]; then
        SKY_SH_S3_KEY="$PRESIGNED"
        log "Uploaded and created presigned URL (valid 1h)."
      else
        log "Uploaded but failed to presign (instance will need network access and permission to get)."
      fi
    else
      log "Upload failed (permissions?). We will attempt to rely on local file packaging later."
    fi
  else
    log "S3 bucket not available — will embed script via user-data if small enough (or fail)."
  fi
elif [ -n "${SKI_SH_S3_KEY}" ]; then
  SKY_SH_S3_KEY=$(sanitize "${SKI_SH_S3_KEY}")
  log "Using provided SKI_SH_S3_KEY (presigned or public URL)."
else
  err "No sky.sh found locally and no SKI_SH_S3_KEY provided. Provide one or place ${CORE_LEGACY_LOCAL}."
  exit 7
fi

# --- build user-data script to download and run sky.sh on the spot instance using SSM-friendly approach ---
USER_DATA=$(cat <<'UD'
#!/bin/bash
set -e
# download sky.sh if SKI_SH_URL provided
SKI_SH_URL='__SKI_SH_URL__'
if [ -n "$SKI_SH_URL" ]; then
  /usr/bin/curl -fsSL "$SKI_SH_URL" -o /tmp/sky.sh || /usr/bin/wget -qO /tmp/sky.sh "$SKI_SH_URL"
  chmod +x /tmp/sky.sh || true
fi
# signal ready (cloud-init or SSM can be used further)
echo "sky.sh downloaded: $(stat -c '%s %n' /tmp/sky.sh 2>/dev/null || true)" > /tmp/sky_status.txt
UD
)

USER_DATA="${USER_DATA//__SKI_SH_URL__/${SKY_SH_S3_KEY:-}}"

# Sanitize USER_DATA (no CRLF)
USER_DATA=$(printf '%s' "$USER_DATA" | tr -d '\r')

# --- Launch Spot Instance request (simple fallback to on-demand if spot fails) ---
log "Requesting spot instance (or on-demand fallback) with SG ${SG_ID} ..."

# Build CLI run-instances param list safely
RUN_CMD=(aws_cmd ec2 run-instances
  --image-id "${AMI_ID}"
  --count "${COUNT}"
  --instance-type "${INSTANCE_TYPE}"
  --key-name "${KEY_NAME}"
  --security-group-ids "${SG_ID}"
  --user-data "${USER_DATA}"
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=sky-axs-spot},{Key=project,Value=sky-axs}]"
)

# If instance profile exists, attach it
if [ -n "$IPROF" ]; then
  RUN_CMD+=(--iam-instance-profile "Name=${INSTANCE_PROFILE_NAME}")
fi

# Execute run-instances (wrap with AWS CLI)
# We place call in subshell to capture output safely
INSTANCE_JSON=$("${RUN_CMD[@]}" 2>/dev/null || true)
if [ -z "${INSTANCE_JSON}" ]; then
  err "run-instances failed (attempting Spot request approach)..."
  # Try Spot Instance Request flow (simpler): create spot instance (one-shot)
  SIR_JSON=$(aws_cmd ec2 request-spot-instances --instance-count 1 --launch-specification "{\"ImageId\":\"${AMI_ID}\",\"InstanceType\":\"${INSTANCE_TYPE}\",\"KeyName\":\"${KEY_NAME}\",\"SecurityGroupIds\":[\"${SG_ID}\"] $( [ -n "$IPROF" ] && echo ",\"IamInstanceProfile\":{\"Name\":\"${INSTANCE_PROFILE_NAME}\"}" || echo "" ) }" --type "one-time" 2>/dev/null || true)
  SIR_ID=$(printf '%s' "$SIR_JSON" | jq -r '.SpotInstanceRequests[0].SpotInstanceRequestId' 2>/dev/null || true)
  if [ -n "$SIR_ID" ] && [ "$SIR_ID" != "null" ]; then
    log "Spot Instance Request created: ${SIR_ID}. Waiting for fulfillment..."
    # wait for instance id
    INST_ID=""
    for i in $(seq 1 20); do
      sleep 3
      INST_ID=$(aws_cmd ec2 describe-spot-instance-requests --spot-instance-request-ids "${SIR_ID}" --query "SpotInstanceRequests[0].InstanceId" --output text 2>/dev/null || true)
      INST_ID=$(sanitize "$INST_ID")
      if [ -n "$INST_ID" ] && [ "$INST_ID" != "None" ] && [ "$INST_ID" != "null" ]; then break; fi
    done
    if [ -n "$INST_ID" ]; then
      log "Spot fulfilled: instance ${INST_ID}"
      PUBIP=$(aws_cmd ec2 describe-instances --instance-ids "${INST_ID}" --query "Reservations[0].Instances[0].PublicIpAddress" --output text 2>/dev/null || true)
      PUBIP=$(sanitize "$PUBIP")
      log "Instance public IP: ${PUBIP}"
      echo "Spot instance created: ${INST_ID}"
      echo "${INST_ID}"
      exit 0
    else
      err "Spot request not fulfilled within wait window."
      exit 8
    fi
  else
    err "Spot request creation failed."
    exit 9
  fi
else
  # parse instance id(s)
  FIRST_ID=$(printf '%s' "$INSTANCE_JSON" | jq -r '.Instances[0].InstanceId' 2>/dev/null || true)
  FIRST_ID=$(sanitize "$FIRST_ID")
  PUBIP=$(printf '%s' "$INSTANCE_JSON" | jq -r '.Instances[0].PublicIpAddress' 2>/dev/null || true)
  PUBIP=$(sanitize "$PUBIP")
  log "Instance launched: ${FIRST_ID} public-ip=${PUBIP:-(none)}"
  echo "${FIRST_ID}"
  exit 0
fi

