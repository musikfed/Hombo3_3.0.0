# PegineLab lab — infrastructure, host roles and development contract

> Snapshot: **2026-11-01**. Specs below are owner-reported, not an automated hardware or network audit. Keep this file synchronized between `musikfed/wificam_T23N` and `musikfed/Hombo3_3.0.0`, alongside the Russian copy. **Never commit credentials, a public IP, VPN keys, private .env, certificates' private keys or TLS/SSH secrets.**

## Architecture and project boundaries

**WIFICAM T23N** is an SD-booted Thingino/Raptor firmware for the Galayou G2 T23N + SC2336 + ATBM6012BX Wi-Fi camera. It provides PegineLab local UI, video/audio when supported, ONVIF/PTZ when supported, and permanent SSH recovery. Firmware is **built under Ubuntu 24.04 in WSL on the Acer laptop**, then written as a whole disk image starting at LBA0.

**Hombo3 3.0** runs its FastAPI backend and browser dashboard **natively on Acer Windows 11 Pro** (not WSL), controls the ESP32-S3 robot, and integrates camera vision, YOLO/VectorProbe, speech and higher-level LLM calls. Robot motor safety remains on ESP32-S3. Do not run large LLMs on the camera.

**CORE .100** is the GPU/LLM server, **DEXP .109** is the edge AmneziaWG/VPN/CI gateway, **Ardor .103** is a graphics workstation. Acer is the central orchestration and operator console.

## Network layout (logical; not a verified routing configuration)

```text
Internet — static public IP, 100 Mbps WAN, purchased domain/TLS
    |
Tenda TX12 — NAT, Wi-Fi, WireGuard/OpenVPN client
    |
    +--- .109 DEXP N100 / Ubuntu / Docker Compose
    |         AmneziaWG VPN server, edge, 2FA, CI/CD
    |
    +--- .100 Huananzhi X79 / Ubuntu Server / RTX 3060
    |         GPU LLM/Ollama CORE
    |
    +--- .103 Ardor / Windows 11 Pro / RX 7600 XT
    |         GRAPHICS workstation
    |
    +--- .101 Tenda E205 managed switch (connects Ardor)
    |
    +--- Acer Swift 3 / Windows 11 Pro — HOMBO3
    |         WSL Ubuntu 24.04 (distribution storage on D:)
    |         WIFICAM SD firmware build in WSL only
    |
    +--- T23N camera (previously tested at 192.168.1.55)
    +--- ESP32-S3 robot (full IP must be verified)

Cisco Catalyst 3250: training switch, normally OFF.
Smart socket and magic packet/Wake-on-LAN: on-demand boot paths.
LAN nodes use gigabit switches/hubs where connected.
```

The `.100/.101/.103/.109` names are **IP suffixes**, not complete addresses. Do not infer subnet or port forwarding from them. WAN IP, Acer IP, ESP32 IP, VPN CIDR, VLANs, NAT and domain targets remain to be inventoried.

## Compute inventory

| Role | OS | Hardware (owner-reported) | Primary responsibility |
|---|---|---|---|
| Acer Swift 3 control center | Windows 11 Pro; Ubuntu 24.04 WSL on D: | Ryzen 5 3500U (4C/8T), 20 GB DDR4, Vega 8 (reported 2 GB allocation), 512 GB M.2 SSD | Native Hombo3, camera/robot coordination; firmware toolchain only in WSL |
| DEXP N100 .109 (2026 edge) | Ubuntu / Docker Compose | Intel N100, 16 GB RAM, 512 GB SSD | VPN AmneziaWG gateway, 2FA, CI/CD, external service ingress |
| Huananzhi X79 .100 CORE | Ubuntu Server 24.04 | 2× Xeon E5-2650 (owner reports 32 logical threads), 48 GB DDR3-1600, RTX 3060 12 GB VRAM, 2 TB disk | GPU LLM/Ollama and compute workloads, remotely powerable |
| Ardor .103 GRAPHICS (2025) | Windows 11 Pro | AMD Ryzen 5 5600, 32 GB DDR4, Radeon RX 7600 XT 16 GB, 1 TB | Graphics tasks, remotely powerable |
| T23N Wi-Fi camera | Thingino/Linux SD | Ingenic T23N + SC2336 + ATBM6012BX | Independent local AV sensor, PTZ when supported, SSH recovery |
| Hombo3 robot | ESP32-S3 firmware | ESP32-S3-DevKitC-1 N16R8 according to project baseline | Sensor/motor control and local safety |

CORE's owner-reported setup also includes a 650 W Bronze PSU, bottom-mounted power supply and additional case/CPU cooling; this does not replace a load/temperature test. Vega 8 typically uses shared RAM; the reported 2 GB should not be assumed dedicated VRAM.

## Toolchains: do not mix Windows, WSL and Linux server

### Acer / Windows 11 Pro — Hombo3

Installed: Python **3.14.4 (default)**, **3.13.13**, **3.12.9**; `uv 0.11.15` on Windows. The Hombo3 repo's `.python-version` explicitly says **3.13**, so prefer Python 3.13 and do **not** rely on default Python 3.14:

