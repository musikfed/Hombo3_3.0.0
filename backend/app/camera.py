"""REGGO ONVIF camera: low-latency video, microphone, PTZ and autofocus.

The API exposes semantic PTZ directions (negative pan = left, positive pan =
right).  Vendor axis inversion is handled in one place through environment
settings, so UI, MCP and VectorProbe all agree on the same coordinate system.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from contextlib import suppress
from typing import AsyncIterator, Any
from urllib.parse import quote, urlsplit, urlunsplit

os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay",
)

import cv2

from .config import settings
from .database import log_event

logger = logging.getLogger(__name__)


def _read_attr(value: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(value, name)
    except Exception:
        return default


def _uri_with_credentials(uri: str) -> str:
    if not uri or not settings.camera_username:
        return uri
    parts = urlsplit(uri)
    if parts.username:
        return uri

    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parts.port:
        host = f"{host}:{parts.port}"

    user = quote(settings.camera_username, safe="")
    password = quote(settings.camera_password, safe="")
    auth = user if not password else f"{user}:{password}"
    return urlunsplit((parts.scheme, f"{auth}@{host}", parts.path, parts.query, parts.fragment))


class CameraHub:
    """One video connection shared by dashboard and local vision."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._condition = asyncio.Condition()
        self._latest_jpeg: bytes | None = None
        self._frame_id = 0
        self._last_frame_monotonic = 0.0

        self._video_stream_uri = ""
        self._audio_stream_uri = ""
        self._video_profile_token = ""
        self._audio_profile_token = ""
        self._video_source_token = ""
        self._source_width = 0
        self._source_height = 0
        self._output_width = 0
        self._output_height = 0
        self._connected = False
        self._last_error = ""
        self._active_video_backend = ""
        self._reconnects = 0

        self._ptz_service: Any | None = None
        self._ptz_profile_token = ""
        self._imaging_service: Any | None = None
        self._head_pan_deg = 0.0
        self._head_tilt_deg = 0.0
        self._autofocus_supported: bool | None = None
        self._autofocus_mode = "unknown"
        self._focus_error = ""

        self._audio_processes: set[asyncio.subprocess.Process] = set()
        self._video_process: asyncio.subprocess.Process | None = None

    @property
    def configured(self) -> bool:
        return bool(settings.camera_onvif_host or settings.camera_rtsp_url)

    async def start(self) -> None:
        if self._task is None and self.configured:
            self._stop_event.clear()
            self._task = asyncio.create_task(self._reader_loop(), name="reggo-camera-reader")

    def request_shutdown(self) -> None:
        self._stop_event.set()
        if self._video_process and self._video_process.returncode is None:
            with suppress(ProcessLookupError):
                self._video_process.terminate()
        for process in list(self._audio_processes):
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.terminate()

    async def stop(self) -> None:
        self.request_shutdown()
        async with self._condition:
            self._condition.notify_all()
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def status(self) -> dict[str, object]:
        age_ms = None
        if self._last_frame_monotonic:
            age_ms = round((time.monotonic() - self._last_frame_monotonic) * 1000.0)
        return {
            "configured": self.configured,
            "connected": self._connected,
            "video_profile_token": self._video_profile_token,
            "audio_profile_token": self._audio_profile_token,
            "profile_mode": settings.camera_profile_mode,
            "source_width": self._source_width,
            "source_height": self._source_height,
            "output_width": self._output_width,
            "output_height": self._output_height,
            "fps_limit": settings.camera_mjpeg_fps,
            "jpeg_quality": settings.camera_jpeg_quality,
            "video_backend": self._active_video_backend or settings.camera_video_backend,
            "rtsp_transport": settings.camera_rtsp_transport,
            "frame_age_ms": age_ms,
            "frame_id": self._frame_id,
            "reconnects": self._reconnects,
            "audio_enabled": settings.camera_audio_enabled,
            "audio_backend": self._ffmpeg_executable() or "",
            "error": self._last_error,
            "head_pan_deg": round(self._head_pan_deg, 1),
            "head_tilt_deg": round(self._head_tilt_deg, 1),
            "pan_invert": settings.camera_pan_invert,
            "tilt_invert": settings.camera_tilt_invert,
            "autofocus_requested": settings.camera_autofocus,
            "autofocus_supported": self._autofocus_supported,
            "autofocus_mode": self._autofocus_mode,
            "focus_error": self._focus_error,
        }

    @staticmethod
    def _profile_pixels(profile: Any) -> int:
        encoder = _read_attr(profile, "VideoEncoderConfiguration")
        resolution = _read_attr(encoder, "Resolution")
        width = int(_read_attr(resolution, "Width", 10_000) or 10_000)
        height = int(_read_attr(resolution, "Height", 10_000) or 10_000)
        return width * height

    @staticmethod
    def _stream_uri_for_profile(media: Any, profile: Any) -> str:
        request = media.create_type("GetStreamUri")
        request.StreamSetup = {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}
        request.ProfileToken = _read_attr(profile, "token")
        response = media.GetStreamUri(request)
        uri = str(_read_attr(response, "Uri", "") or "").strip()
        if not uri:
            raise RuntimeError("ONVIF GetStreamUri returned an empty URI")
        return _uri_with_credentials(uri)

    def _discover_stream_uris_sync(self) -> tuple[str, str]:
        if settings.camera_rtsp_url:
            manual = _uri_with_credentials(settings.camera_rtsp_url.strip())
            self._video_profile_token = "manual"
            self._audio_profile_token = "manual"
            return manual, manual
        if not settings.camera_onvif_host:
            raise RuntimeError("CAMERA_ONVIF_HOST is not configured")

        from onvif import ONVIFCamera

        camera = ONVIFCamera(
            settings.camera_onvif_host,
            settings.camera_onvif_port,
            settings.camera_username,
            settings.camera_password,
        )
        media = camera.create_media_service()
        profiles = list(media.GetProfiles() or [])
        if not profiles:
            raise RuntimeError("ONVIF camera returned no media profiles")

        mode = settings.camera_profile_mode.strip().lower()
        if mode == "high":
            video_profile = max(profiles, key=self._profile_pixels)
        elif mode.isdigit():
            video_profile = profiles[min(int(mode), len(profiles) - 1)]
        else:
            video_profile = min(profiles, key=self._profile_pixels)

        audio_profiles = [p for p in profiles if _read_attr(p, "AudioEncoderConfiguration") is not None]
        audio_profile = min(audio_profiles, key=self._profile_pixels) if audio_profiles else video_profile

        encoder = _read_attr(video_profile, "VideoEncoderConfiguration")
        resolution = _read_attr(encoder, "Resolution")
        self._source_width = int(_read_attr(resolution, "Width", 0) or 0)
        self._source_height = int(_read_attr(resolution, "Height", 0) or 0)
        self._video_profile_token = str(_read_attr(video_profile, "token", ""))
        self._audio_profile_token = str(_read_attr(audio_profile, "token", ""))

        source_config = _read_attr(video_profile, "VideoSourceConfiguration")
        self._video_source_token = str(_read_attr(source_config, "SourceToken", "") or "")

        ptz_profile = next((p for p in profiles if _read_attr(p, "PTZConfiguration") is not None), profiles[0])
        self._ptz_service = camera.create_ptz_service()
        self._ptz_profile_token = str(_read_attr(ptz_profile, "token", ""))
        try:
            self._imaging_service = camera.create_imaging_service()
        except Exception as exc:
            self._imaging_service = None
            self._autofocus_supported = False
            self._focus_error = str(exc)

        if settings.camera_autofocus and self._imaging_service is not None and self._video_source_token:
            try:
                self._set_autofocus_sync()
            except Exception as exc:
                self._focus_error = str(exc)
                logger.info("Camera autofocus is not available: %s", exc)

        video_uri = self._stream_uri_for_profile(media, video_profile)
        audio_uri = self._stream_uri_for_profile(media, audio_profile)
        log_event("INFO", "camera", "Separate ONVIF video and audio profiles selected", {
            "video_profile": self._video_profile_token,
            "audio_profile": self._audio_profile_token,
            "source_width": self._source_width,
            "source_height": self._source_height,
            "mode": mode or "low",
        })
        return video_uri, audio_uri

    async def _ensure_stream_uris(self, force: bool = False) -> None:
        if force:
            self._video_stream_uri = ""
            self._audio_stream_uri = ""
        if not self._video_stream_uri or not self._audio_stream_uri:
            video_uri, audio_uri = await asyncio.to_thread(self._discover_stream_uris_sync)
            self._video_stream_uri = video_uri
            self._audio_stream_uri = audio_uri

    async def _resolve_video_uri(self, force: bool = False) -> str:
        await self._ensure_stream_uris(force)
        return self._video_stream_uri

    async def _resolve_audio_uri(self, force: bool = False) -> str:
        await self._ensure_stream_uris(force)
        return self._audio_stream_uri or self._video_stream_uri

    @staticmethod
    def _open_capture(uri: str) -> cv2.VideoCapture:
        params: list[int] = []
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            params += [int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC), 4000]
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            params += [int(cv2.CAP_PROP_READ_TIMEOUT_MSEC), int(max(1000, settings.camera_stall_timeout_s * 1000))]
        try:
            cap = cv2.VideoCapture(uri, cv2.CAP_FFMPEG, params) if params else cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
        except Exception:
            cap = cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _encode_frame(self, frame: Any) -> bytes | None:
        height, width = frame.shape[:2]
        target_width = max(320, int(settings.camera_mjpeg_width))
        if width > target_width:
            scale = target_width / float(width)
            target_height = max(180, int(height * scale))
            frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
        self._output_height, self._output_width = frame.shape[:2]
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), max(35, min(90, int(settings.camera_jpeg_quality)))],
        )
        return encoded.tobytes() if ok else None

    async def _publish_jpeg(self, jpeg: bytes) -> None:
        self._last_frame_monotonic = time.monotonic()
        self._connected = True
        self._last_error = ""
        async with self._condition:
            self._latest_jpeg = jpeg
            self._frame_id += 1
            self._condition.notify_all()

    async def _opencv_reader_loop(self) -> None:
        self._active_video_backend = "opencv"
        cap: cv2.VideoCapture | None = None
        last_publish = 0.0
        min_interval = 1.0 / max(1.0, float(settings.camera_mjpeg_fps))
        refresh_uri = False
        try:
            while not self._stop_event.is_set():
                if cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    uri = await self._resolve_video_uri(force=refresh_uri)
                    refresh_uri = False
                    cap = await asyncio.to_thread(self._open_capture, uri)
                    if not cap.isOpened():
                        raise RuntimeError("OpenCV/FFmpeg could not open the camera stream")
                    self._connected = True
                    log_event("INFO", "camera", "Camera dashboard stream opened", self.status())

                ok, frame = await asyncio.to_thread(cap.read)
                if not ok or frame is None:
                    self._reconnects += 1
                    self._connected = False
                    self._last_error = "Camera frame read failed"
                    cap.release(); cap = None; refresh_uri = True
                    await asyncio.sleep(0.20)
                    continue

                now = time.monotonic()
                if now - last_publish < min_interval:
                    continue
                last_publish = now
                jpeg = await asyncio.to_thread(self._encode_frame, frame)
                if jpeg:
                    await self._publish_jpeg(jpeg)
        finally:
            if cap is not None:
                cap.release()

    @staticmethod
    def _ffmpeg_executable() -> str:
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return shutil.which("ffmpeg") or ""

    async def _stop_video_process(self) -> None:
        process = self._video_process
        self._video_process = None
        if process is None:
            return
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.terminate()
            with suppress(asyncio.TimeoutError, ProcessLookupError):
                await asyncio.wait_for(process.wait(), timeout=0.8)
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            with suppress(asyncio.TimeoutError, ProcessLookupError):
                await asyncio.wait_for(process.wait(), timeout=0.5)

    async def _ffmpeg_reader_loop(self) -> None:
        ffmpeg = self._ffmpeg_executable()
        if not ffmpeg:
            raise RuntimeError("FFmpeg video backend requested but FFmpeg is unavailable")
        self._active_video_backend = "ffmpeg-pipe"
        refresh_uri = False
        # In AUTO mode, an FFmpeg executable may exist but still be incompatible
        # with a particular camera/profile. If FFmpeg cannot produce even one
        # frame, bubble the error up so _reader_loop() can fall back to the
        # proven OpenCV reader instead of reconnecting forever on a blank UI.
        any_frame_published = False
        transport = settings.camera_rtsp_transport.strip().lower()
        if transport not in {"tcp", "udp", "udp_multicast", "http", "https"}:
            transport = "tcp"

        while not self._stop_event.is_set():
            uri = await self._resolve_video_uri(force=refresh_uri)
            refresh_uri = False
            width = max(320, int(settings.camera_mjpeg_width))
            fps = max(1.0, float(settings.camera_mjpeg_fps))
            quality = max(2, min(18, round((100 - max(35, min(90, int(settings.camera_jpeg_quality)))) / 5)))
            command = [
                ffmpeg, "-hide_banner", "-loglevel", "error",
                "-rtsp_transport", transport,
                "-fflags", "nobuffer", "-flags", "low_delay",
                "-probesize", "32768", "-analyzeduration", "200000",
                "-i", uri, "-an",
                "-vf", f"fps={fps:g},scale={width}:-2",
                "-q:v", str(quality), "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
            ]
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._video_process = process
            buffer = bytearray()
            log_event("INFO", "camera", "FFmpeg low-latency camera stream opened", {
                "backend": self._active_video_backend, "transport": transport, "width": width, "fps": fps,
            })
            try:
                assert process.stdout is not None
                while not self._stop_event.is_set():
                    try:
                        chunk = await asyncio.wait_for(
                            process.stdout.read(65536),
                            timeout=max(1.0, float(settings.camera_stall_timeout_s)),
                        )
                    except asyncio.TimeoutError as exc:
                        raise RuntimeError(f"Camera stream stalled for {settings.camera_stall_timeout_s:g}s") from exc
                    if not chunk:
                        detail = ""
                        if process.stderr is not None:
                            with suppress(Exception):
                                detail = (await asyncio.wait_for(process.stderr.read(4096), timeout=0.2)).decode(errors="replace").strip()
                        raise RuntimeError("FFmpeg camera stream ended" + (f": {detail}" if detail else ""))
                    buffer.extend(chunk)
                    while True:
                        start = buffer.find(b"\xff\xd8")
                        if start < 0:
                            if len(buffer) > 2_000_000:
                                del buffer[:-2]
                            break
                        end = buffer.find(b"\xff\xd9", start + 2)
                        if end < 0:
                            if start > 0:
                                del buffer[:start]
                            break
                        jpeg = bytes(buffer[start:end + 2])
                        del buffer[:end + 2]
                        self._output_width = width
                        await self._publish_jpeg(jpeg)
                        any_frame_published = True
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected = False
                self._last_error = str(exc)
                self._reconnects += 1
                log_event("WARNING", "camera", "Camera video stream restarted", {
                    "error": str(exc), "reconnects": self._reconnects, "backend": self._active_video_backend,
                })
                # Crucial AUTO fallback: if FFmpeg never yielded a frame, it is
                # not a usable backend for this camera/profile. Let the caller
                # switch to OpenCV. Once FFmpeg has proven itself, stalls are
                # handled by reconnecting FFmpeg as before.
                if not any_frame_published:
                    raise
                refresh_uri = True
            finally:
                await self._stop_video_process()
            if not self._stop_event.is_set():
                await asyncio.sleep(0.25)

    async def _reader_loop(self) -> None:
        backend = settings.camera_video_backend.strip().lower()
        try:
            if backend in {"ffmpeg", "ffmpeg_pipe", "auto"} and self._ffmpeg_executable():
                try:
                    await self._ffmpeg_reader_loop()
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if backend != "auto":
                        raise
                    log_event("WARNING", "camera", "FFmpeg video backend failed; using OpenCV fallback", {"error": str(exc)})
            await self._opencv_reader_loop()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._connected = False
            self._last_error = str(exc)
            log_event("ERROR", "camera", "Camera reader stopped", {"error": str(exc)})
        finally:
            self._connected = False

    async def latest_jpeg(self) -> bytes | None:
        return self._latest_jpeg

    async def jpeg_stream(self) -> AsyncIterator[bytes]:
        """Yield only the newest JPEG frame; never queue historical frames."""
        last_id = -1
        try:
            while not self._stop_event.is_set():
                async with self._condition:
                    try:
                        await asyncio.wait_for(
                            self._condition.wait_for(lambda: self._frame_id != last_id or self._stop_event.is_set()),
                            timeout=0.5,
                        )
                    except asyncio.TimeoutError:
                        continue
                    if self._stop_event.is_set():
                        return
                    last_id = self._frame_id
                    jpeg = self._latest_jpeg
                if jpeg:
                    yield jpeg
        except (asyncio.CancelledError, GeneratorExit):
            return

    async def mjpeg_stream(self) -> AsyncIterator[bytes]:
        # Kept as a compatibility/diagnostic fallback. The dashboard uses the
        # binary WebSocket path because browsers can buffer multipart MJPEG.
        async for jpeg in self.jpeg_stream():
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\nCache-Control: no-cache\r\n\r\n"
                + jpeg + b"\r\n"
            )

    async def audio_stream(self) -> AsyncIterator[bytes]:
        if not settings.camera_audio_enabled:
            raise RuntimeError("Camera microphone relay is disabled")
        ffmpeg = self._ffmpeg_executable()
        if not ffmpeg:
            raise RuntimeError("FFmpeg is not installed in the project environment")
        uri = await self._resolve_audio_uri()
        transport = settings.camera_rtsp_transport.strip().lower()
        if transport not in {"tcp", "udp", "udp_multicast", "http", "https"}:
            transport = "tcp"
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-fflags", "nobuffer", "-flags", "low_delay",
            "-rtsp_transport", transport, "-i", uri,
            "-vn", "-ac", "1", "-ar", "16000", "-codec:a", "libmp3lame", "-b:a", "64k", "-f", "mp3", "pipe:1",
        ]
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        self._audio_processes.add(process)
        log_event("INFO", "camera", "Camera microphone stream requested", {})
        try:
            assert process.stdout is not None
            while not self._stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(process.stdout.read(8192), timeout=0.75)
                except asyncio.TimeoutError:
                    continue
                if not chunk:
                    break
                yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            return
        finally:
            self._audio_processes.discard(process)
            if process.returncode is None:
                with suppress(ProcessLookupError): process.terminate()
                with suppress(asyncio.TimeoutError, ProcessLookupError): await asyncio.wait_for(process.wait(), timeout=0.8)
            if process.returncode is None:
                with suppress(ProcessLookupError): process.kill()
                with suppress(asyncio.TimeoutError, ProcessLookupError): await asyncio.wait_for(process.wait(), timeout=0.5)

    def _set_autofocus_sync(self) -> dict[str, object]:
        if self._imaging_service is None or not self._video_source_token:
            if not settings.camera_onvif_host:
                raise RuntimeError("CAMERA_ONVIF_HOST is not configured")
            self._discover_stream_uris_sync()
        imaging = self._imaging_service
        if imaging is None or not self._video_source_token:
            self._autofocus_supported = False
            raise RuntimeError("ONVIF Imaging/Focus service is unavailable; camera may have fixed focus")
        try:
            request = imaging.create_type("SetImagingSettings")
            request.VideoSourceToken = self._video_source_token
            request.ImagingSettings = {"Focus": {"AutoFocusMode": "AUTO"}}
            request.ForcePersistence = True
            imaging.SetImagingSettings(request)
            self._autofocus_supported = True
            self._autofocus_mode = "AUTO"
            self._focus_error = ""
            log_event("INFO", "camera", "ONVIF autofocus enabled", {"video_source_token": self._video_source_token})
            return {"ok": True, "supported": True, "mode": "AUTO"}
        except Exception as exc:
            self._autofocus_supported = False
            self._autofocus_mode = "unsupported"
            self._focus_error = str(exc)
            raise RuntimeError(f"Camera does not expose ONVIF autofocus: {exc}") from exc

    async def autofocus(self) -> dict[str, object]:
        return await asyncio.to_thread(self._set_autofocus_sync)

    def _ptz_move_sync(self, pan: float, tilt: float, timeout_s: float) -> None:
        if not settings.camera_onvif_host:
            raise RuntimeError("CAMERA_ONVIF_HOST is not configured")
        if self._ptz_service is None or not self._ptz_profile_token:
            self._discover_stream_uris_sync()
        ptz = self._ptz_service
        if ptz is None or not self._ptz_profile_token:
            raise RuntimeError("ONVIF PTZ service is unavailable")

        request = ptz.create_type("ContinuousMove")
        request.ProfileToken = self._ptz_profile_token
        request.Velocity = {"PanTilt": {"x": pan, "y": tilt}}
        ptz.ContinuousMove(request)
        time.sleep(timeout_s)

        stop = ptz.create_type("Stop")
        stop.ProfileToken = self._ptz_profile_token
        stop.PanTilt = True
        stop.Zoom = False
        ptz.Stop(stop)

    async def ptz_move(self, pan: float, tilt: float, zoom: float = 0.0) -> None:
        del zoom
        # pan/tilt here are semantic robot coordinates. Vendor inversion happens
        # only for the ONVIF command, while VectorProbe keeps semantic angles.
        pan = max(-1.0, min(1.0, pan))
        tilt = max(-1.0, min(1.0, tilt))
        device_pan = -pan if settings.camera_pan_invert else pan
        device_tilt = -tilt if settings.camera_tilt_invert else tilt
        await asyncio.to_thread(self._ptz_move_sync, device_pan, device_tilt, 0.30)
        half_pan = max(1.0, float(settings.head_pan_range_deg) / 2.0)
        self._head_pan_deg = max(-half_pan, min(half_pan, self._head_pan_deg + pan * float(settings.head_ptz_step_deg)))
        self._head_tilt_deg = max(-90.0, min(90.0, self._head_tilt_deg + tilt * float(settings.head_ptz_step_deg)))
        log_event("INFO", "camera", "ONVIF pan/tilt move", {
            "pan": pan, "tilt": tilt, "device_pan": device_pan, "device_tilt": device_tilt,
            "head_pan_deg": self._head_pan_deg,
        })


camera_hub = CameraHub()
