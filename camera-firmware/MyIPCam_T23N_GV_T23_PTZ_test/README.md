# MyIPCam OS 3.1 — T23/T23N microSD boot test branch

Experimental local-only IP camera firmware for the **GV-T23-PTZ-MAIN-V2.0** board family.

> Status: hardware test branch / Stage2, not the final minimal MyIPCam OS.

This branch documents a board configuration that boots from **microSD** and does not use SPI NOR as the active boot medium. It does not provide soldering instructions.

## Tested baseline

- PCB: `GV-T23-PTZ-MAIN-V2.0` (`20230915`)
- SoC: Ingenic T23/T23N
- microSD: native 1-bit MMC
- sensor donor profile: SC2336
- Wi-Fi donor profile: AltoBeam ATBM6012BX
- PTZ: ULN2803LV
- compatible donor profile: `galayou_g2_t23n_sc2336_atbm6012bx`

The Galayou G2 name identifies a compatible software profile, not the retail identity of the physical camera.

## Proven on hardware

microSD boot, Wi-Fi association, SC2336 video, hardware H.264, PTZ and the MyIPCam web page have all been exercised on the target board.

Stage2 still reuses proven Thingino kernel/drivers/backend services. The final goal is a smaller appliance rootfs with only MyIPCam services.

## SD layout

- sector 34 / `0x4400`: SPL
- p1: FAT, starts at sector 2048
- p2: ext4, starts at sector 34816
- current test image: 85 MiB
- project image limit: 128 MiB

## Build and tests

```bash
chmod +x build-stage2.sh tests/run.sh
./build-stage2.sh
./tests/run.sh
```

## Performance observation

With the browser live view closed, a runtime snapshot showed roughly **90% CPU idle**. Earlier, with live web video open, `uhttpd`, `prudynt`, and the local proxy path consumed noticeably more CPU. See [docs/PERFORMANCE.md](docs/PERFORMANCE.md).

## Documentation screenshots

![Initial setup](docs/screenshots/setup-login.svg)

![Wi-Fi dashboard](docs/screenshots/dashboard-wifi.svg)

The images above are generated UI previews, not proof of a live camera frame.

## Source archive

The branch also carries the browsable Stage2 sources under `web/`, build scripts, tests, and documentation.
