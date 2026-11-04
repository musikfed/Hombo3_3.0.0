# Hombo3 conversational vision & operator-approved visual memory

This opt-in feature integrates into **the existing camera conversation**, not separate YOLO/VLM test buttons. The same camera session is shared by push-to-talk transcription and typed turns. A CPU Ollama planner (`qwen3:4b-instruct`) uses prior dialogue and approved memory to decide whether it needs existing Acer YOLO, OpenCV frame statistics, CORE VLM (`qwen2.5vl:7b`) or no vision at all. Fresh CameraHub JPEG only; never claim to see an unavailable frame.

## Local settings in ignored Hombo3 .env

```env
CAMERA_DIALOGUE_ENABLED=true
CAMERA_DIALOGUE_PLANNER_MODEL=qwen3:4b-instruct
CAMERA_DIALOGUE_VLM_MODEL=qwen2.5vl:7b
CAMERA_DIALOGUE_SAVE_IMAGES=false
CAMERA_DIALOGUE_CPU_FALLBACK=true
```

The pre-existing `CAMERA_VOICE_ENABLED`, camera microphone/RTSP, trusted external STT and operator token are still required for voice. Set `SPEECH_OUTPUT=camera_ssh` only after audible speaker and SSH tests. Windows native Hombo3 uses Python 3.13, not WSL. T23N firmware, YadroKreator and GPU power control remain unchanged.

## Dialogue and learning

The planner chooses tools based on conversation context (including follow-up questions), not fixed keyword switches. On-demand YOLO runs on Acer CPU; OpenCV reports real frame brightness/blur/change statistics; CORE vision model sees the latest JPEG and may describe unknown objects. The response returns through Hombo's TTS, never through motor commands.

A newly taught label becomes a *pending example* until the operator explicitly confirms on the next turn. Confirmed metadata is stored in a private 0600 SQLite DB. With separately opted-in `CAMERA_DIALOGUE_SAVE_IMAGES=true`, only approved JPEG examples are stored privately (0600). OpenCV ORB matching suggests similar **scenes**, not positive object identification. The visual memory can be listed/deleted through authenticated API/UI. This does **not** finetune YOLO weights or perform automatic long-term object tracking. Future explicit workflow: label → review → approved dataset → training → holdout evaluation → deployment.

## Resource limits

CPU planner sends `num_gpu=0`; local Acer YOLO is CPU. On-demand CORE VLM returns `keep_alive=0`, and Hombo's own Hermes requests do likewise in this opt-in mode. On known GPU OOM errors there is one optional VLM CPU retry on CORE (48 GB RAM, slower DDR3 and Xeons). This is not literal VRAM swapping and no guarantee that two big models fit simultaneously in 12 GB. Inspect `ollama ps` and `nvidia-smi`.

Requests from this dialogue module are serialized; **other projects are not locked**. Server-wide concurrency limits and centralized GPU scheduling are separate changes requiring operator review. No automatic changes to systemd, Ollama service flags, camera configuration or SD images.

## Real hardware validation still required

Physical camera RTSP/SD boot, mic/speaker, STT availability, Wi-Fi, ORB quality, model RAM/VRAM budget, latency and VPN routing must be tested. The voice path remains push-to-talk; always-on VAD/wake/echo suppression is **not yet implemented**. CI/mock tests do not demonstrate hands-free operation.
