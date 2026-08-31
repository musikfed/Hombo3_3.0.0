"""Hombo3 local camera diagnostic.

Checks the local ONVIF/RTSP path only. It does not use Tuya/Smart-Life cloud P2P.
Credentials are never printed.
"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.camera import camera_hub  # noqa: E402


def tcp_check(host: str, port: int, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "open"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def safe_uri(uri: str) -> str:
    if not uri:
        return ""
    p = urlsplit(uri)
    host = p.hostname or ""
    if p.port:
        host = f"{host}:{p.port}"
    return urlunsplit((p.scheme, host, p.path, p.query, p.fragment))


def main() -> int:
    print("Hombo3 camera diagnostic")
    print(f"APP endpoint     : http://127.0.0.1:{settings.app_port}")
    print(f"ONVIF camera     : {settings.camera_onvif_host}:{settings.camera_onvif_port}")
    print(f"video backend    : {settings.camera_video_backend}")
    print(f"RTSP transport   : {settings.camera_rtsp_transport}")
    print()

    if not settings.camera_onvif_host and not settings.camera_rtsp_url:
        print("FAIL: camera is not configured")
        return 2

    if settings.camera_onvif_host:
        ok, detail = tcp_check(settings.camera_onvif_host, int(settings.camera_onvif_port))
        print(f"ONVIF TCP        : {'OK' if ok else 'FAIL'} ({detail})")
        ok554, detail554 = tcp_check(settings.camera_onvif_host, 554)
        print(f"RTSP TCP 554     : {'OK' if ok554 else 'WARN'} ({detail554})")

    try:
        video_uri, audio_uri = camera_hub._discover_stream_uris_sync()
        print(f"ONVIF discovery  : OK")
        print(f"video URI        : {safe_uri(video_uri)}")
        print(f"audio URI        : {safe_uri(audio_uri)}")
    except Exception as exc:
        print(f"ONVIF discovery  : FAIL ({type(exc).__name__}: {exc})")
        if settings.camera_rtsp_url:
            print("Manual CAMERA_RTSP_URL is configured; ONVIF discovery is optional for video.")
        return 3

    try:
        cap = camera_hub._open_capture(video_uri)
        try:
            if not cap.isOpened():
                print("video frame       : FAIL (OpenCV could not open RTSP)")
                return 4
            deadline = time.monotonic() + 6.0
            frame = None
            while time.monotonic() < deadline:
                ok, candidate = cap.read()
                if ok and candidate is not None:
                    frame = candidate
                    break
            if frame is None:
                print("video frame       : FAIL (no frame within 6 s)")
                return 5
            h, w = frame.shape[:2]
            print(f"video frame       : OK ({w}x{h})")
        finally:
            cap.release()
    except Exception as exc:
        print(f"video frame       : FAIL ({type(exc).__name__}: {exc})")
        return 6

    print()
    print("LOCAL CAMERA PATH OK")
    print("If the vendor/Tuya app still shows 'failed to establish encrypted channel',")
    print("that is its cloud/P2P path and is separate from Hombo3 local ONVIF/RTSP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
