# GPU Inference Server — Vast.ai Deploy Guide

## Overview

This FastAPI server runs on a Vast.ai GPU instance and provides a WebSocket
endpoint that handles the full voice pipeline:

```
Audio blob → Whisper STT → LLM (streaming) → edge-tts → audio chunks back to client
```

---

## 1. Rent a Vast.ai Instance

1. Go to [vast.ai](https://vast.ai) and log in.
2. Search for instances with:
   - **GPU**: RTX 3090 / A100 / A6000 (≥ 16 GB VRAM for the 8B model)
   - **Image**: `pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime` (or similar CUDA image)
   - **Disk**: ≥ 50 GB (model weights ≈ 16 GB + Whisper + OS)
3. Open port **8000** in the instance's port mapping settings.

---

## 2. Upload & Run the Server

SSH into the instance, then:

```bash
# Clone or copy the server/ directory onto the instance
git clone <your-repo> && cd <repo>/server

# (Optional) set env vars for gated models or custom config
export MODEL="cognitivecomputations/dolphin-2.9-llama3-8b"
export WHISPER_MODEL="base.en"    # or "large-v3" for better accuracy
export TTS_VOICE="en-US-JennyNeural"
export HF_TOKEN="hf_..."          # only needed for gated models

chmod +x start.sh tunnel.sh
./start.sh
```

The server will download models on first run (~5–20 min depending on size) and
then listen on `0.0.0.0:8000`.

Verify it's up:
```bash
curl http://localhost:8000/health
```

---

## 3. Expose the WebSocket via Cloudflare Tunnel

Run `tunnel.sh` in a **second terminal** on the same instance.
It installs `cloudflared` automatically if needed (no Cloudflare account required)
and prints the ready-to-paste WSS URL:

```bash
bash tunnel.sh
```

Output looks like:

```
============================================================
  Tunnel is live!

  Public HTTPS : https://random-words-here.trycloudflare.com
  WebSocket    : wss://random-words-here.trycloudflare.com/ws

  Paste this into frontend/index.html:
    const WS_URL = "wss://random-words-here.trycloudflare.com/ws";
============================================================
```

Copy that `const WS_URL` line into `frontend/index.html` and refresh the page.

> **Note**: The Quick Tunnel URL changes every restart. For a persistent URL,
> create a free Cloudflare account and use a named tunnel:
> `cloudflared tunnel login` then `cloudflared tunnel create my-bot`

### Override the default port

```bash
TUNNEL_PORT=9000 bash tunnel.sh   # if your server runs on a different port
```

---

## 4. Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `MODEL` | `cognitivecomputations/dolphin-2.9-llama3-8b` | HuggingFace model ID |
| `WHISPER_MODEL` | `base.en` | faster-whisper model size |
| `TTS_VOICE` | `en-US-JennyNeural` | edge-tts voice name |
| `HF_TOKEN` | *(unset)* | HuggingFace access token for gated models |

---

## 5. WebSocket Protocol

| Direction | Format | Meaning |
|---|---|---|
| Client → Server | `{"type":"config","max_tokens":512,"temperature":0.7}` | First message, sets generation params |
| Client → Server | binary bytes | Audio blob (webm/wav) |
| Client → Server | `{"type":"text","content":"..."}` | Typed message |
| Server → Client | `{"type":"transcript","text":"..."}` | STT result |
| Server → Client | `{"type":"token","text":"..."}` | LLM token stream |
| Server → Client | `AUDIO:<base64_mp3>` | TTS audio chunk |
| Server → Client | `[END]` | Turn complete |
