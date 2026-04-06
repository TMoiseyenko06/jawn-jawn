#!/usr/bin/env bash
# tunnel.sh — start a free Cloudflare Quick Tunnel for the VPS frontend
# Gives you an HTTPS URL so the browser allows mic access (getUserMedia).
# No Cloudflare account needed.

set -euo pipefail

TUNNEL_PORT="${TUNNEL_PORT:-6000}"
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
# Wait for the file server to be ready
# ---------------------------------------------------------------------------
echo "==> Waiting for file server on port $TUNNEL_PORT..."
for i in $(seq 1 15); do
  if curl -sf "http://localhost:${TUNNEL_PORT}" >/dev/null 2>&1; then
    echo "==> Server is up."
    break
  fi
  if [ "$i" -eq 15 ]; then
    echo "WARNING: server did not respond on port $TUNNEL_PORT — starting tunnel anyway"
  fi
  sleep 1
done

# ---------------------------------------------------------------------------
# Start the tunnel, print the public HTTPS URL
# ---------------------------------------------------------------------------
echo "==> Starting Cloudflare Quick Tunnel → http://localhost:${TUNNEL_PORT} ..."
echo "    (URL changes each restart — mic will work over this HTTPS URL)"
echo ""

cloudflared tunnel --url "http://localhost:${TUNNEL_PORT}" 2>&1 | tee "$LOG_FILE" | while IFS= read -r line; do
  echo "$line"
  if [[ "$line" == *"trycloudflare.com"* ]]; then
    URL=$(echo "$line" | grep -oP 'https://[^\s]+trycloudflare\.com')
    if [[ -n "$URL" ]]; then
      echo ""
      echo "============================================================"
      echo "  Frontend tunnel is live!"
      echo ""
      echo "  Open in browser : $URL"
      echo ""
      echo "  Mic access works over this HTTPS URL."
      echo "============================================================"
      echo ""
    fi
  fi
done
