#!/usr/bin/env bash
# Store secrets in AWS Secrets Manager (optional helper). Reads deploy/secrets.env — never commit that file.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="${ROOT}/deploy"

# shellcheck source=/dev/null
source "${DEPLOY}/config.env"
# shellcheck source=/dev/null
source "${DEPLOY}/secrets.env"

: "${AWS_REGION:?}"
: "${DATABASE_URL:?Set DATABASE_URL in deploy/secrets.env}"

SECRET_PREFIX="${SECRET_PREFIX:-datapro}"

put_secret() {
  local name="$1"
  local value="$2"
  local full="${SECRET_PREFIX}/${name}"
  if aws secretsmanager describe-secret --secret-id "${full}" --region "${AWS_REGION}" >/dev/null 2>&1; then
    aws secretsmanager put-secret-value --secret-id "${full}" --secret-string "${value}" --region "${AWS_REGION}" >/dev/null
    echo "Updated secret ${full}"
  else
    aws secretsmanager create-secret --name "${full}" --secret-string "${value}" --region "${AWS_REGION}" >/dev/null
    echo "Created secret ${full}"
  fi
  aws secretsmanager describe-secret --secret-id "${full}" --region "${AWS_REGION}" --query ARN --output text
}

DB_ARN="$(put_secret "database-url" "${DATABASE_URL}")"
echo "SECRET_DATABASE_URL_ARN=${DB_ARN}"

if [[ -n "${MISTRAL_API_KEY:-}" ]]; then
  KEY_ARN="$(put_secret "mistral-api-key" "${MISTRAL_API_KEY}")"
  echo "SECRET_MISTRAL_API_KEY_ARN=${KEY_ARN}"
fi

cat <<EOF

Add the ARNs above to deploy/config.env, then run:
  ./deploy/scripts/render-task-defs.sh
  ./deploy/scripts/deploy-ecs.sh

EOF
