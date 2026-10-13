# Hombo3 3.0 · Robot Control Center

基于 ESP32-S3、传感器和 ONVIF/RTSP 摄像机的家庭机器人控制中心，整合运动控制、遥测、本地视觉、语音、LLM/RAG 与 OTA 管理。

## Architecture / Архитектура

```text
ESP32-S3 robot + ONVIF/RTSP camera + sensors -> Wi-Fi/HTTP/WS/PCM -> FastAPI + React Control Center -> local vision / Ollama / RAG / OTA
```

## Project structure / Структура проекта

- `backend/` — FastAPI services and robot control logic
- `frontend/` — React control interface
- `firmware/` — ESP32-S3 firmware and OTA components
- `data/` — runtime settings and project data

## Contact / Контакты

- Email: feudor.lab@yandex.ru
- Telegram: @Feudorlab1
