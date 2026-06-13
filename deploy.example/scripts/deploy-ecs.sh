#!/usr/bin/env bash
# Register task definitions and create/update ECS services.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="${ROOT}/deploy"

"${DEPLOY}/scripts/render-task-defs.sh"

# shellcheck source=/dev/null
source "${DEPLOY}/config.env"

: "${ECS_CLUSTER:?}"
: "${ECS_SUBNETS:?}"
: "${ECS_SECURITY_GROUPS:?}"

IFS=',' read -ra SUBNET_ARRAY <<< "${ECS_SUBNETS}"
IFS=',' read -ra SG_ARRAY <<< "${ECS_SECURITY_GROUPS}"

register() {
  local file="$1"
  echo "Registering ${file} ..."
  aws ecs register-task-definition --cli-input-json "file://${file}" --region "${AWS_REGION}"
}

register "${DEPLOY}/ecs/task-def-api.json"
register "${DEPLOY}/ecs/task-def-web.json"
register "${DEPLOY}/ecs/task-def-mcp.json"
register "${DEPLOY}/ecs/task-def-migrate.json"

network_config() {
  python3 - <<PY
import json
print(json.dumps({
  "awsvpcConfiguration": {
    "subnets": $(python3 -c "import json; print(json.dumps('${ECS_SUBNETS}'.split(',')))"),
    "securityGroups": $(python3 -c "import json; print(json.dumps('${ECS_SECURITY_GROUPS}'.split(',')))"),
    "assignPublicIp": "${ECS_ASSIGN_PUBLIC_IP:-ENABLED}"
  }
}))
PY
}

upsert_service() {
  local name="$1"
  local task_family="$2"
  local count="$3"
  local container_name="$4"
  local port="${5:-}"

  local status
  status="$(aws ecs describe-services \
    --cluster "${ECS_CLUSTER}" \
    --services "${name}" \
    --region "${AWS_REGION}" \
    --query 'services[0].status' \
    --output text 2>/dev/null || echo "MISSING")"

  if [[ "${status}" == "ACTIVE" ]]; then
    echo "Updating service ${name} ..."
    aws ecs update-service \
      --cluster "${ECS_CLUSTER}" \
      --service "${name}" \
      --task-definition "${task_family}" \
      --desired-count "${count}" \
      --force-new-deployment \
      --region "${AWS_REGION}" >/dev/null
  else
    echo "Creating service ${name} ..."
    local -a extra=()
    if [[ -n "${port}" && -n "${TARGET_GROUP_ARN:-}" ]]; then
      extra+=(--load-balancers "targetGroupArn=${TARGET_GROUP_ARN},containerName=${container_name},containerPort=${port}")
    fi
    aws ecs create-service \
      --cluster "${ECS_CLUSTER}" \
      --service-name "${name}" \
      --task-definition "${task_family}" \
      --desired-count "${count}" \
      --launch-type "${ECS_LAUNCH_TYPE:-FARGATE}" \
      --network-configuration "$(network_config)" \
      "${extra[@]}" \
      --region "${AWS_REGION}" >/dev/null
  fi
}

TARGET_GROUP_ARN="${WEB_TARGET_GROUP_ARN:-}"
upsert_service "${WEB_SERVICE_NAME:-web}" "datapro-web" "${DESIRED_COUNT_WEB:-1}" "web" "80"

TARGET_GROUP_ARN="${API_TARGET_GROUP_ARN:-}"
upsert_service "${API_SERVICE_NAME:-api}" "datapro-api" "${DESIRED_COUNT_API:-1}" "api" "8080"

if [[ "${DESIRED_COUNT_MCP:-0}" -gt 0 ]]; then
  TARGET_GROUP_ARN=""
  upsert_service "${MCP_SERVICE_NAME:-mcp}" "datapro-mcp" "${DESIRED_COUNT_MCP}" "mcp" "8000"
fi

cat <<EOF

ECS services updated on cluster ${ECS_CLUSTER}.

Notes:
  - Internal DNS (Cloud Map) for API/MCP must match API_UPSTREAM_HOST in config.env
  - Attach ALB target groups via WEB_TARGET_GROUP_ARN / API_TARGET_GROUP_ARN when ready
  - Run migrations: ./deploy/scripts/run-migrate.sh

EOF
