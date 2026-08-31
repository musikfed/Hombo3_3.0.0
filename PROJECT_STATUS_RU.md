# Hombo3 3.0.0 — статус релизной сборки

## Реализовано

- ESP32-S3-DevKitC-1 N16R8, MicroPython 1.28 SPIRAM_OCT, dual-COM provisioning;
- два TB6612: один драйвер на левый борт и один на правый;
- 3×HC-SR04, VL53L0X с локально включённым драйвером, MAX98357A;
- контроль 2S2P через GPIO2/ADC1_CH1, делитель 3 кОм / 1 кОм, коэффициент 4.0;
- Primary + Backup Wi-Fi + Recovery AP, token auth;
- обычный runtime OTA по Wi-Fi с SHA-256, .prev и автоматическим boot rollback;
- стабильный boot.py не заменяется обычным OTA;
- FastAPI + React Robot Control Center, ONVIF/RTSP, локальный YOLO, Ollama, RAG+Graph, MCP;
- Hombo VectorProbe: reference/live/vector/dynamic maps, track, semantic inventory, change history, A* route and steering hints.

## Зафиксированный монтажный baseline

GPIO2 — BATTERY ADC; GPIO15 — MAX98357A DIN. GPIO0/3/45/46, 19/20 и 35–37 не используются проектом.

## Что проверяется только на собранной машине

Это не программные заглушки, а физические параметры конкретного экземпляра: полярность моторов, ориентация датчиков, коэффициент ADC после измерения мультиметром, реальные углы ONVIF PTZ, качество беспроводного совмещения катушек и точная прозвонка контактов I–0–II.
