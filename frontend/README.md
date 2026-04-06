# Chat Frontend — VPS Deploy Guide

## Overview

`index.html` is a single, self-contained file.  No build step, no npm, no
dependencies.  Drop it on any HTTP server and open it in a browser.

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
sudo apt update && sudo apt install -y nginx
```

### Open port 6000 in your VPS firewall

```bash
# ufw (Ubuntu)
sudo ufw allow 6000/tcp

# Or with iptables
sudo iptables -I INPUT -p tcp --dport 6000 -j ACCEPT
```

### Copy the file

```bash
sudo mkdir -p /var/www/chatbot
sudo cp index.html /var/www/chatbot/
```

### Install the Nginx config

```bash
sudo cp nginx.conf /etc/nginx/sites-available/chatbot
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/chatbot
sudo nginx -t && sudo systemctl reload nginx
```

### Verify

Open `http://<your-vps-ip>:6000` in your browser. You should see the dark
chat UI.

---

## 3. Updating WS_URL after a tunnel restart

Every time cloudflared is restarted with a temporary tunnel, the URL changes.
Update `index.html` and recopy it:

```bash
sudo nano /var/www/chatbot/index.html
# (no nginx reload needed — file is served statically)
```

---

## 4. Browser Requirements

| Feature | Notes |
|---|---|
| MediaRecorder API | Chrome 49+, Firefox 25+, Safari 14.1+ |
| AudioContext | All modern browsers |
| WebSocket | All modern browsers |

> **Note on microphone access**: browsers require either `localhost` or HTTPS
> for `getUserMedia`.  If you serve over plain HTTP on port 6000, the mic
> button will only work when accessed from `localhost` (e.g. SSH port-forward)
> or if your browser has been explicitly granted an exception.  For remote
> access add a TLS terminator (e.g. `nginx` with Let's Encrypt) in front.
