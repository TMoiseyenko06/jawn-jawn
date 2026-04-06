import os
import json
import asyncio
import base64
import io
import re
import logging
import tempfile
from threading import Thread
from typing import Optional

import numpy as np
import soundfile as sf
import edge_tts
import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TextIteratorStreamer,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# ---------------------------------------------------------------------------
# Global model state
# ---------------------------------------------------------------------------

MODEL_NAME = os.environ.get("MODEL", "cognitivecomputations/dolphin-2.9-llama3-8b")
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base.en")
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-GuyNeural")
HF_TOKEN = os.environ.get("HF_TOKEN", None)

whisper_model: Optional[WhisperModel] = None
llm_tokenizer: Optional[AutoTokenizer] = None
llm_model: Optional[AutoModelForCausalLM] = None
models_loaded: bool = False
load_error: Optional[str] = None


@app.on_event("startup")
async def load_models():
    global whisper_model, llm_tokenizer, llm_model, models_loaded, load_error
    try:
        logger.info("Loading Whisper model: %s", WHISPER_MODEL_SIZE)
        whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device="cuda",
            compute_type="float16",
        )
        logger.info("Whisper loaded.")

        logger.info("Loading LLM: %s", MODEL_NAME)
        llm_tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME,
            token=HF_TOKEN,
        )
        llm_model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.float16,
            device_map="auto",
            token=HF_TOKEN,
        )
        llm_model.eval()
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
# Helpers
# ---------------------------------------------------------------------------

def transcribe_audio(audio_bytes: bytes) -> str:
    """Transcribe raw audio bytes with faster-whisper."""
    # Write to a temp file so faster-whisper can read it
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, _ = whisper_model.transcribe(tmp_path, beam_size=5)
        transcript = " ".join(seg.text.strip() for seg in segments).strip()
    finally:
        os.unlink(tmp_path)

    return transcript


def run_llm(
    messages: list,
    max_new_tokens: int,
    temperature: float,
    streamer: TextIteratorStreamer,
):
    """Run LLM inference in a background thread (so we can stream)."""
    inputs = llm_tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
    ).to(llm_model.device)

    gen_kwargs = dict(
        input_ids=inputs,
        streamer=streamer,
        max_new_tokens=max_new_tokens,
        do_sample=temperature > 0,
        temperature=temperature if temperature > 0 else 1.0,
        pad_token_id=llm_tokenizer.eos_token_id,
    )
    with torch.no_grad():
        llm_model.generate(**gen_kwargs)


async def synthesize_sentence(sentence: str) -> bytes:
    """Convert a sentence to MP3 bytes via edge-tts."""
    communicate = edge_tts.Communicate(sentence, TTS_VOICE)
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
    return b"".join(audio_chunks)


def split_into_sentences(text: str) -> tuple[list[str], str]:
    """
    Split text on sentence-ending punctuation.
    Returns (complete_sentences, remainder).
    """
    pattern = r"(?<=[.!?])\s+"
    parts = re.split(pattern, text)
    if len(parts) <= 1:
        return [], text
    # Last element is the incomplete remainder (no terminal punctuation yet)
    # unless the whole string ended with punctuation
    if re.search(r"[.!?]\s*$", text):
        return parts, ""
    return parts[:-1], parts[-1]


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Defaults — overridden by client config message
    max_new_tokens = 512
    temperature = 0.7
    chat_history: list[dict] = []

    # ---- config handshake (first message must be JSON config) ----
    try:
        raw = await asyncio.wait_for(websocket.receive(), timeout=10.0)
    except asyncio.TimeoutError:
        await websocket.close(code=1008)
        return

    if "text" in raw:
        try:
            cfg = json.loads(raw["text"])
            if cfg.get("type") == "config":
                max_new_tokens = int(cfg.get("max_tokens", max_new_tokens))
                temperature = float(cfg.get("temperature", temperature))
        except (json.JSONDecodeError, ValueError):
            pass
    # If it was binary, we treat it as the first audio message below (fall through)
    first_message = raw if "bytes" in raw else None

    async def handle_turn(text_input: str):
        """Run one full pipeline turn given a text prompt."""
        nonlocal chat_history

        chat_history.append({"role": "user", "content": text_input})

        # ---- LLM streaming ----
        streamer = TextIteratorStreamer(
            llm_tokenizer, skip_prompt=True, skip_special_tokens=True
        )
        thread = Thread(
            target=run_llm,
            args=(chat_history, max_new_tokens, temperature, streamer),
            daemon=True,
        )
        thread.start()

        full_response = ""
        sentence_buffer = ""

        for token in streamer:
            full_response += token
            sentence_buffer += token
            await websocket.send_text(json.dumps({"type": "token", "text": token}))

            # Check for complete sentences
            complete, sentence_buffer = split_into_sentences(sentence_buffer)
            for sentence in complete:
                sentence = sentence.strip()
                if sentence:
                    try:
                        mp3_bytes = await synthesize_sentence(sentence)
                        b64 = base64.b64encode(mp3_bytes).decode("utf-8")
                        await websocket.send_text(f"AUDIO:{b64}")
                    except Exception as tts_err:
                        logger.warning("TTS error: %s", tts_err)

        # Flush any remaining buffer (sentence without terminal punctuation)
        remainder = sentence_buffer.strip()
        if remainder:
            try:
                mp3_bytes = await synthesize_sentence(remainder)
                b64 = base64.b64encode(mp3_bytes).decode("utf-8")
                await websocket.send_text(f"AUDIO:{b64}")
            except Exception as tts_err:
                logger.warning("TTS error (remainder): %s", tts_err)

        chat_history.append({"role": "assistant", "content": full_response})
        await websocket.send_text("[END]")

    # ---- main receive loop ----
    async def process_message(raw_msg):
        if "bytes" in raw_msg and raw_msg["bytes"]:
            # Binary = audio blob
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
                if msg.get("type") == "text" and msg.get("content"):
                    await handle_turn(msg["content"])
            except (json.JSONDecodeError, KeyError):
                pass

    try:
        if first_message is not None:
            await process_message(first_message)

        while True:
            raw_msg = await websocket.receive()
            await process_message(raw_msg)

    except WebSocketDisconnect:
        logger.info("Client disconnected.")
    except Exception as exc:
        logger.exception("WebSocket error: %s", exc)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
