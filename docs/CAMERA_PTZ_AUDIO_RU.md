# PegineLab T23N / Hombo3 — PTZ, orientation, focus and spoken dialog

> Updated 2026-11-01. Firmware baseline `0.1_test` is unchanged. New code is only in WIFICAM `mymarrchWFcam` and Hombo3 `main` until a fresh SD image boots and hardware is tested.

## 1. Physical camera features vs viewer effects

| Feature | WIFICAM :8090 | Hombo3 Windows on Acer | Hardware required |
|---|---|---|---|
| Pan/tilt | Bounded motor nudges using Thingino `motors` | ONVIF PTZ continuous pulse with STOP | Motors daemon and motor wiring |
| Invert pan/tilt | Persisted independently per axis | Persisted on Acer | Existing PTZ motor |
| Digital zoom | Browser transform ×1–×3 | Browser transform ×1–×2.5 | None; no optical change |
| Horizontal mirror | Browser-only checkbox | Browser-only checkbox | None |
| Vertical flip | Browser-only checkbox | Browser-only checkbox | None |
| 180° rotation | Enable both mirror and flip | Enable both mirror and flip | None |
| Optical zoom | Not reported as supported | ONVIF Zoom attempt, STOP even on error | Motorized zoom lens |
| Autofocus | Disabled when no focus driver | ONVIF Imaging SetImagingSettings Focus AUTO, non-persistent | Supported focusing mechanism |
| Manual focus | Not reported as supported | ONVIF Imaging Move near/far 0.2s with Stop | Focus actuator and Imaging endpoint |

**Caution:** Galayou G2 pinned Thingino board config advertises `BR2_THINGINO_MOTORS=y` and `BR2_THINGINO_AUDIO=y` but does **not** establish a focus actuator or optical-zoom hardware. The presence of focus APIs in Hombo3 must not be mistaken for proof of physical focus. Optical zoom is different from display zoom.

Mirror/flip in both web UIs is currently for **operator preview only**. No change is made to the raw RTSP feed, the YOLO input, recorded video, neural vision coordinates or PTZ direction. If an actual sensor-level flip is later required for both Hombo3 and the recordings, validate the Thingino ISP/Raptor sensor controls on real hardware first; an unverified `raptorctl` flip operation must not silently change motor semantics.

Recommended acceptance: choose one visible object, move pan LEFT, confirm actual movement and adjust pan inversion if needed; repeat for tilt UP; verify STOP/no runaway; test mirror/flip with RTSP and YOLO unchanged; focus near/far and autofocus only with visible focus hardware confirmed.

## 2. Why camera microphone and speaker unload ESP32

```text
T23N mic (if physically connected and enabled)
     |  Thingino rad + rsd -> RTSP audio track
     v
Acer Windows 11 Hombo3 / FFmpeg
     |  bounded 2–10 s mono PCM16 16 kHz capture
     |  RIFF WAV in memory; no file saved on disk
     v
Trusted CORE .100 speech-to-text server (OpenAI-compatible /v1/audio/transcriptions)
     |  recognized text
     v
Hombo3 LLM (Ollama CORE .100, allow_action=false)
     |  decision.say / reply
     v
Acer Windows SAPI TTS (pyttsx3)
     |  PCM samples
     v
T23N speaker over key-based SSH -> Thingino Raptor play / rac
```

The audio and STT/LLM/TTS processing occur on Acer/CORE, **not on ESP32** and not as heavy models inside the T23N Linux memory. ESP32 retains motor/safety control only. The camera speakers do not need an additional public unauthenticated HTTP command endpoint. This is an **optional architecture**, not proven live audio.

Current phase implements **operator-triggered push-to-talk**: the Hombo3 camera panel has a password-type operator-token input plus "Recognize 5 s" and "Ask AI by voice". It does not continuously record: no wake word, streaming VAD or echo cancellation yet. Duplex operation may create acoustic feedback when the speaker plays while the microphone is listening; begin with half-duplex and evaluate latency.

## 3. Opt in on Acer (Windows, Python 3.13)

