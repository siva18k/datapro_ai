#!/usr/bin/env bash
# Wait for Postgres, then run catalog migrations.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Waiting for database..."
for i in $(seq 1 30); do
  if python -c "from db import connect; c, _ = connect(); c.close()" 2>/dev/null; then
    break
  fi
  sleep 2
done

python scripts/migrate.py
