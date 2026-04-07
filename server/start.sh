#!/usr/bin/env bash
# start.sh — install deps and launch the server
# The server serves the frontend at / and handles WebSocket at /ws.
# Run tunnel.sh in a second terminal to get a public HTTPS URL.

set -euo pipefail

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "==> Starting server on 0.0.0.0:8000 ..."
echo "    Run tunnel.sh in a second terminal to expose it publicly."
echo ""

exec uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
