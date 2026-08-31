# Full MicroPython core OTA

Hombo3 can always update the **application MicroPython firmware (`*.py`) over Wi-Fi**.
This is the primary and safest robot development workflow.

To update the **MicroPython core itself (`.app-bin`) without USB**, the board must first be provisioned
once with a partition table containing `ota_0 + ota_1 + otadata`. This directory contains a 16 MB
Flash layout scaffold for that purpose.

After the one-time USB migration, future `.app-bin` images can be uploaded from `System / OTA`.
The runtime verifies SHA-256, writes the inactive OTA partition and switches the boot partition.

For ESP32-S3 N16R8, MicroPython 1.28.0 should use the **SPIRAM_OCT** variant.
Core OTA uses the `.app-bin` application image, not the combined initial-flash `.bin`.

Build MicroPython on Linux/WSL with ESP-IDF. The baseline MicroPython board command is:

```bash
make -C ports/esp32 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT
```

The custom partition table must be integrated into the build. Before deploying to the real robot,
validate the generated partition table and OTA slots on the target hardware.
