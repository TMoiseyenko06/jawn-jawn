import os
import json
import asyncio
import base64
import io
import re
import logging
import subprocess
import tempfile
from pathlib import Path
from threading import Thread
from typing import Optional

import queue
import numpy as np
import soundfile as sf
import edge_tts
import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from faster_whisper import WhisperModel
from llama_cpp import Llama

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

FRONTEND_HTML = Path(__file__).parent.parent / "frontend" / "index.html"


@app.get("/")
async def serve_frontend():
    return HTMLResponse(FRONTEND_HTML.read_text())

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL_NAME        = os.environ.get("MODEL", "themradermacher/MN-Violet-Lotus-12B-GGUF")
GGUF_FILE         = os.environ.get("GGUF_FILE", "*Q4_K_M.gguf")
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base.en")
TTS_VOICE         = os.environ.get("TTS_VOICE", "en-US-JennyNeural")
HF_TOKEN          = os.environ.get("HF_TOKEN", None)
N_CTX             = int(os.environ.get("N_CTX", "4096"))
N_GPU_LAYERS      = int(os.environ.get("N_GPU_LAYERS", "-1"))  # -1 = all layers on GPU
SYSTEM_PROMPT     = os.environ.get(
    "SYSTEM_PROMPT",
    "You are a helpful, conversational voice assistant. "
    "Keep your responses concise and natural — you are speaking aloud, not writing. "
    "Avoid bullet points, markdown, or code blocks unless explicitly asked."
)

# Tell Coqui TTS we accept their terms so loading is non-interactive
os.environ.setdefault("COQUI_TOS_AGREED", "1")

# ---------------------------------------------------------------------------
# Global model state
# ---------------------------------------------------------------------------

whisper_model: Optional[WhisperModel] = None
llm_model: Optional[Llama] = None
models_loaded: bool = False
load_error: Optional[str] = None

# Single global conversation history (user + assistant turns only, no system)
global_history: list[dict] = []
HISTORY_CONTEXT = 6  # messages kept in LLM context (3 pairs)

# XTTS is loaded lazily on first voice-clone request
xtts_model = None
_xtts_lock: Optional[asyncio.Lock] = None


@app.on_event("startup")
async def load_models():
    global whisper_model, llm_model, models_loaded, load_error, _xtts_lock
    _xtts_lock = asyncio.Lock()
    try:
        logger.info("Loading Whisper model: %s", WHISPER_MODEL_SIZE)
        whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device="cuda",
            compute_type="float16",
        )
        logger.info("Whisper loaded.")

        logger.info("Loading LLM from %s (file: %s) ...", MODEL_NAME, GGUF_FILE)
        llm_model = Llama.from_pretrained(
            repo_id=MODEL_NAME,
            filename=GGUF_FILE,
            n_gpu_layers=N_GPU_LAYERS,
            n_ctx=N_CTX,
            verbose=False,
        )
        logger.info("LLM loaded.")
        models_loaded = True
    except Exception as exc:
        load_error = str(exc)
        logger.exception("Failed to load models: %s", exc)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    if models_loaded:
        return JSONResponse({"status": "ok", "model": MODEL_NAME, "whisper": WHISPER_MODEL_SIZE})
    if load_error:
        return JSONResponse({"status": "error", "detail": load_error}, status_code=503)
    return JSONResponse({"status": "loading"}, status_code=503)


# ---------------------------------------------------------------------------
# XTTS voice cloning helpers
# ---------------------------------------------------------------------------

async def ensure_xtts() -> bool:
    """Lazily load XTTS v2. Returns True if available."""
    global xtts_model
    if xtts_model is not None:
        return True
    async with _xtts_lock:
        if xtts_model is not None:
            return True
        try:
            logger.info("Loading XTTS v2 for voice cloning...")

            def _load():
                from TTS.api import TTS as CoquiTTS  # noqa: PLC0415
                api = CoquiTTS(
                    "tts_models/multilingual/multi-dataset/xtts_v2",
                    gpu=torch.cuda.is_available(),
                )
                # Return the underlying model for direct inference
                return api.synthesizer.tts_model

            xtts_model = await asyncio.get_event_loop().run_in_executor(None, _load)
            logger.info("XTTS v2 ready.")
            return True
        except Exception as exc:
            logger.warning("XTTS v2 unavailable (%s) — will fall back to edge-tts.", exc)
            return False


