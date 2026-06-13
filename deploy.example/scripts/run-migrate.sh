#!/usr/bin/env bash
# Run catalog migrations as a one-off Fargate task.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="${ROOT}/deploy"

"${DEPLOY}/scripts/render-task-defs.sh"
# shellcheck source=/dev/null
source "${DEPLOY}/config.env"

: "${ECS_CLUSTER:?}"
: "${ECS_SUBNETS:?}"
: "${ECS_SECURITY_GROUPS:?}"

NETWORK_JSON="$(python3 - <<PY
import json
print(json.dumps({
  "awsvpcConfiguration": {
    "subnets": $(python3 -c "import json; print(json.dumps('${ECS_SUBNETS}'.split(',')))"),
    "securityGroups": $(python3 -c "import json; print(json.dumps('${ECS_SECURITY_GROUPS}'.split(',')))"),
    "assignPublicIp": "${ECS_ASSIGN_PUBLIC_IP:-ENABLED}"
  }
}))
PY
)"

echo "Starting migration task on ${ECS_CLUSTER} ..."
TASK_ARN="$(aws ecs run-task \
  --cluster "${ECS_CLUSTER}" \
  --task-definition datapro-migrate \
  --launch-type "${ECS_LAUNCH_TYPE:-FARGATE}" \
  --network-configuration "${NETWORK_JSON}" \
  --region "${AWS_REGION}" \
  --query 'tasks[0].taskArn' \
  --output text)"

echo "Task: ${TASK_ARN}"
echo "Waiting for task to stop ..."
aws ecs wait tasks-stopped --cluster "${ECS_CLUSTER}" --tasks "${TASK_ARN}" --region "${AWS_REGION}"

EXIT_CODE="$(aws ecs describe-tasks \
  --cluster "${ECS_CLUSTER}" \
  --tasks "${TASK_ARN}" \
  --region "${AWS_REGION}" \
  --query 'tasks[0].containers[0].exitCode' \
  --output text)"

if [[ "${EXIT_CODE}" != "0" ]]; then
  echo "Migration failed with exit code ${EXIT_CODE}. Check CloudWatch logs: ${LOG_GROUP_PREFIX}/migrate"
  exit 1
fi

echo "Migration completed successfully."
