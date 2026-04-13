#!/usr/bin/env bash
# run.sh — start the inference server + Cloudflare tunnel in one command
# Usage: bash run.sh  (from inside the server/ directory)

set -euo pipefail

# Load .env if present — handles quoted and unquoted values, skips comments
if [ -f .env ]; then
  echo "==> Loading .env ..."
  while IFS= read -r line || [ -n "$line" ]; do
    # skip blank lines and comments
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    # strip leading/trailing whitespace then export
    line="${line#"${line%%[![:space:]]*}"}"
    export "$line"
  done < .env
fi

# ---------------------------------------------------------------------------
# Install Python deps
# ---------------------------------------------------------------------------
echo "==> Installing Python dependencies..."
pip install --upgrade pip -q
# llama-cpp-python must be built with CUDA support
CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=120" pip install llama-cpp-python --upgrade -q
pip install -r requirements.txt -q

# ---------------------------------------------------------------------------
# Install cloudflared if needed
# ---------------------------------------------------------------------------
if ! command -v cloudflared &>/dev/null; then
  echo "==> Installing cloudflared..."
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64)  PKG="cloudflared-linux-amd64.deb" ;;
    aarch64) PKG="cloudflared-linux-arm64.deb"  ;;
    *)       echo "ERROR: unsupported architecture: $ARCH"; exit 1 ;;
  esac
  TMP_DEB="/tmp/${PKG}"
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/${PKG}" -o "$TMP_DEB"
  dpkg -i "$TMP_DEB"
  rm -f "$TMP_DEB"
fi

# ---------------------------------------------------------------------------
# Start the server in the background
# ---------------------------------------------------------------------------
PORT="${PORT:-6006}"
echo ""
echo "==> Starting server on port $PORT ..."
uvicorn main:app --host 0.0.0.0 --port "$PORT" --log-level info &
SERVER_PID=$!

# Kill server when this script exits
trap 'echo ""; echo "==> Shutting down..."; kill $SERVER_PID 2>/dev/null; exit' INT TERM EXIT

# ---------------------------------------------------------------------------
# Wait for server to be ready
# ---------------------------------------------------------------------------
echo "==> Waiting for server to be ready..."
for i in $(seq 1 120); do
  if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    echo "==> Server is up."
    break
  fi
  if [ "$i" -eq 120 ]; then
    echo "ERROR: Server did not start within 120 s. Check logs above."
    exit 1
  fi
  sleep 1
done

# ---------------------------------------------------------------------------
# Start Cloudflare tunnel (foreground — URL appears in output below)
# ---------------------------------------------------------------------------
echo ""
echo "==> Starting Cloudflare tunnel — look for the trycloudflare.com URL:"
echo ""

cloudflared tunnel --url "http://localhost:${PORT}"
