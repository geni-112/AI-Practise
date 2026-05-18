#!/bin/bash
# ChatBI Huawei Cloud Deploy Script (Linux/Mac)
# Usage: ./deploy.sh [plan|apply|destroy|output|ssh|status|logs]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"
CREDS_FILE="${HOME}/.claude/huawei-chatbi/credentials.env"
ACTION="${1:-help}"

if [[ ! -f "$CREDS_FILE" ]]; then
  echo "ERROR: Credentials not found at $CREDS_FILE"
  echo "Run /huawei-chatbi configure first"
  exit 1
fi

# Load credentials
source "$CREDS_FILE"

# Write terraform.tfvars
cat > "$TERRAFORM_DIR/terraform.tfvars" <<EOF
access_key    = "$HW_ACCESS_KEY"
secret_key    = "$HW_SECRET_KEY"
region        = "${HW_REGION:-la-south-2}"
maas_api_key  = "$MAAS_API_KEY"
maas_base_url = "${MAAS_BASE_URL:-https://api-ap-southeast-1.modelarts-maas.com/openai/v1}"
maas_model    = "${MAAS_MODEL:-glm-5.1}"
ecs_flavor    = "${ECS_FLAVOR:-c7.xlarge.4}"
dws_flavor    = "${DWS_FLAVOR:-dws.d2.xlarge.8}"
eip_bandwidth = ${EIP_BANDWIDTH:-5}
project_name  = "chatbi"
EOF

export CHECKPOINT_DISABLE=1

case "$ACTION" in
  plan)
    terraform -chdir="$TERRAFORM_DIR" init -upgrade
    terraform -chdir="$TERRAFORM_DIR" plan -out=tfplan
    ;;
  apply)
    if [[ ! -f "$TERRAFORM_DIR/tfplan" ]]; then
      terraform -chdir="$TERRAFORM_DIR" init -upgrade
      terraform -chdir="$TERRAFORM_DIR" plan -out=tfplan
    fi
    terraform -chdir="$TERRAFORM_DIR" apply tfplan
    echo "=== Outputs ==="
    terraform -chdir="$TERRAFORM_DIR" output
    ;;
  output)
    terraform -chdir="$TERRAFORM_DIR" output
    ;;
  status)
    terraform -chdir="$TERRAFORM_DIR" state list
    terraform -chdir="$TERRAFORM_DIR" output
    ECS_IP=$(terraform -chdir="$TERRAFORM_DIR" output -raw ecs_public_ip 2>/dev/null || echo "")
    if [[ -n "$ECS_IP" ]]; then
      echo "=== Health Check ==="
      curl -sf "http://$ECS_IP/api/health" || echo "Backend not yet reachable"
    fi
    ;;
  destroy)
    echo "WARNING: This will permanently destroy ALL resources including DWS data!"
    read -rp "Type 'yes' to confirm: " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
      echo "Aborted."
      exit 1
    fi
    terraform -chdir="$TERRAFORM_DIR" destroy -auto-approve
    ;;
  ssh)
    ECS_IP=$(terraform -chdir="$TERRAFORM_DIR" output -raw ecs_public_ip)
    KEY="$SCRIPT_DIR/../chatbi-keypair.pem"
    chmod 600 "$KEY"
    ssh -i "$KEY" ubuntu@"$ECS_IP"
    ;;
  logs)
    ECS_IP=$(terraform -chdir="$TERRAFORM_DIR" output -raw ecs_public_ip)
    KEY="$SCRIPT_DIR/../chatbi-keypair.pem"
    chmod 600 "$KEY"
    ssh -i "$KEY" ubuntu@"$ECS_IP" \
      "echo '=== Cloud-Init ===' && tail -100 /var/log/cloud-init-chatbi.log && \
       echo '=== Backend ===' && docker logs chatbi-backend --tail 50 && \
       echo '=== Superset ===' && docker logs chatbi-superset --tail 20"
    ;;
  *)
    echo "Usage: $0 [plan|apply|destroy|output|ssh|status|logs]"
    exit 1
    ;;
esac
