# Hombo3 3.0 · Robot Control Center

ESP32-S3, 센서, ONVIF/RTSP 카메라를 사용하는 홈 로봇 제어 센터입니다. 이동 제어, 텔레메트리, 로컬 비전, 음성, LLM/RAG 및 OTA를 통합합니다.

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
