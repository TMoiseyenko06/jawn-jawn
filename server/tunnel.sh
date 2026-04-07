#!/usr/bin/env bash
# tunnel.sh — expose the inference server (+ frontend) via Cloudflare Quick Tunnel
# No Cloudflare account needed. Run this in a second terminal after start.sh.

set -euo pipefail

TUNNEL_PORT="${TUNNEL_PORT:-8000}"
LOG_FILE="${LOG_FILE:-/tmp/cloudflared.log}"

# ---------------------------------------------------------------------------
# Install cloudflared if not present
# ---------------------------------------------------------------------------
if ! command -v cloudflared &>/dev/null; then
  echo "==> cloudflared not found — installing..."
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64)  PKG="cloudflared-linux-amd64.deb" ;;
    aarch64) PKG="cloudflared-linux-arm64.deb"  ;;
    *)
      echo "ERROR: unsupported architecture: $ARCH"
      exit 1
      ;;
  esac
  TMP_DEB="/tmp/${PKG}"
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/${PKG}" -o "$TMP_DEB"
  dpkg -i "$TMP_DEB"
  rm -f "$TMP_DEB"
  echo "==> cloudflared installed: $(cloudflared --version)"
else
  echo "==> cloudflared already installed: $(cloudflared --version)"
fi

# ---------------------------------------------------------------------------
# Wait for the server to be ready
# ---------------------------------------------------------------------------
echo "==> Waiting for server on port $TUNNEL_PORT..."
for i in $(seq 1 60); do
  if curl -sf "http://localhost:${TUNNEL_PORT}/health" >/dev/null 2>&1; then
    echo "==> Server is up."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "WARNING: server did not respond after 60 s — starting tunnel anyway"
  fi
  sleep 1
done

# ---------------------------------------------------------------------------
# Start the tunnel
# ---------------------------------------------------------------------------
echo "==> Starting Cloudflare Quick Tunnel → http://localhost:${TUNNEL_PORT} ..."
echo ""

cloudflared tunnel --url "http://localhost:${TUNNEL_PORT}" 2>&1 | tee "$LOG_FILE" | while IFS= read -r line; do
  echo "$line"
  if [[ "$line" == *"trycloudflare.com"* ]]; then
    URL=$(echo "$line" | grep -oP 'https://[^\s]+trycloudflare\.com')
    if [[ -n "$URL" ]]; then
      echo ""
      echo "============================================================"
      echo "  Tunnel is live!"
      echo ""
      echo "  Open in browser : $URL"
      echo "  WebSocket       : ${URL/https/wss}/ws"
      echo ""
      echo "  Share this URL — mic works because it's HTTPS."
      echo "============================================================"
      echo ""
    fi
  fi
done
