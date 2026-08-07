import logging
import numpy as np
from app.config import settings

logger = logging.getLogger(__name__)

try:
    from pedalboard import Pedalboard, PitchShift, Reverb, Bitcrush, HighpassFilter
    HAS_PEDALBOARD = True
except ImportError:
    HAS_PEDALBOARD = False
    logger.warning("Pedalboard package not available. Using NumPy/SciPy fallback for voice FX.")


class VoiceCharacterFX:
    def __init__(self, profile_name: str = settings.VOICE_PROFILE, sample_rate: int = 16000):
        self.profile_name = profile_name
        self.sample_rate = sample_rate
        self.board = None
        self.init_profile()

    def init_profile(self):
        if HAS_PEDALBOARD:
            if self.profile_name == "cold":
                # Cold preset: pitch shift -3 semitones, subtle reverb, clean bitcrush
                self.board = Pedalboard([
                    PitchShift(semitones=-3.0),
                    Reverb(room_size=0.15, damping=0.5, wet_level=0.12, dry_level=0.88),
                    Bitcrush(bit_depth=14.0),
                    HighpassFilter(cutoff_frequency_hz=80.0)
                ])
            else:
                # Default subtle profile
                self.board = Pedalboard([
                    PitchShift(semitones=-2.0),
                    Reverb(room_size=0.1, wet_level=0.08, dry_level=0.92)
                ])

    def process_pcm(self, pcm_bytes: bytes) -> bytes:
        """
        Process 16-bit Mono 16kHz PCM audio bytes through the character FX chain.
        Returns modified 16-bit PCM audio bytes.
        """
        if not pcm_bytes or len(pcm_bytes) == 0:
            return b""

        # Convert int16 PCM to float32 [-1.0, 1.0]
        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        if len(audio_int16) == 0:
            return b""

        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        if HAS_PEDALBOARD and self.board:
            try:
                # Pedalboard expects 2D array [channels, samples]
                input_2d = np.expand_dims(audio_float32, axis=0)
                output_2d = self.board(input_2d, sample_rate=self.sample_rate)
                processed_float32 = output_2d[0]
                processed_int16 = (processed_float32 * 32767).clip(-32768, 32767).astype(np.int16)
                return processed_int16.tobytes()
            except Exception as e:
                logger.error(f"Pedalboard FX processing error: {e}")

        # NumPy/SciPy fallback FX processing for 'cold' profile
        return self._fallback_dsp_cold(audio_float32)

    def _fallback_dsp_cold(self, audio_float32: np.ndarray) -> bytes:
        try:
            from scipy import signal
            # Simple resampling to pitch shift down ~3 semitones (ratio ~ 0.84)
            shift_ratio = 0.841
            new_length = int(len(audio_float32) / shift_ratio)
            shifted = signal.resample(audio_float32, new_length)
            
            # Simple short delay reverb blend
            delay_samples = int(self.sample_rate * 0.04) # 40ms
            reverb_out = np.copy(shifted)
            if len(shifted) > delay_samples:
                reverb_out[delay_samples:] += 0.15 * shifted[:-delay_samples]
                
            processed_int16 = (reverb_out * 32767).clip(-32768, 32767).astype(np.int16)
            return processed_int16.tobytes()
        except Exception:
            # Direct passthrough if scipy unavailable
            processed_int16 = (audio_float32 * 32767).clip(-32768, 32767).astype(np.int16)
            return processed_int16.tobytes()
