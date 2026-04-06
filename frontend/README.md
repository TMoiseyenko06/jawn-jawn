# Chat Frontend — VPS Deploy Guide

## Overview

`index.html` is a single, self-contained file.  No build step, no npm, no
dependencies.  Drop it on any HTTP/HTTPS server and open it in a browser.

---

## 1. Edit WS_URL

Open `index.html` and change the `WS_URL` constant at the top of the first
`<script>` block:

```js
const WS_URL = "wss://random-words-here.trycloudflare.com/ws";
```

This is the WebSocket URL printed by `cloudflared tunnel` on the Vast.ai
instance (see `server/README.md`).

---

## 2. Serve with Nginx on a VPS

### Install Nginx (Debian/Ubuntu)

```bash
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
```

### Copy the file

```bash
sudo mkdir -p /var/www/chatbot
sudo cp index.html /var/www/chatbot/
```

### Install the Nginx config

```bash
# Edit nginx.conf first — replace "your-vps-domain.com" with your real domain
sudo cp nginx.conf /etc/nginx/sites-available/chatbot
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/chatbot
sudo nginx -t && sudo systemctl reload nginx
```

### Get a free TLS certificate

```bash
sudo certbot --nginx -d your-vps-domain.com
```

Certbot will automatically edit the nginx config to add the certificate paths.

### Verify

Open `https://your-vps-domain.com` in your browser. You should see the dark
chat UI.

---

## 3. Updating WS_URL after a tunnel restart

Every time cloudflared is restarted with a temporary tunnel, the URL changes.
Update `index.html` and recopy it:

```bash
# On the VPS:
sudo nano /var/www/chatbot/index.html   # or use scp from your machine
sudo systemctl reload nginx             # optional, file is served statically
```

---

## 4. Browser Requirements

| Feature | Notes |
|---|---|
| MediaRecorder API | Chrome 49+, Firefox 25+, Safari 14.1+ |
| AudioContext | All modern browsers |
| WebSocket | All modern browsers |

The mic button requires `getUserMedia` which needs either **localhost** or
**HTTPS**.  Always serve from `https://` in production.
