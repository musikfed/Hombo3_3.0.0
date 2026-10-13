# Hardware baseline

This branch documents the physically tested board.

| Item | Tested value |
|---|---|
| PCB | GV-T23-PTZ-MAIN-V2.0 |
| PCB date | 20230915 |
| SoC | Ingenic T23/T23N |
| Sensor donor profile | SC2336 |
| Wi-Fi donor profile | AltoBeam ATBM6012BX |
| PTZ driver | ULN2803LV |
| Original SPI NOR | PUYA P25Q64SH, 64 Mbit / 8 MB |
| Boot medium | microSD |
| microSD bus | 1-bit MMC: CLK/CMD/DAT0 |

The working profile `galayou_g2_t23n_sc2336_atbm6012bx` is a compatible donor profile, not proof of the retail camera model.

## Boot chain

```text
T23 BootROM
 -> SPL / U-Boot on microSD
 -> Linux
 -> ext4 rootfs on microSD
 -> camera / Wi-Fi / PTZ services
 -> MyIPCam UI
```

The experiment validates boot with the SPI NOR physically absent.
