# MyIPCam OS 3.1 — T23/T23N microSD boot test branch

Experimental local-only IP camera firmware work for the **GV-T23-PTZ-MAIN-V2.0** board family, booting from **microSD without SPI NOR**.

> Status: **hardware test branch / Stage2**, not the final minimal MyIPCam OS.

Languages: [Русский](docs/i18n/README.ru.md) · [中文](docs/i18n/README.zh-CN.md) · [Српски](docs/i18n/README.sr.md) · [Беларуская](docs/i18n/README.be.md) · [Қазақша](docs/i18n/README.kk.md) · [فارسی](docs/i18n/README.fa.md)

## Proven hardware baseline

- Board marking: `GV-T23-PTZ-MAIN-V2.0` (`20230915`)
- SoC: Ingenic T23/T23N
- Boot storage: microSD, native **1-bit MMC** wiring
- SPI NOR: PUYA P25Q64SH was physically removed for this experiment
- Sensor profile used in the working donor build: SC2336
- Wi-Fi profile used in the working donor build: AltoBeam ATBM6012BX
- PTZ driver: ULN2803LV + motors-daemon path verified on hardware
- Known working donor profile: `galayou_g2_t23n_sc2336_atbm6012bx`

The Galayou G2 profile is a compatible donor profile, **not proof that the physical camera is exactly a Galayou G2**.

## What is already proven on the physical camera

The camera has successfully booted from microSD with the SPI NOR removed. Wi-Fi association, SC2336 video, hardware H.264, PTZ and the custom MyIPCam web page have all been exercised on the board during development.

Current Stage2 still reuses proven Thingino kernel/drivers/backend services. The final goal is a smaller appliance rootfs with only the services needed by MyIPCam.

## SD image layout used by this branch

- sector 0: MBR / Ingenic boot metadata
- sector 34 (`0x4400`): SPL
- p1: FAT boot partition, starts at sector 2048
- p2: ext4 rootfs, starts at sector 34816
- current test image size: 85 MiB
- project hard limit: 128 MiB

## Build

Requirements: Linux/WSL, `debugfs`, `e2fsck`, Python 3, and a known-good Thingino build output.

```bash
chmod +x build-stage2.sh
./build-stage2.sh
```

The builder refuses an unexpected donor image SHA-256 and validates the final rootfs readback.

## Tests

```bash
./tests/run.sh
# Optional: validate a built image too
./tests/run.sh /path/to/MyIPCam_OS_3.1_T23N_stage2.bin
```

GitHub Actions runs the source-level checks on every push and pull request.

## Flashing

A generic PowerShell raw writer is included in `tools/write-sd.ps1`, but the development machine currently uses a stricter project-specific writer with full readback verification. Always verify the target disk before writing.

## Safety notes

- This branch targets one experimentally verified board family; do not assume pin compatibility with another T23 camera.
- microSD is wired in 1-bit mode on this PCB. Do not reconfigure it as 4-bit unless the board routing is independently verified.
- Removing the SPI NOR is a hardware modification and can permanently damage the camera if done incorrectly.
- Never bridge unknown pads or SPI-NOR pads.
- Keep a known-good SD image backup before modifying the rootfs.

## Current performance observation

When the browser live view was closed, the camera reported roughly **90% CPU idle** in a snapshot. With the web live view open earlier, `uhttpd`, `prudynt`, and the HTTP streaming proxy path consumed noticeably more CPU. This confirms that browser streaming/proxying is a major part of the current runtime load, not an always-on CPU bottleneck.

See [docs/PERFORMANCE.md](docs/PERFORMANCE.md).

## Screenshots

![Initial setup/login UI](docs/screenshots/setup-login.jpg)

![Wi-Fi connected dashboard preview](docs/screenshots/dashboard-wifi.jpg)

These screenshots are generated from the current Stage2 HTML/CSS for documentation. They are UI previews, not proof of a live camera frame. Replace the dashboard image with a real field screenshot after a successful video/PTZ test on the target board.
