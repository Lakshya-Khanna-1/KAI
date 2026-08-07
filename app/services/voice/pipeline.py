import re
import time
import asyncio
import logging
import base64
from typing import Dict, Any, Optional, AsyncGenerator
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal
from app.db.models.voice_turn import VoiceTurn
from app.llm.client import ollama_client
from app.services.voice.vad import SileroVAD
from app.services.voice.stt import FasterWhisperSTT
from app.services.voice.tts import get_tts_engine, BaseTTSEngine
from app.services.voice.fx import VoiceCharacterFX

logger = logging.getLogger(__name__)


class StreamingVoicePipeline:
    def __init__(self):
        self.vad: Optional[SileroVAD] = None
        self.stt: Optional[FasterWhisperSTT] = None
        self.tts: Optional[BaseTTSEngine] = None
        self.fx: Optional[VoiceCharacterFX] = None
        self.is_warm: bool = False

    def warm_start(self):
        """Pre-loads VAD, STT, TTS, and FX models into memory at FastAPI startup."""
        if self.is_warm:
            return

        t0 = time.perf_counter()
        logger.info("Initializing KAI Voice Pipeline Warm Start...")

        try:
            self.vad = SileroVAD()
            self.stt = FasterWhisperSTT()
            self.tts = get_tts_engine()
            self.fx = VoiceCharacterFX()
            self.is_warm = True
            total_warm_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(f"KAI Voice Pipeline warm start completed in {total_warm_ms:.2f}ms")
        except Exception as e:
            logger.error(f"Voice Pipeline Warm Start failed: {e}")
            raise RuntimeError(f"Voice Pipeline Warm Start error: {e}")

    def get_health(self) -> Dict[str, Any]:
        """Returns per-stage load time and last inference timing in ms."""
        return {
            "status": "healthy" if self.is_warm else "uninitialized",
            "tts_engine": settings.KAI_TTS_ENGINE,
            "voice_profile": settings.VOICE_PROFILE,
            "stage_load_times_ms": {
                "vad": round(self.vad.load_time_ms, 2) if self.vad else 0.0,
                "stt": round(self.stt.load_time_ms, 2) if self.stt else 0.0,
                "tts": round(self.tts.load_time_ms, 2) if self.tts else 0.0,
            },
            "last_inference_ms": {
                "vad": round(self.vad.last_inference_ms, 2) if self.vad else 0.0,
                "stt": round(self.stt.last_inference_ms, 2) if self.stt else 0.0,
                "tts": round(self.tts.last_inference_ms, 2) if self.tts else 0.0,
            }
        }

    async def process_voice_turn(
        self,
        pcm_bytes: bytes,
        speech_end_time: float,
        system_prompt: str = "You are KAI, a concise and direct personal AI assistant. Reply in 1-2 short natural spoken sentences."
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Orchestrates STT -> Streaming LLM -> Sentence Chunked TTS -> FX -> Yielding websocket frames.
        Enforces latency budget and logs turn to voice_turns table.
        """
        if not self.is_warm:
            self.warm_start()

        # Target budgets (ms)
        TARGET_STT_MS = 400.0
        TARGET_LLM_FIRST_TOKEN_MS = 300.0
        TARGET_TTS_FIRST_AUDIO_MS = 300.0
        TARGET_TOTAL_PERCEIVED_MS = 1200.0

        # Stage 1: Speech End -> Final Transcript (STT)
        t_speech_end = speech_end_time
        try:
            transcript = self.stt.transcribe_pcm(pcm_bytes)
        except Exception as e:
            logger.error(f"STT pipeline error: {e}")
            yield {"type": "error", "stage": "stt", "message": str(e)}
            return

        t_transcript_done = time.perf_counter()
        stt_latency_ms = (t_transcript_done - t_speech_end) * 1000.0

        if not transcript or not transcript.strip():
            yield {"type": "info", "message": "No speech detected in turn"}
            return

        yield {
            "type": "transcript",
            "text": transcript,
            "stt_ms": round(stt_latency_ms, 2)
        }

        # Stage 2: Transcript -> First LLM Token & Sentence Generator
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript}
        ]

        t_llm_start = time.perf_counter()
        t_first_token: Optional[float] = None
        t_first_audio: Optional[float] = None

        full_response_text = ""
        sentence_buffer = ""

        try:
            llm_stream = await ollama_client.chat_completion(messages=messages, stream=True)
            async for token in llm_stream:
                if t_first_token is None:
                    t_first_token = time.perf_counter()

                full_response_text += token
                sentence_buffer += token

                # Split on sentence boundaries [.!?]
                match = re.search(r'([.!?])(?:\s+|$)', sentence_buffer)
                if match:
                    split_idx = match.end()
                    complete_sentence = sentence_buffer[:split_idx].strip()
                    sentence_buffer = sentence_buffer[split_idx:]

                    if complete_sentence:
                        # Synthesize sentence to audio & apply FX
                        pcm_tts = self.tts.synthesize(complete_sentence)
                        pcm_fx = self.fx.process_pcm(pcm_tts)

                        if t_first_audio is None:
                            t_first_audio = time.perf_counter()

                        audio_b64 = base64.b64encode(pcm_fx).decode('ascii')
                        yield {
                            "type": "audio_chunk",
                            "sentence": complete_sentence,
                            "audio_b64": audio_b64,
                            "sample_rate": 16000
                        }

            # Flush any remaining text in buffer after stream ends
            remaining_text = sentence_buffer.strip()
            if remaining_text:
                pcm_tts = self.tts.synthesize(remaining_text)
                pcm_fx = self.fx.process_pcm(pcm_tts)
                if t_first_audio is None:
                    t_first_audio = time.perf_counter()

                audio_b64 = base64.b64encode(pcm_fx).decode('ascii')
                yield {
                    "type": "audio_chunk",
                    "sentence": remaining_text,
                    "audio_b64": audio_b64,
                    "sample_rate": 16000
                }

        except Exception as e:
            logger.error(f"LLM/TTS streaming error: {e}")
            yield {"type": "error", "stage": "llm_tts", "message": str(e)}
            return

        # Timing Benchmarks Calculation
        llm_first_token_ms = ((t_first_token - t_transcript_done) * 1000.0) if t_first_token else 0.0
        tts_first_audio_ms = ((t_first_audio - t_first_token) * 1000.0) if (t_first_audio and t_first_token) else 0.0
        total_perceived_ms = ((t_first_audio - t_speech_end) * 1000.0) if t_first_audio else (time.perf_counter() - t_speech_end) * 1000.0

        # Latency Budget Evaluation & Warning Logging
        warning_stages = []
        if stt_latency_ms > TARGET_STT_MS:
            warning_stages.append(f"STT ({stt_latency_ms:.1f}ms > {TARGET_STT_MS}ms)")
        if llm_first_token_ms > TARGET_LLM_FIRST_TOKEN_MS:
            warning_stages.append(f"LLM First Token ({llm_first_token_ms:.1f}ms > {TARGET_LLM_FIRST_TOKEN_MS}ms)")
        if tts_first_audio_ms > TARGET_TTS_FIRST_AUDIO_MS:
            warning_stages.append(f"TTS First Audio ({tts_first_audio_ms:.1f}ms > {TARGET_TTS_FIRST_AUDIO_MS}ms)")
        if total_perceived_ms > TARGET_TOTAL_PERCEIVED_MS:
            warning_stages.append(f"Total Perceived ({total_perceived_ms:.1f}ms > {TARGET_TOTAL_PERCEIVED_MS}ms)")

        warning_msg = ", ".join(warning_stages) if warning_stages else None
        if warning_msg:
            logger.warning(f"[LATENCY BUDGET WARNING] Voice turn exceeded budget target: {warning_msg}")

        # Record Audit Turn to DB
        self._log_voice_turn(
            transcript=transcript,
            response_text=full_response_text,
            stt_ms=stt_latency_ms,
            llm_first_token_ms=llm_first_token_ms,
            tts_first_audio_ms=tts_first_audio_ms,
            total_ms=total_perceived_ms,
            exceeded_budget=bool(warning_stages),
            warning_stage=warning_msg
        )

        yield {
            "type": "turn_complete",
            "response_text": full_response_text,
            "timings_ms": {
                "stt": round(stt_latency_ms, 2),
                "llm_first_token": round(llm_first_token_ms, 2),
                "tts_first_audio": round(tts_first_audio_ms, 2),
                "total_perceived": round(total_perceived_ms, 2)
            },
            "budget_exceeded": bool(warning_stages),
            "warnings": warning_msg
        }

    def _log_voice_turn(
        self,
        transcript: str,
        response_text: str,
        stt_ms: float,
        llm_first_token_ms: float,
        tts_first_audio_ms: float,
        total_ms: float,
        exceeded_budget: bool,
        warning_stage: Optional[str]
    ):
        try:
            db: Session = SessionLocal()
            turn = VoiceTurn(
                transcript=transcript,
                response_text=response_text,
                stt_latency_ms=stt_ms,
                llm_first_token_ms=llm_first_token_ms,
                tts_first_audio_ms=tts_first_audio_ms,
                total_latency_ms=total_ms,
                exceeded_budget=exceeded_budget,
                warning_stage=warning_stage
            )
            db.add(turn)
            db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Failed logging voice turn to DB: {e}")


# Singleton instance
voice_pipeline = StreamingVoicePipeline()
