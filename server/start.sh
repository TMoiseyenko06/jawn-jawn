#!/usr/bin/env bash
# start.sh — install deps and launch the server
# Copy .env.example to .env and fill in your values before running.

set -euo pipefail

# Load .env if present
if [ -f .env ]; then
  echo "==> Loading .env ..."
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "==> Starting server on 0.0.0.0:6006 ..."
echo "    Run tunnel.sh in a second terminal to expose it publicly."
echo ""

exec uvicorn main:app --host 0.0.0.0 --port 6006 --log-level info
