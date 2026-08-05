from fastapi import APIRouter, File, UploadFile, Query, HTTPException, Response
from pydantic import BaseModel
from typing import Optional
from app.modules.voice import service as voice_service

router = APIRouter(prefix="/voice", tags=["voice"])


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None


@router.post("/stt")
async def speech_to_text(file: UploadFile = File(...)):
    """Transcribe uploaded audio file using Whisper STT."""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file submitted.")

    result = await voice_service.transcribe_audio(audio_bytes, filename=file.filename or "recording.wav")
    return result


@router.post("/tts")
async def text_to_speech_post(req: TTSRequest):
    """Synthesize text into WAV audio stream via Piper TTS."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    audio_bytes = await voice_service.synthesize_speech(req.text, voice=req.voice)
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": "inline; filename=speech.wav",
            "Cache-Control": "public, max-age=3600"
        }
    )


@router.get("/tts")
async def text_to_speech_get(text: str = Query(..., description="Text to speak")):
    """GET endpoint for synthesizing text to speech."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text parameter required.")

    audio_bytes = await voice_service.synthesize_speech(text)
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": "inline; filename=speech.wav",
            "Cache-Control": "public, max-age=3600"
        }
    )


@router.get("/status")
async def voice_status():
    """Returns connectivity status for STT and TTS services."""
    return await voice_service.check_voice_health()
