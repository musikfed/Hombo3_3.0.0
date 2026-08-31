# Hombo3 3.0 — MicroPython runtime

Target: **ESP32-S3-DevKitC-1 N16R8 (16 MB Flash + 8 MB Octal PSRAM)**.

The Hombo3 hardware baseline retains the proven v1.2 motor and sensor GPIO assignments, with one deliberate pre-soldering change:

- MAX98357A `DIN/DOUT` signal: **GPIO15** (was GPIO2);
- battery measurement: **GPIO2 / ADC1_CH1** through a 4:1 divider (`3 kΩ` upper, `1 kΩ` lower).

GPIO3 is not used for battery sensing because it is an ESP32-S3 strapping pin. GPIO35..37 are not used on this N16R8 design because Octal memory can occupy them.

Application/runtime updates are performed over Wi-Fi. A full MicroPython core OTA update is supported only when the board has an OTA-capable partition table; see `../core_ota/README_RU.md`.

`secrets.py` is private, ignored by Git and is never overwritten by normal runtime OTA.
