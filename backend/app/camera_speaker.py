"""Optional PegineLab WIFICAM speaker output via Raptor rac/play over SSH.

No unauthenticated HTTP speaker endpoint is exposed on the camera. Requires
pre-provisioned SSH public-key access and a functioning 'play -s -r' command.
"""
from __future__ import annotations

import asyncio
import shutil

from .config import settings


async def send_pcm_to_camera(pcm: bytes, sample_rate: int) -> None:
    host = settings.camera_speaker_ssh_host.strip()
    user = settings.camera_speaker_ssh_user.strip()
    key = settings.camera_speaker_ssh_key.strip()
    if not host or not user:
        raise RuntimeError("CAMERA_SPEAKER_SSH_HOST/USER must be configured")
    if not all(c.isalnum() or c in ".-_" for c in host + user):
        raise RuntimeError("Invalid SSH hostname or username")
    if not (8000 <= sample_rate <= 48000):
        raise RuntimeError("Unsupported audio sample rate")
    if not pcm:
        return
    if len(pcm) > 12_000_000:
        raise RuntimeError("PCM payload exceeds 12MB speaker safety limit")
    exe = shutil.which("ssh")
    if not exe:
        raise RuntimeError("OpenSSH client is not installed")

    args = [
        exe, "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=4",
    ]
    if key:
        args += ["-i", key]
    args += [f"{user}@{host}", f"play -s -r {int(sample_rate)} -"]

    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(pcm), timeout=35)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise RuntimeError("Camera speaker timed out") from exc

    if process.returncode:
        detail = (stderr or b"").decode("utf-8", "replace").strip()[-600:]
        raise RuntimeError(f"Camera speaker SSH/play failed: {detail or process.returncode}")
