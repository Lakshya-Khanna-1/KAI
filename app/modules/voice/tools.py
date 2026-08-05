from typing import Any, Dict, Optional
from app.modules.voice import service as voice_service

async def handle_speak_text(text: str, voice: Optional[str] = None) -> Dict[str, Any]:
    audio_bytes = await voice_service.synthesize_speech(text, voice=voice)
    return {
        "status": "success",
        "audio_bytes_length": len(audio_bytes),
        "message": f"Synthesized speech for text ({len(text)} characters)."
    }

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "speak_text",
            "description": "Synthesize a text response into audio speech using local Piper TTS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text content to speak"},
                    "voice": {"type": "string", "description": "Voice model (optional)"}
                },
                "required": ["text"]
            }
        },
        "handler": handle_speak_text
    }
]
