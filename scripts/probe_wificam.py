#!/usr/bin/env python3
"""Read-only PegineLab T23N connectivity/CGI/RTSP/microphone probe on the host.

No camera settings are changed. Uses stdlib + optional ffprobe.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import shutil
import socket
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(url: str, user: str, password: str) -> tuple[int, str, bytes]:
    req = Request(url, headers={"Cache-Control": "no-store"})
    if user:
        raw = f"{user}:{password}".encode("utf-8")
        req.add_header("Authorization", "Basic " + base64.b64encode(raw).decode())
    try:
        with urlopen(req, timeout=6) as res:
            return res.status, res.headers.get("Content-Type", ""), res.read(2_000_000)
    except HTTPError as err:
        return err.code, err.headers.get("Content-Type", ""), err.read(256)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default="192.168.1.55")
    ap.add_argument("--web-port", type=int, default=8090)
    ap.add_argument("--rtsp-port", type=int, default=554)
    ap.add_argument("--rtsp-path", default="ch0")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default=os.environ.get("WIFICAM_PASSWORD", ""))
    ap.add_argument("--rtsp-url", default="")
    args = ap.parse_args()

    if not args.password and args.user:
        args.password = getpass.getpass("WIFICAM Web UI password: ")

    print("T23N / Hombo3 connectivity probe (no changes to the camera)")
    for port, name in [(22, "SSH"), (80, "ONVIF/Thingino HTTP"), (args.web_port, "PegineLab"), (args.rtsp_port, "RTSP")]:
        try:
            with socket.create_connection((args.ip, port), timeout=2):
                print(f"  {name} TCP/{port}: reachable")
        except OSError:
            print(f"  {name} TCP/{port}: not reachable")

    base = f"http://{args.ip}:{args.web_port}"
    try:
        status, mime, body = request(base + "/cgi-bin/api?op=status", args.user, args.password)
        print(f"  Web API: HTTP {status}; {mime}")
        if body.startswith(b"#!"):
            print("  ERROR: BusyBox is exposing CGI source instead of executing it")
        elif body.lstrip().startswith(b"<"):
            print("  ERROR: HTML instead of JSON (authentication or CGI failure)")
        else:
            obj = json.loads(body)
            print(f"  API JSON: ok={obj.get('ok')}, camera={obj.get('camera')}")
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        print(f"  Web API failed: {exc}")

    try:
        status, mime, body = request(base + "/cgi-bin/snapshot.jpg", args.user, args.password)
        valid = status == 200 and body.startswith(b"\xff\xd8")
        print(f"  Snapshot: HTTP {status}; JPEG={valid}; bytes={len(body)}")
        if not valid:
            print("  Snapshot requires working CGI + Raptor RVD/RHD or camera snapshot command")
    except (URLError, TimeoutError, OSError) as exc:
        print(f"  Snapshot failed: {exc}")

    ffprobe = shutil.which("ffprobe")
    rtsp = args.rtsp_url or f"rtsp://{args.ip}:{args.rtsp_port}/{args.rtsp_path.lstrip('/')}"
    if ffprobe:
        print("  Probing RTSP tracks (may require separate RTSP credentials)...")
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-rtsp_transport", "tcp",
                 "-show_entries", "stream=codec_type,codec_name", "-of", "json", rtsp],
                capture_output=True, text=True, timeout=12, check=False,
            )
            if result.returncode == 0:
                tracks = json.loads(result.stdout).get("streams", [])
                print(f"  RTSP tracks: {tracks}")
                if not any(t.get("codec_type") == "audio" for t in tracks):
                    print("  Microphone NOT yet verified: no audio track in this RTSP response")
            else:
                print("  RTSP probe failed; check RSD, path and RTSP credentials")
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            print(f"  RTSP probe unavailable: {exc}")
    else:
        print("  ffprobe not installed; install FFmpeg to verify video/microphone tracks")
    print("  Speaker: requires separate SSH/play or RTSP-backchannel test; not proven by RTSP audio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
