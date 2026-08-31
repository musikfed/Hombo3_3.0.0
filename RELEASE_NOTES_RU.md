# Hombo3 3.0.0 — Release Notes

Hombo3 3.0.0 фиксирует аппаратный baseline домашнего робота на ESP32-S3-DevKitC-1 N16R8 и рабочую host-архитектуру Acer ↔ Wi-Fi ↔ ESP32/REGGO ↔ Ollama.

## Зафиксировано перед пайкой

- ESP32-S3-DevKitC-1 N16R8, MicroPython 1.28 SPIRAM_OCT.
- Два TB6612: отдельный драйвер на левый и правый борт.
- 3×HC-SR04, VL53L0X, MAX98357A.
- GPIO2 / ADC1_CH1 — контроль 2S2P через делитель 3 кОм / 1 кОм (коэффициент 4.0).
- MAX98357A DIN — GPIO15.
- Flash/bootloader COM и Runtime/REPL COM разделены.
- Primary Wi-Fi + Backup Wi-Fi + Recovery AP.
- Проводная и беспроводная энергия входят в единый штатный зарядный тракт до BMS/2S2P.

## Программный baseline

- Транзакционный Runtime OTA по Wi-Fi: SHA-256, `.prev`, pending marker, автоматический rollback.
- `boot.py` и `secrets.py` защищены от обычного OTA.
- FastAPI + готовый production web UI без обязательной npm-сборки на целевой машине.
- ONVIF/RTSP/PTZ и микрофон REGGO.
- Локальный vision-классификатор/YOLO.
- Ollama/Hermes или другая LLM через host-оркестратор.
- RAG + Graph + MCP semantic tools.
- Hombo VectorProbe: reference/live/dynamic map, robot track, semantic inventory, change history, A* route planning и steering hints.

## Автоматическая проверка релиза

Перед упаковкой выполняются `tools/validate_project.py`, `tools/selftest.py`, compileall backend/tools и синтаксическая проверка MicroPython-файлов. Аппаратные параметры конкретной сборки (полярность моторов, точная калибровка ADC, углы PTZ, прозвонка I–0–II, совмещение катушек) проверяются при commissioning после пайки.

## Документация

В `docs/release/` находятся полная документация и короткая монтажная инструкция. Монтажный GPIO baseline в релизе считается замороженным для версии 3.0.0; дальнейшие программные патчи не должны самовольно менять распаянные контакты.
