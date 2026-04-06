# Chat Frontend — VPS Deploy Guide

## Overview

The frontend is a single `index.html` file served by a Python HTTP server.
A Cloudflare Quick Tunnel wraps it in HTTPS so the browser allows mic access.

---

## 1. Set WS_URL

Edit `index.html` and set `WS_URL` to the Vast.ai instance's direct WebSocket
address (found on the Vast.ai instance detail page under port mappings):

```js
const WS_URL = "ws://123.45.67.89:12345/ws";
```

---

## 2. Terminal 1 — start the file server

```bash
chmod +x serve.sh
bash serve.sh
```

Serves `index.html` on port 6000. No installation required — uses Python 3
which is pre-installed on every modern Linux VPS.

---

## 3. Terminal 2 — start the Cloudflare tunnel

```bash
chmod +x tunnel.sh
bash tunnel.sh
```

Installs `cloudflared` if needed (no Cloudflare account required) and prints:

```
============================================================
  Frontend tunnel is live!

  Open in browser : https://some-words.trycloudflare.com

  Mic access works over this HTTPS URL.
============================================================
```

Open that URL from any device — mic works because the page is HTTPS.

> Tunnel URL changes each restart. No Cloudflare account needed.
