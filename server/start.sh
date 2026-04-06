#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Starting server on 0.0.0.0:8000 ..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
