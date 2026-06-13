#!/usr/bin/env bash
# One-time (or occasional) AWS resource bootstrap: ECR repos + CloudWatch log groups.
# Review and edit deploy/config.env before running. Does not create RDS or ECS cluster.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="${ROOT}/deploy"
# shellcheck source=/dev/null
source "${DEPLOY}/config.env"

: "${AWS_REGION:?}"
: "${ECR_REPO_API:?}"
: "${ECR_REPO_WEB:?}"
: "${ECR_REPO_MCP:?}"
: "${LOG_GROUP_PREFIX:?/ecs/datapro}"

create_repo() {
  local name="$1"
  if aws ecr describe-repositories --repository-names "${name}" --region "${AWS_REGION}" >/dev/null 2>&1; then
    echo "ECR repo exists: ${name}"
  else
    echo "Creating ECR repo: ${name}"
    aws ecr create-repository --repository-name "${name}" --region "${AWS_REGION}" \
      --image-scanning-configuration scanOnPush=true
  fi
}

create_repo "${ECR_REPO_API}"
create_repo "${ECR_REPO_WEB}"
create_repo "${ECR_REPO_MCP}"

for svc in api web mcp migrate; do
  lg="${LOG_GROUP_PREFIX}/${svc}"
  if aws logs describe-log-groups --log-group-name-prefix "${lg}" --region "${AWS_REGION}" \
    | grep -q "\"logGroupName\": \"${lg}\""; then
    echo "Log group exists: ${lg}"
  else
    echo "Creating log group: ${lg}"
    aws logs create-log-group --log-group-name "${lg}" --region "${AWS_REGION}" || true
  fi
done

cat <<EOF

ECR and log groups ready.

You still need (outside this script):
  - ECS cluster: ${ECS_CLUSTER:-datapro}
  - RDS Postgres with pgvector (see docs/deploy-ecs.md)
  - VPC subnets + security groups in deploy/config.env
  - Optional: ALB + target groups for public web/API access

Create cluster example:
  aws ecs create-cluster --cluster-name ${ECS_CLUSTER:-datapro} --region ${AWS_REGION}

EOF
