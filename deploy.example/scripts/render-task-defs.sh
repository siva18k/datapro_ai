#!/usr/bin/env bash
# Substitute placeholders in ECS task definition templates → deploy/ecs/*.json
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="${ROOT}/deploy"

# shellcheck source=/dev/null
source "${DEPLOY}/config.env"
# shellcheck source=/dev/null
source "${DEPLOY}/secrets.env" 2>/dev/null || true

: "${AWS_REGION:?}"
: "${AWS_ACCOUNT_ID:?}"
: "${IMAGE_TAG:=latest}"

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_API="${ECR_REGISTRY}/${ECR_REPO_API}:${IMAGE_TAG}"
IMAGE_WEB="${ECR_REGISTRY}/${ECR_REPO_WEB}:${IMAGE_TAG}"
IMAGE_MCP="${ECR_REGISTRY}/${ECR_REPO_MCP}:${IMAGE_TAG}"

# Set these in deploy/config.env after creating secrets in AWS Secrets Manager
: "${SECRET_DATABASE_URL_ARN:?Set SECRET_DATABASE_URL_ARN in deploy/config.env}"
SECRET_MISTRAL_API_KEY_ARN="${SECRET_MISTRAL_API_KEY_ARN:-}"

LOG_GROUP_API="${LOG_GROUP_PREFIX}/api"
LOG_GROUP_WEB="${LOG_GROUP_PREFIX}/web"
LOG_GROUP_MCP="${LOG_GROUP_PREFIX}/mcp"
LOG_GROUP_MIGRATE="${LOG_GROUP_PREFIX}/migrate"

mkdir -p "${DEPLOY}/ecs"

render() {
  local src="$1"
  local dst="$2"
  sed \
    -e "s|__AWS_ACCOUNT_ID__|${AWS_ACCOUNT_ID}|g" \
    -e "s|__AWS_REGION__|${AWS_REGION}|g" \
    -e "s|__IMAGE_API__|${IMAGE_API}|g" \
    -e "s|__IMAGE_WEB__|${IMAGE_WEB}|g" \
    -e "s|__IMAGE_MCP__|${IMAGE_MCP}|g" \
    -e "s|__TASK_CPU__|${TASK_CPU}|g" \
    -e "s|__TASK_MEMORY__|${TASK_MEMORY}|g" \
    -e "s|__MCP_TASK_CPU__|${MCP_TASK_CPU}|g" \
    -e "s|__MCP_TASK_MEMORY__|${MCP_TASK_MEMORY}|g" \
    -e "s|__DB_SCHEMA__|${DB_SCHEMA}|g" \
    -e "s|__EMBEDDING_MODEL__|${EMBEDDING_MODEL}|g" \
    -e "s|__DEFAULT_LLM_BACKEND__|${DEFAULT_LLM_BACKEND}|g" \
    -e "s|__PGSSLMODE__|${PGSSLMODE}|g" \
    -e "s|__MCP_URL__|${MCP_URL:-http://mcp:8000/mcp}|g" \
    -e "s|__API_UPSTREAM_HOST__|${API_UPSTREAM_HOST}|g" \
    -e "s|__SECRET_DATABASE_URL_ARN__|${SECRET_DATABASE_URL_ARN}|g" \
    -e "s|__SECRET_MISTRAL_API_KEY_ARN__|${SECRET_MISTRAL_API_KEY_ARN}|g" \
    -e "s|__LOG_GROUP_API__|${LOG_GROUP_API}|g" \
    -e "s|__LOG_GROUP_WEB__|${LOG_GROUP_WEB}|g" \
    -e "s|__LOG_GROUP_MCP__|${LOG_GROUP_MCP}|g" \
    -e "s|__LOG_GROUP_MIGRATE__|${LOG_GROUP_MIGRATE}|g" \
    "${src}" > "${dst}"
  echo "Wrote ${dst}"
}

render "${DEPLOY}/ecs/task-def-api.json.example" "${DEPLOY}/ecs/task-def-api.json"
render "${DEPLOY}/ecs/task-def-web.json.example" "${DEPLOY}/ecs/task-def-web.json"
render "${DEPLOY}/ecs/task-def-mcp.json.example" "${DEPLOY}/ecs/task-def-mcp.json"
render "${DEPLOY}/ecs/task-def-migrate.json.example" "${DEPLOY}/ecs/task-def-migrate.json"

echo "Task definitions rendered under deploy/ecs/"
