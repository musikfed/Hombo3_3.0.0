# Миграция старой ESP32-S3 UNO схемы → Hombo3 / ESP32-S3-DevKitC-1 N16R8

Старые моторные и сенсорные GPIO сохранены. До финальной пайки сделано **одно осознанное изменение**:

- старый MAX98357A DIN GPIO2 → **GPIO15**;
- **GPIO2** теперь `ADC1_CH1` для контроля 2S2P АКБ через делитель 3k/1k.

Это изменение одновременно зафиксировано в `board_config.py`, board JSON, React PinBoard, validator и документации. GPIO3 для АКБ не используется: это strapping pin ESP32-S3.

Старая Arduino-прошивка находится в `firmware/legacy_arduino_s3_uno/` только как историческая/аварийная справка. Активная прошивка Hombo3 — `firmware/hombowifi_s3_micropython/device/`.
