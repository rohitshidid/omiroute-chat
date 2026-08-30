#!/usr/bin/env bash
set -e

PORT="${PORT:-8000}"
echo "🚀 Starting OmniRoute Web Server via Python on port $PORT..."
exec python3 -m uvicorn app:app --host 0.0.0.0 --port "$PORT"
