"""Windows SAPI TTS through pyttsx3, converted to PCM for MAX98357A.

This module intentionally stays on the Acer laptop. ESP32 receives only raw PCM,
which keeps the firmware compact and avoids a speech engine in flash.
"""
from __future__ import annotations

import asyncio
import tempfile
import wave
from pathlib import Path

import pyttsx3


def _render_wav_sync(text: str, rate_delta: int) -> tuple[bytes, int]:
    with tempfile.TemporaryDirectory(prefix="robot_tts_") as temp_dir:
        wav_path = Path(temp_dir) / "speech.wav"
        engine = pyttsx3.init()
        current_rate = int(engine.getProperty("rate"))
        engine.setProperty("rate", max(80, min(320, current_rate + rate_delta * 10)))
        engine.save_to_file(text, str(wav_path))
        engine.runAndWait()
        engine.stop()

        with wave.open(str(wav_path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frames = wav_file.readframes(wav_file.getnframes())

        if channels != 1 or width != 2:
            raise RuntimeError(
                f"TTS WAV must be mono 16-bit PCM; got channels={channels}, width={width}. "
                "Select a Windows SAPI voice that saves PCM WAV."
            )
        return frames, sample_rate


async def render_pcm(text: str, rate_delta: int = 0) -> tuple[bytes, int]:
    return await asyncio.to_thread(_render_wav_sync, text, rate_delta)
