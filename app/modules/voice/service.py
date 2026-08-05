import logging
import math
import struct
import httpx
from typing import Any, Dict, Optional
from app.config import settings

logger = logging.getLogger(__name__)


def generate_fallback_wav(duration_sec: float = 0.4, freq: float = 440.0) -> bytes:
    """Generate a minimal valid 16kHz mono 16-bit PCM WAV audio file."""
    sample_rate = 16000
    num_samples = int(sample_rate * duration_sec)
    data = bytearray()
    for i in range(num_samples):
        sample = int(32767 * 0.08 * math.sin(2 * math.pi * freq * i / sample_rate))
        data.extend(struct.pack("<h", sample))

    header = bytearray()
    header.extend(b"RIFF")
    header.extend(struct.pack("<I", 36 + len(data)))
    header.extend(b"WAVEfmt ")
    header.extend(struct.pack("<I", 16))  # Subchunk1Size
    header.extend(struct.pack("<H", 1))   # PCM format
    header.extend(struct.pack("<H", 1))   # Mono
    header.extend(struct.pack("<I", sample_rate))
    header.extend(struct.pack("<I", sample_rate * 2))
    header.extend(struct.pack("<H", 2))   # Block align
    header.extend(struct.pack("<H", 16))  # Bits per sample
    header.extend(b"data")
    header.extend(struct.pack("<I", len(data)))

    return bytes(header + data)


async def transcribe_audio(audio_bytes: bytes, filename: str = "recording.wav") -> Dict[str, Any]:
    """
    Sends raw audio bytes to the whisper.cpp STT endpoint for transcription.
    Returns dict with 'text' and status.
    """
    if not audio_bytes or len(audio_bytes) < 10:
        return {"status": "error", "message": "Empty or invalid audio file provided.", "text": ""}

    url = settings.WHISPER_URL.rstrip("/")
    endpoints = [f"{url}/inference", f"{url}/v1/audio/transcriptions"]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for ep in endpoints:
            try:
                files = {"file": (filename, audio_bytes, "audio/wav")}
                data = {"response_format": "json", "temperature": "0.0"}
                resp = await client.post(ep, files=files, data=data)
                if resp.status_code == 200:
                    res_json = resp.json()
                    text = res_json.get("text", "").strip()
                    return {"status": "success", "text": text, "source": "whisper"}
            except Exception as e:
                logger.debug(f"Whisper endpoint {ep} attempt failed: {e}")

    # Fallback if whisper container is not active or reachable
    logger.warning("Whisper STT service unavailable. Returning fallback response.")
    return {
        "status": "success",
        "text": "[Voice recording received]",
        "source": "fallback",
        "note": "whisper.cpp service unreachable"
    }


async def synthesize_speech(text: str, voice: Optional[str] = None) -> bytes:
    """
    Sends text to Piper TTS service to synthesize WAV audio stream.
    Returns raw audio bytes (WAV format).
    """
    clean_text = text.strip()
    if not clean_text:
        return generate_fallback_wav(duration_sec=0.2)

    url = settings.PIPER_URL.rstrip("/")
    endpoints = [
        (f"{url}/", "GET", {"text": clean_text}),
        (f"{url}/api/tts", "POST", {"text": clean_text}),
        (f"{url}/v1/audio/speech", "POST", {"input": clean_text, "model": voice or "en_US-lessac-medium"})
    ]

    async with httpx.AsyncClient(timeout=8.0) as client:
        for ep, method, params_or_json in endpoints:
            try:
                if method == "GET":
                    resp = await client.get(ep, params=params_or_json)
                else:
                    resp = await client.post(ep, json=params_or_json)

                if resp.status_code == 200 and len(resp.content) > 100:
                    return resp.content
            except Exception as e:
                logger.debug(f"Piper TTS endpoint {ep} attempt failed: {e}")

    # Fallback clean audio stream
    logger.warning("Piper TTS service unavailable. Returning fallback WAV stream.")
    return generate_fallback_wav(duration_sec=0.5)


async def check_voice_health() -> Dict[str, Any]:
    """Check connectivity to Whisper STT and Piper TTS services."""
    stt_ok = False
    tts_ok = False

    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            r = await client.get(settings.WHISPER_URL)
            stt_ok = r.status_code in [200, 404, 405]
        except Exception:
            stt_ok = False

        try:
            r = await client.get(settings.PIPER_URL)
            tts_ok = r.status_code in [200, 404, 405]
        except Exception:
            tts_ok = False

    return {
        "stt": {"service": "whisper.cpp", "url": settings.WHISPER_URL, "status": "online" if stt_ok else "offline"},
        "tts": {"service": "piper-tts", "url": settings.PIPER_URL, "status": "online" if tts_ok else "offline"}
    }
