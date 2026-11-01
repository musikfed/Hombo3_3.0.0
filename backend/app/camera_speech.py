"""Opt-in microphone speech capture from T23N RTSP and transcription on CORE.

Hombo3 is a Windows app. It requests one short microphone clip from RTSP,
converts it to PCM16 WAV on Acer (never on ESP32), then calls an explicitly
configured OpenAI-compatible Whisper transcription endpoint on the trusted
GPU/LLM host. No always-on recording. No stored audio clips.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
from io import BytesIO
import secrets
from urllib.parse import urlsplit
import wave

import httpx

from .camera import camera_hub
from .config import settings

_MAX_PCM_BYTES = 640_000
_CAPTURE_LOCK = asyncio.Lock()


def require_operator_token(supplied: str) -> None:
    if not settings.camera_voice_enabled:
        raise RuntimeError("Camera voice input is disabled; opt in with CAMERA_VOICE_ENABLED=true")
    expected = settings.camera_voice_access_token
    if len(expected) < 20 or not secrets.compare_digest(supplied, expected):
        raise PermissionError("Camera voice token is missing or invalid")


def as_wav(pcm: bytes, sample_rate: int = 16_000) -> bytes:
    """Construct a proper finite RIFF/WAV length (FFmpeg pipe.wav does not)."""
    if not pcm or len(pcm) > _MAX_PCM_BYTES or len(pcm) % 2:
        raise RuntimeError("Invalid PCM16 mono capture")
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return output.getvalue()


async def capture_camera_wav(seconds: int | None = None) -> bytes:
    ffmpeg = camera_hub._ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("FFmpeg unavailable; install FFmpeg on Acer Windows")
    seconds = min(10, max(2, int(seconds or settings.camera_voice_clip_seconds)))
    uri = await camera_hub._resolve_audio_uri()
    if not uri:
        raise RuntimeError("RTSP audio URL unavailable")

    # Exactly one input track. If microphone is not published to RTSP the
    # command fails instead of returning silent footage or video frames.
    cmd = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp", "-i", uri,
        "-map", "0:a:0", "-vn", "-t", str(seconds),
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        "-f", "s16le", "pipe:1",
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        pcm, error = await asyncio.wait_for(
            process.communicate(), timeout=seconds+12,
        )
    except (asyncio.CancelledError, asyncio.TimeoutError):
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        raise
    if process.returncode != 0:
        # FFmpeg may include the RTSP URL (with passwords) in stderr.
        raise RuntimeError("Cannot capture T23N microphone RTSP audio; verify ffprobe audio track")
    if not pcm:
        raise RuntimeError("RTSP returned zero microphone samples")
    return as_wav(pcm)


async def transcribe_camera(seconds: int | None = None) -> str:
    if not settings.camera_voice_enabled:
        raise RuntimeError("Camera voice input disabled")
    url = settings.camera_stt_url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
        raise RuntimeError("Configure a trusted HTTP(S) CAMERA_STT_URL in local .env")
    if not settings.camera_audio_enabled:
        raise RuntimeError("RTSP microphone audio is disabled")
    if _CAPTURE_LOCK.locked():
        raise RuntimeError("Another camera speech capture is running")

    async with _CAPTURE_LOCK:
        wav = await capture_camera_wav(seconds)
        headers = {}
        if settings.camera_stt_api_key:
            headers["Authorization"] = "Bearer " + settings.camera_stt_api_key
        async with httpx.AsyncClient(timeout=40.0, trust_env=False) as client:
            response = await client.post(
                url, headers=headers,
                data={"model": settings.camera_stt_model,
                      "language": settings.camera_stt_language},
                files={"file": ("camera.wav", wav, "audio/wav")},
            )
            response.raise_for_status()
            obj = response.json()
        if not isinstance(obj, dict) or not isinstance(obj.get("text"), str):
            raise RuntimeError("STT service did not return a JSON 'text' field")
        return " ".join(obj["text"].split())[:3000]
