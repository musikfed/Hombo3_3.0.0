# PegineLab T23N ↔ Hombo3 — imaging/PTZ and bidirectional voice plan

The **SD 0.1_test binary remains unchanged**. New controls are in WIFICAM `mymarrchWFcam` and Hombo3 `main`.

## Camera controls

- Motor pan/tilt: bounded steps via Thingino motors on-camera; independent persistent axis reversal. Hombo3 uses ONVIF short pulses with Stop and separate reverse flags.
- Digital zoom: browser-only ×1–×3 WIFICAM, ×1–×2.5 Hombo3. No lens movement.
- Browser-only horizontal mirror, vertical flip and 180° rotation (both toggles). Does **not** alter the RTSP/YOLO/recorded pixels or PTZ axes.
- Optical zoom: ONVIF request with Stop, physical actuator unverified.
- Autofocus: ONVIF Imaging AUTO, non-persistent setting to avoid repeated NVRAM writes, physical actuator unverified.
- Manual focus: ONVIF Imaging near/far short 0.2s pulse, Stop. Unsupported on fixed-focus camera.
- Pinned Galayou G2 Thingino config claims motors and audio, **not** autofocus or optical zoom. Hardware testing is mandatory.

## Voice architecture

```text
T23N microphone → Raptor RAD/RSD RTSP audio → Acer Windows 11 FFmpeg
    → bounded 5s PCM16 WAV (in RAM) → trusted CORE .100 Whisper-compatible STT
    → transcript → CORE Ollama LLM (allow_action=false)
    → Acer Windows SAPI TTS → PCM → T23N SSH/Raptor play/rac speaker
```

No heavy STT/TTS/LLM is run on ESP32 or T23N; ESP32 stays responsible for motor safety. No raw audio is sent to Ollama automatically; the voice endpoint is *disabled by default* and only responds to operator-initiated actions with a secret token. Audio stays off disk. External STT server (OpenAI-compatible `/v1/audio/transcriptions`) must be installed and verified separately on CORE. Ollama is not itself assumed to provide speech transcription.

### Windows Hombo3 local .env (template only)

```env
CAMERA_VOICE_ENABLED=true
CAMERA_VOICE_ACCESS_TOKEN=<random-operator-secret-20+-chars>
CAMERA_STT_URL=http://<trusted-CORE-host>:<verified-STT-port>/v1/audio/transcriptions
CAMERA_STT_MODEL=whisper-1
CAMERA_STT_LANGUAGE=ru
CAMERA_STT_API_KEY=
CAMERA_VOICE_CLIP_SECONDS=5
# Set only after physical speaker test:
SPEECH_OUTPUT=camera_ssh
CAMERA_SPEAKER_SSH_HOST=192.168.1.55
CAMERA_SPEAKER_SSH_USER=root
CAMERA_SPEAKER_SSH_KEY=C:\Users\obzor\.ssh\hombo_t23n_ed25519
```

Create token on Windows with `py -3.13 -c "import secrets; print(secrets.token_urlsafe(32))"`. The UI has "Recognize 5s" and "Ask AI by voice" with nonpersistent secret input. Microphone path must have an RTSP **audio** track verified by `ffprobe`; Raptor RAD alone is not evidence. Speaker needs `rac/play` + configured public-key SSH + audible physical test.

Full safety notes, PowerShell speaker test and acceptance checklist are in [Russian guide](CAMERA_PTZ_AUDIO_RU.md). Always require VPN/reverse proxy authentication for external access; never expose camera SSH or Hombo3 unsecured. Start half-duplex until speaker-to-microphone feedback is under control.