```powershell
cd <PATH-TO-Hombo3_3.0.0>
py -3.13 --version
uv venv --python 3.13 .venv
uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
.\.venv\Scripts\python.exe backend\run.py
```

Frontend: develop/build via `npm` in `frontend/`. Keep tokens and camera passwords in a local, ignored `.env`. For Ollama use an allowed private CORE .100 address on LAN/VPN, **not a publicly exposed TCP 11434**.

### Acer / WSL Ubuntu 24.04 on Windows D: — WIFICAM firmware

Owner's stack:

```text
WSL 3.0.3.0 / kernel 6.18.54.1-1
WSLg 1.0.79 / MSRDC 1.2.7391
Direct3D 1.611.1-81528511 / DXCore 10.0.26100.1-240331-1435.ge-release
Windows build 10.0.26300.9711
```

Previously used Linux working paths (WSL disk stored on D: does **not** mean source code resides in `/mnt/d`):

```sh
cd ~/myipcam/wificam_T23N
git switch mymarrchWFcam
git pull --ff-only origin mymarrchWFcam
# Pinned Thingino clone: ~/myipcam/thingino-firmware
THINGINO_FAST=1 PUBLISH=1 sh scripts/build_thingino_wificam_image.sh
```

Keep IO-heavy building in the WSL Linux filesystem. Output `Thingino/thingino-t23-sd.bin` is a complete disk image: write **from sector LBA0**, never add `dd seek`/offset to an already assembled image. Windows PowerShell `usbipd` was used for the Realtek 0bda:0177 reader (`3-2` was the verified BUSID in a prior session); verify BUSID and Linux `/dev/sdX` each time. Protect all host disks from accidental writing. Baseline `0.1_test` is not the same as unreleased new CGI/PTZ changes.

### .100 CORE / Ubuntu 24.04 server — heavy LLM

Installed (owner report): **Python 3.12.3** and **uv 0.12.0** on Linux. RTX 3060 12GB is the main GPU inference target. Dynamic power/WOL is a planned operational capability, not proof of configured network wake.

## Data paths and design intent

```text
T23N SC2336 -> Raptor RTSP/JPEG -> LAN/Wi-Fi -> Acer Hombo3 CameraHub
    -> YOLO/VectorProbe, audio handling -> observations and requests
    -> CORE .100 RTX 3060/Ollama over trusted LAN or AmneziaWG VPN
    <- inference/LLM response
Acer -> Hombo3 ESP32-S3 robot (bounded actions; local safety on MCU)
Acer -> T23N ONVIF/PTZ (calibrated axes, bounded pulses and STOP)
Acer -> T23N SSH / Raptor play/rac (optional speaker TTS)
T23N mic -> RTSP audio -> Acer (STT requires separately validated integration)
Remote client -> TLS/2FA + AmneziaWG on .109 -> allowlisted LAN services
```

Priorities: local-first ownership and offline camera autonomy; SSH recovery always retained; low-latency RTSP/substream or persistent MJPEG without stale JPEG frame queues; capability-tested PTZ/focus/zoom/mic/speaker; GPU work on CORE, short control loops on Acer/ESP32; authenticated edge/VPN access; no direct WAN exposure of cameras, robot motors or Ollama; power on/off only when operationally safe. Do not allow unconstrained LLM output to execute arbitrary shell or motor commands.

## Network services and secrets

- ISP: owner-reported **100 Mbps WAN**, **655 RUB/month**, static public address (not recorded).
- Router: **Tenda TX12** with WireGuard/OpenVPN clients and an older PPTP server (PPTP should not be used for new secure remote access).
- Edge: **DEXP .109** with AmneziaWG server in Docker Compose, 2FA and CI/CD.
- Owner-reported domains: `peginelab.ru` (paid SSL/email) and `peginelab.com` (mentioned for DEXP services). Domain ownership, DNS records, certificate SANs and routing **have not been verified**.
- `fullchain.pem` and especially `privkey.pem` are **not Git artifacts**. Never commit them or private AmneziaWG config. Prefer explicit port allowlists and VPN ingress over blanket port forwarding.
- Tenda E205 .101 is the managed switch associated with Ardor; Cisco Catalyst 3250 remains off.

## Related repositories and verification

- WIFICAM: [musikfed/wificam_T23N](https://github.com/musikfed/wificam_T23N) `mymarrchWFcam`; `scripts/build_thingino_wificam_image.sh`, `web/`, `rootfs/`, `docs/HOMBO3_INTEGRATION_RU.md`.
- Hombo3: [musikfed/Hombo3_3.0.0](https://github.com/musikfed/Hombo3_3.0.0) `main`; `backend/app/main.py`, `backend/app/camera.py`, `frontend/`, `.env.wificam.example`, `docs/WIFICAM_T23N_RU.md`.
- Hardware acceptance still required: actual camera PTZ/mic/speaker/RTSP latency and FPS, SSH persistence after reboot, CORE LLM connectivity, VPN 2FA ingress and Wake-on-LAN operation. CI syntax/mock tests are **not** physical verification.
