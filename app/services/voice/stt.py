import os
import io
import time
import logging
import numpy as np
from faster_whisper import WhisperModel
from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL_SIZE = "small.en"


class FasterWhisperSTT:
    def __init__(self, model_size: str = DEFAULT_MODEL_SIZE, device: str = "cpu", compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None
        self.load_time_ms = 0.0
        self.last_inference_ms = 0.0
        self.download_root = os.path.join(settings.MODELS_DIR, "whisper")
        self.init_model()

    def init_model(self):
        t0 = time.perf_counter()
        os.makedirs(self.download_root, exist_ok=True)
        try:
            logger.info(f"Loading faster-whisper model '{self.model_size}' ({self.compute_type})...")
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.download_root,
                cpu_threads=4,
            )
            self.load_time_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(f"faster-whisper STT loaded in {self.load_time_ms:.2f}ms")
        except Exception as e:
            logger.error(f"Failed to load faster-whisper STT model: {e}")
            raise RuntimeError(f"STT Model loading failed for '{self.model_size}': {e}")

    def transcribe_pcm(self, pcm_bytes: bytes) -> str:
        """
        Transcribe 16-bit 16kHz mono PCM audio bytes.
        Returns clean string transcript.
        """
        t0 = time.perf_counter()
        if not pcm_bytes or len(pcm_bytes) == 0:
            return ""

        # Convert 16-bit int16 PCM to float32 numpy array
        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        if len(audio_int16) == 0:
            return ""

        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        try:
            segments, info = self.model.transcribe(
                audio_float32,
                beam_size=1,
                best_of=1,
                language="en",
                vad_filter=False,
                temperature=0.0,
            )
            text_parts = [segment.text.strip() for segment in segments if segment.text.strip()]
            result = " ".join(text_parts).strip()
            self.last_inference_ms = (time.perf_counter() - t0) * 1000.0
            return result
        except Exception as e:
            logger.error(f"STT transcription error: {e}")
            self.last_inference_ms = (time.perf_counter() - t0) * 1000.0
            raise RuntimeError(f"STT inference failed: {e}")
