import os
import sys
import wave
import time
import asyncio
import logging

from app.services.voice.pipeline import voice_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice.selftest")


def check_environment():
    """Diagnoses common voice environment issues and prints clear user actionable errors."""
    issues = []
    
    # 1. Check ONNX Runtime
    try:
        import onnxruntime as ort
    except ImportError as e:
        issues.append(f"ONNX Runtime Mismatch / Missing: {e}. Please run `pip install onnxruntime`.")

    # 2. Check faster-whisper
    try:
        import faster_whisper
    except ImportError as e:
        issues.append(f"faster-whisper package missing: {e}. Please run `pip install faster-whisper`.")

    # 3. Check FFmpeg availability
    import shutil
    if not shutil.which("ffmpeg"):
        logger.warning("FFmpeg binary not found on system PATH. (faster-whisper will rely on direct array decoding).")

    return issues


async def run_selftest():
    print("=" * 60)
    print("      KAI VOICE PIPELINE DIAGNOSTIC SELFTEST (TASK 15 REDO)")
    print("=" * 60)

    env_issues = check_environment()
    if env_issues:
        print("\nENVIRONMENT SETUP ERRORS DETECTED:")
        for issue in env_issues:
            print(f"  [X] {issue}")
        print("\nSelf-test aborted due to missing dependencies.")
        sys.exit(1)

    wav_path = os.path.join(os.path.dirname(__file__), "test.wav")
    if not os.path.exists(wav_path):
        print(f"\n[X] Error: Bundled test file missing at {wav_path}")
        sys.exit(1)

    try:
        with wave.open(wav_path, "rb") as wf:
            n_channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            sampwidth = wf.getsampwidth()
            pcm_data = wf.readframes(wf.getnframes())

        if sample_rate != 16000 or n_channels != 1 or sampwidth != 2:
            print(f"\n[X] Error: Sample rate mismatch! Required: 16000Hz 1-channel 16-bit PCM. Found: {sample_rate}Hz {n_channels}-ch {sampwidth*8}-bit.")
            sys.exit(1)

        print(f"[+] Loaded test audio: {len(pcm_data)} bytes ({len(pcm_data)/(16000*2):.2f}s)")
    except Exception as e:
        print(f"\n[X] Error reading test WAV file: {e}")
        sys.exit(1)

    # Warm Start Pipeline
    t0_warm = time.perf_counter()
    try:
        print("[+] Initializing Warm Start (Loading Silero VAD, Whisper STT, Piper/Kokoro TTS, Pedalboard FX)...")
        voice_pipeline.warm_start()
        warm_ms = (time.perf_counter() - t0_warm) * 1000.0
        print(f"[+] Warm Start complete in {warm_ms:.2f}ms")
    except Exception as e:
        print(f"\n[X] Pipeline Warm Start Failed: {e}")
        sys.exit(1)

    # Run Voice Turn
    print("\n[+] Processing Voice Turn through Pipeline...")
    speech_end_time = time.perf_counter()
    turn_generator = voice_pipeline.process_voice_turn(
        pcm_bytes=pcm_data,
        speech_end_time=speech_end_time,
        system_prompt="Reply concisely: All systems operational."
    )

    results = {}
    try:
        async for frame in turn_generator:
            ftype = frame.get("type")
            if ftype == "transcript":
                print(f"  -> Transcript: '{frame.get('text')}' (STT Latency: {frame.get('stt_ms')}ms)")
            elif ftype == "audio_chunk":
                print(f"  -> Audio Frame Chunk: '{frame.get('sentence')}' ({len(frame.get('audio_b64', ''))} chars b64)")
            elif ftype == "turn_complete":
                results = frame.get("timings_ms", {})
                budget_exceeded = frame.get("budget_exceeded", False)
                warnings = frame.get("warnings")
            elif ftype == "error":
                print(f"\n[X] Pipeline Error during turn: {frame}")
                sys.exit(1)

    except Exception as e:
        print(f"\n[X] Unexpected Exception during pipeline run: {e}")
        sys.exit(1)

    # Print Timing Summary Table
    stt_ms = results.get("stt", 0.0)
    llm_ms = results.get("llm_first_token", 0.0)
    tts_ms = results.get("tts_first_audio", 0.0)
    total_ms = results.get("total_perceived", 0.0)

    print("\n" + "-" * 60)
    print("STAGE TIMING BREAKDOWN vs LATENCY BUDGET TARGETS")
    print("-" * 60)
    print(f"  {'STAGE':<32} | {'ACTUAL':<10} | {'TARGET':<10} | {'STATUS'}")
    print("-" * 60)

    stt_status = "PASS" if stt_ms <= 400.0 else "WARN"
    llm_status = "PASS" if llm_ms <= 300.0 else "WARN"
    tts_status = "PASS" if tts_ms <= 300.0 else "WARN"
    tot_status = "PASS" if total_ms <= 1200.0 else "WARN"

    print(f"  {'Speech End -> STT Transcript':<32} | {stt_ms:>7.1f} ms | {'400.0 ms':<10} | [{stt_status}]")
    print(f"  {'Transcript -> First LLM Token':<32} | {llm_ms:>7.1f} ms | {'300.0 ms':<10} | [{llm_status}]")
    print(f"  {'First Token -> First Audio Out':<32} | {tts_ms:>7.1f} ms | {'300.0 ms':<10} | [{tts_status}]")
    print("-" * 60)
    print(f"  {'TOTAL PERCEIVED LATENCY':<32} | {total_ms:>7.1f} ms | {'1200.0 ms':<10} | [{tot_status}]")
    print("-" * 60)

    print("\n[+] Health Status Report:")
    print(voice_pipeline.get_health())

    print("\n[+] VOICE PIPELINE DIAGNOSTIC SELFTEST COMPLETED SUCCESSFULLY!")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(run_selftest())
