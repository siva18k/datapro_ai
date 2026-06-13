#!/usr/bin/env bash
# Build DATA Pro images and push to ECR. Requires deploy/config.env and AWS CLI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="${ROOT}/deploy"

# shellcheck source=/dev/null
source "${DEPLOY}/config.env"

: "${AWS_REGION:?Set AWS_REGION in deploy/config.env}"
: "${AWS_ACCOUNT_ID:?Set AWS_ACCOUNT_ID in deploy/config.env}"
: "${ECR_REPO_API:?}"
: "${ECR_REPO_WEB:?}"
: "${ECR_REPO_MCP:?}"
: "${IMAGE_TAG:=latest}"

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Logging in to ECR ${ECR_REGISTRY} ..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

API_IMAGE="${ECR_REGISTRY}/${ECR_REPO_API}:${IMAGE_TAG}"
WEB_IMAGE="${ECR_REGISTRY}/${ECR_REPO_WEB}:${IMAGE_TAG}"
MCP_IMAGE="${ECR_REGISTRY}/${ECR_REPO_MCP}:${IMAGE_TAG}"

echo "Building API ..."
docker build --target api -t "${API_IMAGE}" "${ROOT}"

echo "Building web-ecs ..."
docker build --target web-ecs -t "${WEB_IMAGE}" "${ROOT}"

echo "Building MCP ..."
docker build --target mcp -t "${MCP_IMAGE}" "${ROOT}"

echo "Pushing images ..."
docker push "${API_IMAGE}"
docker push "${WEB_IMAGE}"
docker push "${MCP_IMAGE}"

echo "Done. Images:"
echo "  ${API_IMAGE}"
echo "  ${WEB_IMAGE}"
echo "  ${MCP_IMAGE}"
