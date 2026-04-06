import asyncio
import os
import logging
from pathlib import Path

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

VAST_WS_URL = os.environ.get("VAST_WS_URL", "")  # e.g. ws://123.45.67.89:12345/ws
FRONTEND_HTML = Path(__file__).parent.parent / "frontend" / "index.html"


@app.get("/")
async def serve_frontend():
    return HTMLResponse(FRONTEND_HTML.read_text())


@app.websocket("/ws")
async def proxy_websocket(client: WebSocket):
    await client.accept()

    if not VAST_WS_URL:
        await client.send_text('{"type":"error","message":"VAST_WS_URL not configured on VPS"}')
        await client.close()
        return

    logger.info("New browser connection — opening upstream to %s", VAST_WS_URL)

    try:
        async with websockets.connect(VAST_WS_URL) as upstream:

            async def browser_to_vast():
                """Forward everything the browser sends to Vast.ai."""
                try:
                    while True:
                        msg = await client.receive()
                        if msg.get("bytes"):
                            await upstream.send(msg["bytes"])
                        elif msg.get("text"):
                            await upstream.send(msg["text"])
                except (WebSocketDisconnect, Exception):
                    pass
                finally:
                    await upstream.close()

            async def vast_to_browser():
                """Forward everything Vast.ai sends back to the browser."""
                try:
                    async for msg in upstream:
                        if isinstance(msg, bytes):
                            await client.send_bytes(msg)
                        else:
                            await client.send_text(msg)
                except Exception:
                    pass

            await asyncio.gather(browser_to_vast(), vast_to_browser())

    except OSError as exc:
        logger.error("Could not connect to Vast.ai at %s: %s", VAST_WS_URL, exc)
        try:
            await client.send_text(
                f'{{"type":"error","message":"Cannot reach GPU server: {exc}"}}'
            )
            await client.close()
        except Exception:
            pass
    except WebSocketDisconnect:
        logger.info("Browser disconnected.")
