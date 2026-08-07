import os
import logging
import urllib.request
import numpy as np
import onnxruntime as ort
from app.config import settings

logger = logging.getLogger(__name__)

SILERO_VAD_URL = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
DEFAULT_MODEL_PATH = os.path.join(settings.MODELS_DIR, "silero_vad.onnx")


class SileroVAD:
    def __init__(self, model_path: str = DEFAULT_MODEL_PATH, threshold: float = 0.5):
        self.model_path = model_path
        self.threshold = threshold
        self.session = None
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)
        self.sample_rate = 16000
        self.window_size_samples = 512  # 32ms at 16kHz
        self.load_time_ms = 0.0
        self.last_inference_ms = 0.0
        self.init_model()

    def init_model(self):
        import time
        t0 = time.perf_counter()
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        if not os.path.exists(self.model_path):
            logger.info(f"Downloading Silero VAD model to {self.model_path}...")
            try:
                urllib.request.urlretrieve(SILERO_VAD_URL, self.model_path)
            except Exception as e:
                logger.error(f"Failed to download Silero VAD ONNX model: {e}")
                raise RuntimeError(f"Silero VAD model missing at {self.model_path} and download failed: {e}")

        try:
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 1
            self.session = ort.InferenceSession(self.model_path, opts, providers=["CPUExecutionProvider"])
            self.reset_state()
            self.load_time_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(f"Silero VAD loaded in {self.load_time_ms:.2f}ms")
        except Exception as e:
            logger.error(f"Failed to initialize Silero VAD ONNX session: {e}")
            raise RuntimeError(f"ONNX runtime mismatch or corrupt model at {self.model_path}: {e}")

    def reset_state(self):
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)

    def is_speech(self, pcm_data: bytes) -> bool:
        """
        Takes raw 16-bit 16kHz mono PCM bytes.
        Returns True if speech probability > threshold.
        """
        import time
        t0 = time.perf_counter()
        if len(pcm_data) == 0:
            return False

        # Convert 16-bit PCM bytes to float32 numpy array [-1.0, 1.0]
        audio_int16 = np.frombuffer(pcm_data, dtype=np.int16)
        if len(audio_int16) == 0:
            return False
            
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        # Reshape to [1, samples]
        tensor = np.expand_dims(audio_float32, axis=0)

        try:
            # Inputs expected by Silero VAD v4: input, sr, h, c
            inputs = {
                "input": tensor,
                "sr": np.array(self.sample_rate, dtype=np.int64),
                "h": self._h,
                "c": self._c,
            }
            out, self._h, self._c = self.session.run(None, inputs)
            prob = float(out[0][0])
            self.last_inference_ms = (time.perf_counter() - t0) * 1000.0
            return prob >= self.threshold
        except Exception as e:
            # Silero VAD v5 input format fallback: input, sr
            try:
                inputs = {
                    "input": tensor,
                    "sr": np.array(self.sample_rate, dtype=np.int64)
                }
                out = self.session.run(None, inputs)
                prob = float(out[0][0])
                self.last_inference_ms = (time.perf_counter() - t0) * 1000.0
                return prob >= self.threshold
            except Exception as ex:
                logger.warning(f"Silero VAD inference error: {ex}, falling back to energy VAD")
                energy = np.sqrt(np.mean(audio_float32 ** 2))
                self.last_inference_ms = (time.perf_counter() - t0) * 1000.0
                return bool(energy > 0.02)
