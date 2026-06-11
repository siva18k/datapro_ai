#!/usr/bin/env bash
# Start API + web dev servers. Run from the DATA Pro repo root.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi

echo "API: http://127.0.0.1:8080"
echo "Web: http://127.0.0.1:5173"
uvicorn api.main:app --reload --host 127.0.0.1 --port 8080 &
API_PID=$!
trap "kill $API_PID 2>/dev/null" EXIT

cd web
if [ ! -d node_modules ]; then
  npm install
fi
npm run dev
