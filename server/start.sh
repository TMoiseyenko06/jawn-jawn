#!/usr/bin/env bash
# start.sh — install deps and launch the server
# Copy .env.example to .env and fill in your values before running.

set -euo pipefail

# Load .env if present — handles quoted and unquoted values, skips comments
if [ -f .env ]; then
  echo "==> Loading .env ..."
  while IFS= read -r line || [ -n "$line" ]; do
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    line="${line#"${line%%[![:space:]]*}"}"
    export "$line"
  done < .env
fi

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "==> Starting server on 0.0.0.0:6006 ..."
echo "    Run tunnel.sh in a second terminal to expose it publicly."
echo ""

exec uvicorn main:app --host 0.0.0.0 --port 6006 --log-level info
