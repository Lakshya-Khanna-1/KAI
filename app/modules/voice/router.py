import time
import os
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Response, Query
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional

from app.services.voice.pipeline import voice_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None


@router.websocket("/stream")
async def voice_stream_websocket(websocket: WebSocket):
    """
    Bidirectional 16kHz PCM WebSocket Streaming Endpoint.
    Client sends binary PCM frames (or complete audio buffer).
    Server streams back partial transcripts, audio chunks, and latency budget timing metrics.
    """
    await websocket.accept()
    logger.info("Voice Stream WebSocket client connected.")

    try:
        while True:
            # Receive binary PCM audio frame or message
            message = await websocket.receive()
            speech_end_time = time.perf_counter()

            pcm_bytes = b""
            if "bytes" in message and message["bytes"]:
                pcm_bytes = message["bytes"]
            elif "text" in message and message["text"]:
                # If text message received, echo back status
                await websocket.send_json({"type": "info", "message": "Text frame received"})
                continue

            if not pcm_bytes or len(pcm_bytes) == 0:
                continue

            logger.info(f"Received {len(pcm_bytes)} bytes of PCM audio. Triggering pipeline...")

            # Run streaming turn generator
            async for frame in voice_pipeline.process_voice_turn(pcm_bytes, speech_end_time):
                await websocket.send_json(frame)

    except WebSocketDisconnect:
        logger.info("Voice Stream WebSocket client disconnected.")
    except Exception as e:
        logger.error(f"WebSocket error in voice stream: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


@router.get("/health")
async def voice_health():
    """
    Reports per-stage load time and last inference duration in ms.
    """
    return voice_pipeline.get_health()


@router.get("/debug", response_class=HTMLResponse)
async def voice_debug_page():
    """
    Serves the interactive Voice Studio Debug page.
    """
    debug_path = os.path.join(os.path.dirname(__file__), "..", "..", "static", "voice_debug.html")
    debug_path = os.path.abspath(debug_path)
    if os.path.exists(debug_path):
        return FileResponse(debug_path)
    raise HTTPException(status_code=404, detail="Debug page HTML not found.")


@router.post("/stt")
async def speech_to_text_legacy(file: FileResponse = None):
    """Transcribe audio via pipeline STT."""
    return {"status": "Use WebSocket endpoint /voice/stream"}


@router.get("/status")
async def voice_status():
    """Returns connectivity status for STT and TTS services."""
    return voice_pipeline.get_health()
