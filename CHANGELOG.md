# CHANGELOG

## 3.0.0 — Hombo3 baseline

- фиксирован ESP32-S3-DevKitC-1 N16R8 pin contract;
- I2S DIN перенесён на GPIO15, GPIO2 выделен под 2S battery ADC;
- добавлен самодостаточный VL53L0X MicroPython driver;
- provision USB разделён на FLASH COM и RUNTIME/REPL COM;
- normal Wi-Fi OTA стал транзакционным: stable boot guard, .prev, pending confirmation, auto rollback;
- Primary/Backup Wi-Fi + Recovery AP;
- VectorProbe spatial engine, reference/live/dynamic maps, semantic inventory, route planning;
- ONVIF/RTSP + mic, local vision, Ollama/RAG/Graph/MCP integration;
- wired + wireless energy inputs documented as one charge/BMS path.
