# GPU Inference Server — Vast.ai Deploy Guide

## Overview

This FastAPI server runs on a Vast.ai GPU instance and provides a WebSocket
endpoint that handles the full voice pipeline:

```
Audio blob → Whisper STT → LLM (streaming) → edge-tts/XTTS → audio chunks back to client
```

The server is accessed directly via the Vast.ai instance's public IP and mapped
port — no tunnel needed on this side.

---

## 1. Rent a Vast.ai Instance

1. Go to [vast.ai](https://vast.ai) and log in.
2. Search for instances with:
   - **GPU**: RTX 3090 / A100 / A6000 (≥ 16 GB VRAM for the 8B model)
   - **Image**: `pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime` (or similar CUDA image)
   - **Disk**: ≥ 50 GB (model weights ≈ 16 GB + Whisper + OS)
3. Under **Port Mapping**, add port **8000** so it gets a public IP:port.

---

## 2. Get the Public WebSocket URL

After the instance starts, Vast.ai shows you a mapped port on the instance
detail page, e.g.:

```
IP: 123.45.67.89   Port: 12345  →  internal 8000
```

Your WebSocket URL is:
```
ws://123.45.67.89:12345/ws
```

Paste that into `frontend/index.html` as `WS_URL`. The frontend is served over
HTTPS (via its own Cloudflare tunnel) so the browser allows mic access even
though the WebSocket itself is plain `ws://`.

---

## 3. Deploy the Server

SSH into the instance, then:

```bash
# Clone or copy the server/ directory onto the instance
git clone <your-repo> && cd <repo>/server

# Set env vars (add to ~/.bashrc for persistence)
export MODEL="cognitivecomputations/dolphin-2.9-llama3-8b"
export WHISPER_MODEL="base.en"    # or "large-v3" for better accuracy
export TTS_VOICE="en-US-JennyNeural"
# export HF_TOKEN="hf_..."        # only needed for gated models

chmod +x start.sh
./start.sh
```

The server downloads models on first run (~5–20 min) then listens on `0.0.0.0:8000`.

Verify:
```bash
curl http://localhost:8000/health
```

---

## 4. Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `MODEL` | `cognitivecomputations/dolphin-2.9-llama3-8b` | HuggingFace model ID |
| `WHISPER_MODEL` | `base.en` | faster-whisper model size |
| `TTS_VOICE` | `en-US-JennyNeural` | edge-tts voice name (fallback) |
| `HF_TOKEN` | *(unset)* | HuggingFace token for gated models |

---

## 5. WebSocket Protocol

| Direction | Format | Meaning |
|---|---|---|
| Client → Server | `{"type":"config","max_tokens":512,"temperature":0.7}` | First message |
| Client → Server | binary bytes | Audio blob (webm/wav) |
| Client → Server | `{"type":"text","content":"..."}` | Typed message |
| Client → Server | `{"type":"voice_ref","audio":"<base64>"}` | Voice clone reference audio |
| Client → Server | `{"type":"clear_voice"}` | Revert to default voice |
| Server → Client | `{"type":"transcript","text":"..."}` | STT result |
| Server → Client | `{"type":"token","text":"..."}` | LLM token stream |
| Server → Client | `AUDIO:<base64_audio>` | TTS audio chunk |
| Server → Client | `{"type":"voice_status","status":"..."}` | Clone status update |
| Server → Client | `[END]` | Turn complete |
