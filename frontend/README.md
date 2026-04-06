# Chat Frontend — VPS Deploy Guide

## Overview

`index.html` is a single, self-contained file served by Nginx on port 6000.
A Cloudflare Quick Tunnel wraps it in HTTPS so the browser allows mic access
(`getUserMedia` requires a secure context).

---

## 1. Set WS_URL

Open `index.html` and set `WS_URL` to the Vast.ai instance's direct WebSocket
address (found on the Vast.ai instance detail page under port mappings):

```js
const WS_URL = "ws://123.45.67.89:12345/ws";
```

---

## 2. Serve with Nginx

```bash
sudo apt update && sudo apt install -y nginx curl

sudo mkdir -p /var/www/chatbot
sudo cp index.html /var/www/chatbot/

sudo cp nginx.conf /etc/nginx/sites-available/chatbot
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/chatbot
sudo nginx -t && sudo systemctl reload nginx
```

---

## 3. Start the Cloudflare Tunnel

Run `tunnel.sh` on the VPS. It installs `cloudflared` automatically and
prints the public HTTPS URL:

```bash
chmod +x tunnel.sh
bash tunnel.sh
```

Output:

```
============================================================
  Frontend tunnel is live!

  Open in browser : https://some-words.trycloudflare.com

  Mic access works over this HTTPS URL.
============================================================
```

Open that URL in your browser — mic will work because the page is HTTPS.

> The tunnel URL changes each restart. No Cloudflare account needed.

---

## 4. Browser Requirements

| Feature | Notes |
|---|---|
| MediaRecorder API | Chrome 49+, Firefox 25+, Safari 14.1+ |
| AudioContext | All modern browsers |
| WebSocket | All modern browsers |
