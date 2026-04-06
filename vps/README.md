# VPS Proxy Server

Runs on your VPS. Does two things:
1. Serves `frontend/index.html` at `/`
2. Accepts WebSocket connections from browsers at `/ws` and proxies them to the Vast.ai GPU server

```
Browser ←—WSS (Cloudflare tunnel)—→ VPS :6000 ←—WS (direct)—→ Vast.ai :8000
```

---

## 1. Find your Vast.ai WebSocket URL

On the Vast.ai instance detail page, find the port mapping for port 8000:

```
IP: 123.45.67.89   mapped port: 12345  →  internal 8000
```

Your Vast.ai WebSocket URL is `ws://123.45.67.89:12345/ws`.

---

## 2. Terminal 1 — start the proxy server

```bash
cd vps/
pip install -r requirements.txt

VAST_WS_URL="ws://123.45.67.89:12345/ws" bash serve.sh
```

Or export it first:

```bash
export VAST_WS_URL="ws://123.45.67.89:12345/ws"
bash serve.sh
```

---

## 3. Terminal 2 — start the Cloudflare tunnel

```bash
bash tunnel.sh
```

Prints something like:

```
============================================================
  Frontend tunnel is live!

  Open in browser : https://some-words.trycloudflare.com

  Mic access works over this HTTPS URL.
============================================================
```

Open that URL from any device. The page loads, mic works (HTTPS), and all
voice/text traffic flows through the VPS to Vast.ai automatically.

---

## How the WebSocket URL works

The frontend uses `window.location` to build the WebSocket URL at runtime:

```js
const WS_URL = location.origin.replace(/^http/, 'ws') + '/ws';
```

So no URL needs to be hardcoded anywhere in the HTML — it always connects
back to whatever server served the page.
