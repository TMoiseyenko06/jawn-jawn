#!/usr/bin/env bash
# tunnel.sh — expose the server via Cloudflare Quick Tunnel
# No Cloudflare account needed. The public HTTPS URL will appear in the output below.

set -euo pipefail

TUNNEL_PORT="${TUNNEL_PORT:-6006}"

# ---------------------------------------------------------------------------
# Install cloudflared if not present
# ---------------------------------------------------------------------------
if ! command -v cloudflared &>/dev/null; then
  echo "==> cloudflared not found — installing..."
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
  echo "==> cloudflared installed: $(cloudflared --version)"
fi

# ---------------------------------------------------------------------------
# Wait for the server
# ---------------------------------------------------------------------------
echo "==> Waiting for server on port $TUNNEL_PORT..."
for i in $(seq 1 60); do
  if curl -sf "http://localhost:${TUNNEL_PORT}/health" >/dev/null 2>&1; then
    echo "==> Server is up."
    break
  fi
  [ "$i" -eq 60 ] && echo "WARNING: server not responding — starting tunnel anyway"
  sleep 1
done

# ---------------------------------------------------------------------------
# Start tunnel — the trycloudflare.com URL will appear in the output below
# ---------------------------------------------------------------------------
echo ""
echo "==> Tunnel starting — look for the trycloudflare.com URL below:"
echo ""

exec cloudflared tunnel --url "http://localhost:${TUNNEL_PORT}"
