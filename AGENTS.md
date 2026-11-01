# Project agent notes / Памятка для разработчиков

> **Always read** [docs/PEGINELAB_LAB_ARCHITECTURE_RU.md](docs/PEGINELAB_LAB_ARCHITECTURE_RU.md) or the matching [EN version](docs/PEGINELAB_LAB_ARCHITECTURE_EN.md) **before altering build, deployment, networking, camera integration, audio/video or AI routing**. These documents are duplicated in the WIFICAM and Hombo3 repositories; maintain RU/EN parity and update both repos on topology changes. The 2026-11-01 inventory is user-reported, not automatically verified.

## Non-negotiable host separation

- **Acer Swift 3** is the central operator/orchestrator: Windows 11 Pro, Ryzen 5 3500U 4C/8T, 20 GB RAM, Vega 8, 512 GB SSD.
- **HomBo3 backend / dashboard:** **native Windows 11**, not WSL. Repo `.python-version` is **3.13**. User has Python 3.14.4 default, 3.13.13, 3.12.9 and `uv 0.11.15`; explicitly choose 3.13.
- **WIFICAM T23N SD firmware:** **Ubuntu 24.04 on Acer's WSL**, distro stored on Windows D:. Sources were under Linux `~/myipcam/wificam_T23N`, Thingino under `~/myipcam/thingino-firmware`, camera profile `galayou_g2_t23n_sc2336_atbm6012bx`. Never tell the user to build this cross-compiled Linux firmware with native Windows Python.
- **.100 CORE:** Ubuntu Server 24.04, dual Xeon E5-2650, RTX 3060 12 GB; main LLM/Ollama target, Python 3.12.3, `uv 0.12.0`.
- **.109 DEXP N100:** Ubuntu, Docker Compose/AmneziaWG VPN, 2FA and CI/CD edge. **.103 Ardor:** Windows 11 Pro, Ryzen 5 5600, Radeon RX 7600 XT; graphics. **.101 Tenda E205:** managed LAN switch; Tenda TX12: router.
- LAN suffixes `.100/.101/.103/.109` are not complete IP addresses; check actual addresses, VPN routes and credentials locally. Camera example `192.168.1.55` is a previously tested endpoint, not guaranteed permanent.
- Domains **peginelab.ru** and **peginelab.com** are owner-reported and need DNS/TLS routing verification. Do not include `privkey.pem`, `fullchain.pem`, passwords, public static IP, secrets, VPN keys or real `.env` in Git.

## Integration principles

- Camera: SD-only independent local stream, Thingino/Raptor, SSH/Dropbear for recovery, PegineLab UI, RTSP/JPEG, PTZ, mic/speaker only if the **hardware capabilities are verified**. No LLM process on resource-limited T23N.
- Hombo3: camera/YOLO/VectorProbe plus robotic control on Acer. Heavy neural inference on GPU CORE over trusted LAN/AmneziaWG, not on camera and not via unnecessary public port forwarding. ESP32-S3 enforces local motor safety.
- Low-latency video: RTSP/substream or native persistent MJPEG; latest-frame semantics and no unbounded queues. Do not disable `rvd/rad/rsd/rhd`, `motors-daemon`, MMC, ISP, Wi-Fi or SSH to achieve speed.
- Remote access: 2FA/VPN ingress on DEXP, explicit allowlists. Never expose camera/SSH/Ollama/robot command endpoints directly to WAN. Camera firmware must remain usable when external Internet is down.
- New code and CI success **do not imply physical camera verification**. Keep established SD `0.1_test` boot baseline intact; new firmware releases only after hardware boot, SSH, UI CGI, video, motors and audio acceptance.

## Repositories

- Firmware: https://github.com/musikfed/wificam_T23N (`mymarrchWFcam`).
- Robot/controller: https://github.com/musikfed/Hombo3_3.0.0 (`main`).
## This repository specifically

- Develop/run Hombo3 Python API **on Windows**. Pin Python 3.13 instead of default 3.14 (`.python-version`); local dependencies live in a virtual environment, `backend/requirements.txt`.
- Vite/React frontend builds from `frontend/`; FastAPI starts from `backend/run.py`. Check platform-specific PowerShell syntax rather than assuming Linux shells.
- Do not force the Windows backend to run inside WSL just because WIFICAM firmware does. WSL is for camera firmware only.
- Prefer a single CameraHub reader and drop stale visual frames; PTZ bounds, independent inverse-axis calibration, STOP, audio and capabilities must be hardware-tested. Keep local safety on ESP32.
- Treat the DEXP VPN and CORE Ollama as external dependencies; avoid hard-coded internet endpoints, secrets and automatic cloud image upload.
