#!/usr/bin/env bash
# tunnel.sh — start a free Cloudflare Quick Tunnel for the inference server
# No Cloudflare account needed. Prints the WSS URL to use in frontend/index.html.

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
  DOWNLOAD_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/${PKG}"
  TMP_DEB="/tmp/${PKG}"
  echo "==> Downloading $DOWNLOAD_URL"
  curl -fsSL "$DOWNLOAD_URL" -o "$TMP_DEB"
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
for i in $(seq 1 30); do
  if curl -sf "http://localhost:${TUNNEL_PORT}/health" >/dev/null 2>&1; then
    echo "==> Server is up."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "WARNING: server did not respond on port $TUNNEL_PORT after 30 s — starting tunnel anyway"
  fi
  sleep 1
done

# ---------------------------------------------------------------------------
# Start the tunnel, capture the public URL
# ---------------------------------------------------------------------------
echo "==> Starting Cloudflare Quick Tunnel → http://localhost:${TUNNEL_PORT} ..."
echo "    (URL changes each restart; use a named tunnel for a stable URL)"
echo ""

# Run cloudflared, tee to log file, and print the WSS URL as soon as it appears
cloudflared tunnel --url "http://localhost:${TUNNEL_PORT}" 2>&1 | tee "$LOG_FILE" | while IFS= read -r line; do
  echo "$line"
  # cloudflared prints the public URL in a line containing trycloudflare.com
  if [[ "$line" == *"trycloudflare.com"* ]]; then
    # Extract just the https URL
    URL=$(echo "$line" | grep -oP 'https://[^\s]+trycloudflare\.com')
    if [[ -n "$URL" ]]; then
      WSS_URL="${URL/https:\/\//wss://}/ws"
      echo ""
      echo "============================================================"
      echo "  Tunnel is live!"
      echo ""
      echo "  Public HTTPS : $URL"
      echo "  WebSocket    : $WSS_URL"
      echo ""
      echo "  Paste this into frontend/index.html:"
      echo "    const WS_URL = \"$WSS_URL\";"
      echo "============================================================"
      echo ""
    fi
  fi
done
