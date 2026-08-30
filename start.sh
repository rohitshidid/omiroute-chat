#!/usr/bin/env bash
set -e

# Target gateway address
TARGET_URL="${OMNIROUTE_BASE_URL:-http://127.0.0.1:20128/v1}"

# If target points to local container, auto-start the OmniRoute gateway daemon
if [[ "$TARGET_URL" == *"localhost"* || "$TARGET_URL" == *"127.0.0.1"* ]]; then
  if [ -f "./node_modules/.bin/omniroute" ]; then
    echo "🚀 Starting OmniRoute gateway from ./node_modules/.bin/omniroute..."
    ./node_modules/.bin/omniroute &
    sleep 5
  elif command -v omniroute >/dev/null 2>&1; then
    echo "🚀 Starting OmniRoute gateway via PATH..."
    omniroute &
    sleep 4
  elif command -v npx >/dev/null 2>&1; then
    echo "🚀 Starting OmniRoute gateway via npx on port 20128..."
    npx -y omniroute &
    sleep 5
  else
    echo "⚠️ Warning: Neither 'omniroute' nor 'npx' found. Gateway might need remote URL."
  fi
fi

PORT="${PORT:-8000}"
echo "🚀 Starting OmniRoute Web Server via Python on port $PORT..."
exec python3 -m uvicorn app:app --host 0.0.0.0 --port "$PORT"
