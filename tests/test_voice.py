import pytest
import io
from fastapi.testclient import TestClient
from app.main import create_app
from app.modules.voice.service import generate_fallback_wav

app = create_app()
client = TestClient(app)

HEADERS = {"Authorization": "Bearer test-token"}


def test_fallback_wav_generator():
    wav_bytes = generate_fallback_wav(duration_sec=0.3, freq=440.0)
    assert len(wav_bytes) > 44
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"


def test_voice_status_endpoint():
    resp = client.get("/voice/status", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "stt" in data
    assert "tts" in data
    assert data["stt"]["service"] == "whisper.cpp"
    assert data["tts"]["service"] == "piper-tts"


def test_tts_synthesis_post():
    resp = client.post("/voice/tts", json={"text": "Hello KAI, testing voice output!"}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert len(resp.content) > 44
    assert resp.content[:4] == b"RIFF"


def test_tts_synthesis_get():
    resp = client.get("/voice/tts?text=Test+Voice", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert len(resp.content) > 44


def test_stt_transcription_upload():
    wav_data = generate_fallback_wav(duration_sec=0.5)
    files = {"file": ("test_recording.wav", io.BytesIO(wav_data), "audio/wav")}
    resp = client.post("/voice/stt", files=files, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data
    assert "status" in data
    assert data["status"] == "success"
