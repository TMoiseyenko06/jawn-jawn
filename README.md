# Real-Time Voice AI Chatbot

A low-latency voice + text chatbot that streams audio responses directly to
the browser.  The heavy GPU work runs on a cheap Vast.ai instance; the
frontend is a single static HTML file served from any VPS.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser (any device)                                               │
│                                                                     │
│  loads page + speaks/types                                          │
│        │  ▲                                                         │
│        │  │  WSS  (Cloudflare tunnel)                               │
└────────┼──┼─────────────────────────────────────────────────────────┘
         │  │
         ▼  │
┌────────────────────────┐
│  VPS                   │
│                        │
│  FastAPI :6000         │  ← serves index.html at /
│  /ws proxy             │  ← forwards WebSocket to Vast.ai
│                        │
│  cloudflared tunnel    │  ← HTTPS so mic works in browser
└────────┬───────────────┘
         │  WS  (direct IP:port)
         ▼
┌────────────────────────┐
│  Vast.ai GPU           │
│                        │
│  FastAPI  :8000        │
│  ├── Whisper STT       │
│  ├── LLM (8B, fp16)    │
│  └── XTTS / edge-tts   │
└────────────────────────┘
```

### Data flow for a voice message

1. User holds mic button → browser captures audio via `MediaRecorder`
2. Audio blob sent as binary WebSocket frame to Cloudflare Tunnel → Vast.ai
3. **Whisper** transcribes audio → server sends `{"type":"transcript","text":"…"}`
4. Transcript shown in user bubble
5. **LLM** streams tokens → server sends `{"type":"token","text":"…"}` per token
6. Tokens build up the assistant bubble in real time
7. As complete sentences form, **edge-tts** synthesises MP3 chunks
8. Each chunk sent as `AUDIO:<base64_mp3>` → browser decodes and queues for playback
9. Server sends `[END]` → input re-enabled

---

## Quick Start

### Step 1 — Rent a GPU on Vast.ai

- GPU with ≥ 16 GB VRAM (RTX 3090 / A100 / A6000)
- Docker image: `pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime`
- Disk: ≥ 50 GB

### Step 2 — Deploy the server

```bash
# SSH into the Vast.ai instance
git clone <your-repo> && cd <repo>/server

# Set env vars (add to ~/.bashrc for persistence)
export MODEL="cognitivecomputations/dolphin-2.9-llama3-8b"
export WHISPER_MODEL="base.en"
export TTS_VOICE="en-US-GuyNeural"
# export HF_TOKEN="hf_..."   # only for gated models

chmod +x start.sh && ./start.sh
```

See `server/README.md` for full details.

### Step 3 — Deploy the VPS proxy server

On your VPS, find the Vast.ai IP:port from the instance detail page, then:

```bash
cd vps/
export VAST_WS_URL="ws://123.45.67.89:12345/ws"
bash serve.sh
```

In a second terminal on the VPS:

```bash
bash vps/tunnel.sh
# Prints: https://some-words.trycloudflare.com
```

Open that URL from any device — the page loads, mic works, all traffic
is proxied through the VPS to Vast.ai automatically.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MODEL` | `cognitivecomputations/dolphin-2.9-llama3-8b` | HuggingFace causal LM |
| `WHISPER_MODEL` | `base.en` | faster-whisper model (`tiny`, `base`, `small`, `medium`, `large-v3`, …) |
| `TTS_VOICE` | `en-US-GuyNeural` | edge-tts voice name |
| `HF_TOKEN` | *(unset)* | HuggingFace token for gated model repos |

---

## WebSocket Protocol Reference

| Direction | Format | Meaning |
|---|---|---|
| Client → Server | `{"type":"config","max_tokens":512,"temperature":0.7}` | First message |
| Client → Server | binary bytes | Audio recording (webm) |
| Client → Server | `{"type":"text","content":"…"}` | Typed message |
| Server → Client | `{"type":"transcript","text":"…"}` | STT result |
| Server → Client | `{"type":"token","text":"…"}` | LLM token |
| Server → Client | `AUDIO:<base64_mp3>` | TTS audio chunk |
| Server → Client | `[END]` | Turn complete |

---

## File Structure

```
.
├── README.md               ← this file
├── server/
│   ├── main.py             ← FastAPI app (Whisper + LLM + TTS pipeline)
│   ├── requirements.txt
│   ├── start.sh
│   └── README.md           ← Vast.ai + cloudflared deploy guide
└── frontend/
    ├── index.html          ← self-contained chat UI
    ├── nginx.conf          ← Nginx config snippet
    └── README.md           ← VPS deploy guide
```
