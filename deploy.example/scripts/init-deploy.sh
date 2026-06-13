#!/usr/bin/env bash
# Create local deploy/ from templates (gitignored). Safe to run multiple times.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXAMPLE="${ROOT}/deploy.example"
TARGET="${ROOT}/deploy"

if [[ -d "${TARGET}" ]]; then
  echo "deploy/ already exists — not overwriting."
  echo "Edit files under deploy/ or remove deploy/ and re-run to start fresh."
  exit 0
fi

echo "Creating deploy/ from deploy.example/ ..."
cp -R "${EXAMPLE}" "${TARGET}"

# Drop the nested example readme path confusion — keep one README
cp "${EXAMPLE}/README.md" "${TARGET}/README.md"

if [[ ! -f "${TARGET}/config.env" ]]; then
  cp "${TARGET}/config.env.example" "${TARGET}/config.env"
fi
if [[ ! -f "${TARGET}/secrets.env" ]]; then
  cp "${TARGET}/secrets.env.example" "${TARGET}/secrets.env"
  chmod 600 "${TARGET}/secrets.env" 2>/dev/null || true
fi

chmod +x "${TARGET}/scripts/"*.sh 2>/dev/null || true

cat <<EOF

Created ${TARGET}/ (gitignored).

Next steps:
  1. Edit deploy/config.env   — AWS region, subnets, cluster name
  2. Edit deploy/secrets.env  — DATABASE_URL, MISTRAL_API_KEY (never commit)
  3. Read docs/deploy-ecs.md

EOF
