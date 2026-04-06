#!/usr/bin/env bash
# start.sh — install deps and launch the inference server
# Run tunnel.sh in a second terminal to expose it via Cloudflare.

set -euo pipefail

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "==> Starting server on 0.0.0.0:8000 ..."
echo "    (Open a second terminal and run: bash tunnel.sh)"
echo ""

exec uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
