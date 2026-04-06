#!/usr/bin/env bash
# serve.sh — install deps and start the VPS proxy server
# Set VAST_WS_URL to your Vast.ai instance's WebSocket address before running.
#
# Usage:
#   VAST_WS_URL="ws://123.45.67.89:12345/ws" bash serve.sh

set -euo pipefail

if [[ -z "${VAST_WS_URL:-}" ]]; then
  echo "ERROR: VAST_WS_URL is not set."
  echo ""
  echo "Find your Vast.ai instance IP and mapped port on the instance detail page, then run:"
  echo "  VAST_WS_URL=\"ws://<ip>:<port>/ws\" bash serve.sh"
  exit 1
fi

echo "==> Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "==> Starting VPS proxy server on 0.0.0.0:6000 ..."
echo "    Proxying WebSocket to: $VAST_WS_URL"
echo "    Run tunnel.sh in a second terminal to get the public HTTPS URL."
echo ""

exec uvicorn main:app --host 0.0.0.0 --port 6000 --log-level info
