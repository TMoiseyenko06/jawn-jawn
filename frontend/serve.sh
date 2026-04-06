#!/usr/bin/env bash
# serve.sh — serve the frontend on port 6000 using Python's built-in HTTP server
# No installation needed. Run tunnel.sh in a second terminal to expose it over HTTPS.

set -euo pipefail

PORT="${PORT:-6000}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Serving frontend from $DIR on port $PORT ..."
echo "    Run tunnel.sh in a second terminal to get the public HTTPS URL."
echo ""

cd "$DIR"
exec python3 -m http.server "$PORT"