def _convert_audio_to_wav(input_path: str, output_path: str) -> bool:
    """Convert any audio file to 22 kHz mono WAV using ffmpeg."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", input_path,
                "-ar", "22050", "-ac", "1", "-sample_fmt", "s16",
                output_path,
            ],
            capture_output=True,
            timeout=60,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _compute_speaker_latents(wav_path: str):
    """Compute XTTS conditioning latents from a reference WAV (sync, run in executor)."""
    return xtts_model.get_conditioning_latents(audio_path=[wav_path])


def _synthesize_xtts(sentence: str, gpt_cond_latent, speaker_embedding) -> bytes:
    """Run XTTS inference and return WAV bytes (sync, run in executor)."""
    out = xtts_model.inference(
        text=sentence,
        language="en",
        gpt_cond_latent=gpt_cond_latent,
        speaker_embedding=speaker_embedding,
        temperature=0.7,
    )
    wav = out["wav"]
    wav_np = np.array(wav, dtype=np.float32) if not isinstance(wav, np.ndarray) else wav
    buf = io.BytesIO()
    sf.write(buf, wav_np, 24000, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return buf.read()


async def process_voice_ref(audio_b64: str) -> tuple:
    """
    Decode base64 reference audio, convert to WAV, compute XTTS latents.
    Returns (gpt_cond_latent, speaker_embedding) or (None, None) on failure.
    """
    if not await ensure_xtts():
        return None, None

    loop = asyncio.get_event_loop()
    try:
        raw_bytes = base64.b64decode(audio_b64)

        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f_in:
            f_in.write(raw_bytes)
            in_path = f_in.name

        out_path = in_path + "_ref.wav"
        converted = await loop.run_in_executor(
            None, _convert_audio_to_wav, in_path, out_path
        )
        os.unlink(in_path)

        if not converted:
            # ffmpeg unavailable or failed — try loading directly with soundfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_fallback:
                f_fallback.write(raw_bytes)
                out_path = f_fallback.name

        gpt_latent, spk_emb = await loop.run_in_executor(
            None, _compute_speaker_latents, out_path
        )
        os.unlink(out_path)
        return gpt_latent, spk_emb

    except Exception as exc:
        logger.warning("Voice reference processing failed: %s", exc)
        for p in (in_path, out_path):
            try:
                os.unlink(p)
            except Exception:
                pass
        return None, None


# ---------------------------------------------------------------------------
# TTS dispatch — XTTS if voice clone ready, else edge-tts
# ---------------------------------------------------------------------------

async def synthesize_sentence(
    sentence: str,
    gpt_cond_latent=None,
    speaker_embedding=None,
) -> bytes:
    if gpt_cond_latent is not None and speaker_embedding is not None:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _synthesize_xtts, sentence, gpt_cond_latent, speaker_embedding
        )

    # Default: edge-tts (female voice)
    communicate = edge_tts.Communicate(sentence, TTS_VOICE)
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# STT + LLM helpers
# ---------------------------------------------------------------------------

def transcribe_audio(audio_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        segments, _ = whisper_model.transcribe(tmp_path, beam_size=5)
        return " ".join(seg.text.strip() for seg in segments).strip()
    finally:
        os.unlink(tmp_path)


def run_llm(messages, max_new_tokens, temperature, token_queue):
    try:
        stream = llm_model.create_chat_completion(
            messages=messages,
            max_tokens=max_new_tokens,
            temperature=temperature if temperature > 0 else 1.0,
            stream=True,
        )
        for chunk in stream:
            delta = chunk["choices"][0]["delta"]
            content = delta.get("content", "")
            if content:
                token_queue.put(content)
    except Exception as exc:
        logger.error("LLM error: %s", exc)
    finally:
        token_queue.put(None)


def split_into_sentences(text: str) -> tuple[list[str], str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    if len(parts) <= 1:
        return [], text
    if re.search(r"[.!?]\s*$", text):
        return parts, ""
    return parts[:-1], parts[-1]


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    max_new_tokens = 512
    temperature    = 0.7

    # Read system prompt from file on every connection
    _prompt_file = Path(__file__).parent / "system_prompt.txt"
    try:
        system_prompt = _prompt_file.read_text().strip()
    except FileNotFoundError:
        system_prompt = SYSTEM_PROMPT

    # Per-connection voice clone state
    voice_gpt_latent  = None
    voice_speaker_emb = None

    # ---- config handshake ----
    # Give the user up to 5 minutes to fill out the setup form before timing out.
    try:
        raw = await asyncio.wait_for(websocket.receive(), timeout=300.0)
    except asyncio.TimeoutError:
        await websocket.close(code=1008)
        return

    first_binary = None
    if "text" in raw:
        try:
            cfg = json.loads(raw["text"])
            if cfg.get("type") == "config":
                max_new_tokens = int(cfg.get("max_tokens", max_new_tokens))
                temperature    = float(cfg.get("temperature", temperature))
                # Frontend can override the system prompt set in system_prompt.txt
                if cfg.get("system_prompt"):
                    system_prompt = cfg["system_prompt"].strip()
        except (json.JSONDecodeError, ValueError):
            pass
    elif "bytes" in raw:
        first_binary = raw

    # Send last 3 exchanges to the frontend so it can re-render them
    if global_history:
        await websocket.send_text(json.dumps({
            "type": "history",
            "messages": global_history[-HISTORY_CONTEXT:]
        }))

    # ---- per-turn handler ----
    async def handle_turn(text_input: str):
        nonlocal voice_gpt_latent, voice_speaker_emb
        global_history.append({"role": "user", "content": text_input})

        # Build context: system prompt + last N history messages
        context = [{"role": "system", "content": system_prompt}] + global_history[-HISTORY_CONTEXT:]
        token_q: queue.Queue = queue.Queue()
        Thread(
            target=run_llm,
            args=(context, max_new_tokens, temperature, token_q),
            daemon=True,
        ).start()

        full_response   = ""
        sentence_buffer = ""   # spoken text only
        in_action       = False
        loop = asyncio.get_event_loop()

        async def flush_spoken(text: str):
            """Send a spoken sentence to TTS and stream audio."""
            text = text.strip()
            if not text:
                return
            try:
                audio = await synthesize_sentence(text, voice_gpt_latent, voice_speaker_emb)
                b64 = base64.b64encode(audio).decode()
                await websocket.send_text(f"AUDIO:{b64}")
            except Exception as err:
                logger.warning("TTS error: %s", err)

        while True:
            raw_token = await loop.run_in_executor(None, token_q.get)
            if raw_token is None:
                break
            full_response += raw_token
            # Split on * to detect action boundaries within a single token
            segments = raw_token.split("*")
            for i, seg in enumerate(segments):
                if seg:
                    msg_type = "action_token" if in_action else "token"
                    await websocket.send_text(json.dumps({"type": msg_type, "text": seg}))
                    if not in_action:
                        sentence_buffer += seg
                        complete, sentence_buffer = split_into_sentences(sentence_buffer)
                        for sentence in complete:
                            await flush_spoken(sentence)
                # Every * toggles action mode
                if i < len(segments) - 1:
                    in_action = not in_action

        # Flush remaining spoken text
        await flush_spoken(sentence_buffer)

        global_history.append({"role": "assistant", "content": full_response})
        await websocket.send_text("[END]")

    # ---- message dispatcher ----
    async def process_message(raw_msg):
        nonlocal voice_gpt_latent, voice_speaker_emb

        if "bytes" in raw_msg and raw_msg["bytes"]:
            audio_bytes = raw_msg["bytes"]
            transcript = await asyncio.get_event_loop().run_in_executor(
                None, transcribe_audio, audio_bytes
            )
            if not transcript:
                transcript = "(no speech detected)"
            await websocket.send_text(
                json.dumps({"type": "transcript", "text": transcript})
            )
            await handle_turn(transcript)

        elif "text" in raw_msg:
            try:
                msg = json.loads(raw_msg["text"])
            except json.JSONDecodeError:
                return

            if msg.get("type") == "text" and msg.get("content"):
                await handle_turn(msg["content"])

            elif msg.get("type") == "voice_ref":
                audio_b64 = msg.get("audio", "")
                if not audio_b64:
                    await websocket.send_text(
                        json.dumps({"type": "voice_status", "status": "failed",
                                    "reason": "no audio data"})
                    )
                    return

                await websocket.send_text(
                    json.dumps({"type": "voice_status", "status": "cloning"})
                )
                lat, emb = await process_voice_ref(audio_b64)
                if lat is not None:
                    voice_gpt_latent  = lat
                    voice_speaker_emb = emb
                    await websocket.send_text(
                        json.dumps({"type": "voice_status", "status": "ready"})
                    )
                else:
                    await websocket.send_text(
                        json.dumps({"type": "voice_status", "status": "failed",
                                    "reason": "could not process reference audio"})
                    )

            elif msg.get("type") == "clear_voice":
                voice_gpt_latent  = None
                voice_speaker_emb = None
                await websocket.send_text(
                    json.dumps({"type": "voice_status", "status": "cleared"})
                )

    try:
        if first_binary is not None:
            await process_message(first_binary)
        while True:
            await process_message(await websocket.receive())
    except WebSocketDisconnect:
        logger.info("Client disconnected.")
    except Exception as exc:
        logger.exception("WebSocket error: %s", exc)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