Install Hombo3 Python dependencies in its native Windows `.venv` as documented in the lab architecture. FFmpeg on Windows must be available to CameraHub (through installation/imageio-ffmpeg as configured). Verify camera microphone audio tracks **first**:

```powershell
ffprobe -v error -rtsp_transport tcp -show_entries stream=codec_type,codec_name -of json rtsp://192.168.1.55:554/ch0
```

The output must contain a real `"codec_type": "audio"` track; the presence of a `rad` daemon alone is insufficient.

An **OpenAI-compatible Whisper transcription service must be deployed and verified separately** on trusted CORE .100 (or another explicit trusted host). No actual STT server URI/port is known at this point; do not assume that Ollama :11434 automatically supports audio transcription.

Generate an access token locally in PowerShell:

```powershell
py -3.13 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Store the token only in the **local ignored** Hombo3 `.env`, never in GitHub:

```env
CAMERA_VOICE_ENABLED=true
CAMERA_VOICE_ACCESS_TOKEN=<a-unique-secret-from-command>
CAMERA_STT_URL=http://<private-CORE-host>:<verified-STT-port>/v1/audio/transcriptions
CAMERA_STT_MODEL=whisper-1
CAMERA_STT_LANGUAGE=ru
CAMERA_STT_API_KEY=
CAMERA_VOICE_CLIP_SECONDS=5

# Enable only after hardware speaker and SSH key checks:
SPEECH_OUTPUT=camera_ssh
CAMERA_SPEAKER_SSH_HOST=192.168.1.55
CAMERA_SPEAKER_SSH_USER=root
CAMERA_SPEAKER_SSH_KEY=C:\Users\obzor\.ssh\hombo_t23n_ed25519
```

This is a **template**: replace host/port, generate token and provision key; user-reported `.100` is a network suffix, not enough for a real URL. Keep `SPEECH_OUTPUT=esp32` until speaker test passes.

The manual UI sends a short RTSP audio segment to the configured trusted STT host and the resulting transcript to the configured Ollama LLM with `allow_action=False` so voice alone **cannot move the robot**. The LLM reply is queued to existing `VoiceAnnouncer`, which routes output to camera SSH `play` only when explicitly configured. A separate `/api/speak` route now honors the same speaker selection.

The `POST /api/camera/voice-ask` endpoint is disabled until `CAMERA_VOICE_ENABLED=true` and requires `CAMERA_VOICE_ACCESS_TOKEN` per request; prevent public access to the entire Hombo3 control panel using trusted LAN/VPN and authenticate at reverse proxy if externally exposed. The access token is held only in the UI state, never in browser localStorage. No audio is stored as files by this feature.

## 4. Hardware tests and current limitations

On T23N over SSH:

```sh
pidof rvd rsd rad rac rhd motors-daemon
microphone status
speaker status
command -v play
command -v rac
raptorctl config get rtsp port
raptorctl config get audio enabled
raptorctl config get audio ao_enabled
```

For a short **low-volume** speaker test when the camera is physically accessible and no sensitive conversations are being recorded, generate small PCM using FFmpeg on Acer and pipe it via SSH. Do not play loud tones near people/animals:

```powershell
ffmpeg -hide_banner -loglevel error -f lavfi -i "sine=frequency=440:duration=0.25" -ac 1 -ar 16000 -f s16le - | ssh -i "$HOME\.ssh\hombo_t23n_ed25519" root@192.168.1.55 "play -s -r 16000 -"
```

Confirm physically audible playback and a valid RTSP mic track; test both at once only after half-duplex works. Avoid exposing the RTSP/Web UI/SSH endpoints directly to the internet.

**Remaining before 0.2_test is real:**
- SD firmware with working BusyBox CGI and Web UI, including pan/tilt, image orientation and lazy MJPEG;
- physical PTZ motor direction/reverse, focus/zoom hardware detection;
- microphone audio track from Raptor and speech recognizer actually reachable from Windows;
- physical speaker, SSH key and no audio feedback;
- latency/FPS, CPU/RAM/network measurements with Hombo3 + optional Web UI;
- boot/reboot with permanent SSH recovery.

These are hardware/infrastructure tests; GitHub syntax/mock CI alone cannot prove them.
