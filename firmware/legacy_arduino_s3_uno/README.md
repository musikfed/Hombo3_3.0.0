# ESP32-S3 UNO firmware — v1.2.0-rc1

## Required Arduino libraries

- ESP32 board package 3.x
- ArduinoJson 7.x
- Adafruit VL53L0X

`WiFi`, `WebServer`, `Wire` and `ESP_I2S` are supplied by the ESP32 Arduino core.

## Before flashing

1. Copy `secrets.h.example` to `secrets.h`.
2. Put your Wi-Fi SSID/password into `secrets.h`.
3. Check `../../docs/WIRING_V1_2.md` — one TB6612 must equal one physical side.
4. Select the real ESP32-S3 UNO N16R8 board/profile.
5. Lift all wheels for the first test.
6. Upload and open Serial Monitor at 115200.

## Motor command topology

The firmware exposes two logical commands only: `left` and `right`.

```text
LEFT_IN1/IN2/PWM   -> A+B control inputs on TB6612-L -> FL + BL
RIGHT_IN1/IN2/PWM  -> A+B control inputs on TB6612-R -> FR + BR
```

The A and B motor outputs on each driver stay separate; only their control inputs receive the same side command.

## Memory approach

The firmware deliberately avoids a web UI, camera processing and an LLM on the ESP32. React, logging, ONVIF, local YOLO and Ollama run on the Acer/Huananzhi computers.
