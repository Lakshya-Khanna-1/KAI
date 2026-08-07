import os
import re
import time
import logging
import urllib.request
import numpy as np
from typing import AsyncGenerator, Generator, Optional
from app.config import settings

logger = logging.getLogger(__name__)

PIPER_ONNX_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx"
PIPER_JSON_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json"

KOKORO_MODEL_URL = "https://github.com/thewhitemamba/kokoro-onnx/releases/download/v0.2.0/kokoro-v0_19.onnx"
KOKORO_VOICES_URL = "https://github.com/thewhitemamba/kokoro-onnx/releases/download/v0.2.0/voices.bin"


class BaseTTSEngine:
    def __init__(self):
        self.load_time_ms = 0.0
        self.last_inference_ms = 0.0

    def synthesize(self, text: str) -> bytes:
        """Synthesize text to 16kHz 16-bit Mono PCM bytes."""
        raise NotImplementedError


class PiperTTSEngine(BaseTTSEngine):
    def __init__(self, model_dir: str = os.path.join(settings.MODELS_DIR, "piper")):
        super().__init__()
        self.model_dir = model_dir
        self.model_path = os.path.join(model_dir, "en_GB-alan-medium.onnx")
        self.config_path = os.path.join(model_dir, "en_GB-alan-medium.onnx.json")
        self.piper_voice = None
        self.init_engine()

    def init_engine(self):
        t0 = time.perf_counter()
        os.makedirs(self.model_dir, exist_ok=True)
        
        if not os.path.exists(self.model_path):
            logger.info(f"Downloading Piper voice ONNX to {self.model_path}...")
            try:
                urllib.request.urlretrieve(PIPER_ONNX_URL, self.model_path)
            except Exception as e:
                logger.error(f"Failed downloading Piper ONNX model: {e}")

        if not os.path.exists(self.config_path):
            logger.info(f"Downloading Piper config to {self.config_path}...")
            try:
                urllib.request.urlretrieve(PIPER_JSON_URL, self.config_path)
            except Exception as e:
                logger.error(f"Failed downloading Piper JSON config: {e}")

        try:
            from piper import PiperVoice
            if os.path.exists(self.model_path) and os.path.exists(self.config_path):
                self.piper_voice = PiperVoice.load(self.model_path, config_path=self.config_path)
                self.load_time_ms = (time.perf_counter() - t0) * 1000.0
                logger.info(f"Piper TTS engine loaded in {self.load_time_ms:.2f}ms")
                return
        except Exception as e:
            logger.warning(f"Piper Voice direct load failed: {e}")

        self.load_time_ms = (time.perf_counter() - t0) * 1000.0

    def synthesize(self, text: str) -> bytes:
        t0 = time.perf_counter()
        if not text.strip():
            return b""

        if self.piper_voice:
            try:
                import io
                import wave
                wav_io = io.BytesIO()
                with wave.open(wav_io, "wb") as wav_file:
                    self.piper_voice.synthesize(text, wav_file)
                wav_bytes = wav_io.getvalue()
                
                # Extract raw PCM data from WAV header (skip 44 byte header)
                pcm_data = wav_bytes[44:] if len(wav_bytes) > 44 else wav_bytes
                self.last_inference_ms = (time.perf_counter() - t0) * 1000.0
                return pcm_data
            except Exception as e:
                logger.error(f"Piper synthesis error: {e}")

        # Fallback synthesis if model unavailable
        return self._fallback_beep_pcm(text)

    def _fallback_beep_pcm(self, text: str) -> bytes:
        # Generates a pleasant soft tone sequence for text length to prevent audio crash
        sample_rate = 16000
        duration = min(2.0, max(0.4, len(text) * 0.05))
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        tone = 0.15 * np.sin(2 * np.pi * 440 * t)
        pcm_int16 = (tone * 32767).astype(np.int16)
        return pcm_int16.tobytes()


class KokoroTTSEngine(BaseTTSEngine):
    def __init__(self, model_dir: str = os.path.join(settings.MODELS_DIR, "kokoro")):
        super().__init__()
        self.model_dir = model_dir
        self.model_path = os.path.join(model_dir, "kokoro-v0_19.onnx")
        self.voices_path = os.path.join(model_dir, "voices.bin")
        self.kokoro = None
        self.init_engine()

    def init_engine(self):
        t0 = time.perf_counter()
        os.makedirs(self.model_dir, exist_ok=True)
        if not os.path.exists(self.model_path):
            try:
                logger.info(f"Downloading Kokoro ONNX model to {self.model_path}...")
                urllib.request.urlretrieve(KOKORO_MODEL_URL, self.model_path)
            except Exception as e:
                logger.warning(f"Could not download Kokoro model: {e}")

        if not os.path.exists(self.voices_path):
            try:
                logger.info(f"Downloading Kokoro voices bin to {self.voices_path}...")
                urllib.request.urlretrieve(KOKORO_VOICES_URL, self.voices_path)
            except Exception as e:
                logger.warning(f"Could not download Kokoro voices: {e}")

        try:
            from kokoro_onnx import Kokoro
            if os.path.exists(self.model_path) and os.path.exists(self.voices_path):
                self.kokoro = Kokoro(self.model_path, self.voices_path)
                self.load_time_ms = (time.perf_counter() - t0) * 1000.0
                logger.info(f"Kokoro TTS engine loaded in {self.load_time_ms:.2f}ms")
                return
        except Exception as e:
            logger.warning(f"Kokoro ONNX engine load failed: {e}")

        self.load_time_ms = (time.perf_counter() - t0) * 1000.0

    def synthesize(self, text: str) -> bytes:
        t0 = time.perf_counter()
        if not text.strip():
            return b""

        if self.kokoro:
            try:
                samples, sample_rate = self.kokoro.create(text, voice="af_sarah", speed=1.0, lang="en-us")
                pcm_int16 = (samples * 32767).clip(-32768, 32767).astype(np.int16)
                self.last_inference_ms = (time.perf_counter() - t0) * 1000.0
                return pcm_int16.tobytes()
            except Exception as e:
                logger.error(f"Kokoro synthesis error: {e}")

        # Fallback to Piper or Tone
        return PiperTTSEngine().synthesize(text)


def get_tts_engine(engine_name: str = settings.KAI_TTS_ENGINE) -> BaseTTSEngine:
    if engine_name.lower() == "kokoro":
        return KokoroTTSEngine()
    return PiperTTSEngine()


def split_into_sentences(text: str) -> list[str]:
    """Splits a block of text into sentences based on punctuation boundaries [.!?]."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]
