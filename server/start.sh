#!/usr/bin/env bash
# start.sh — install deps and launch the inference server
# The server binds to 0.0.0.0:8000. Use the Vast.ai instance's direct IP:port
# as the WS_URL in frontend/index.html.

set -euo pipefail

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "==> Starting server on 0.0.0.0:8000 ..."
echo ""

exec uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
