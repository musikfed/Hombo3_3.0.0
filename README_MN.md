# Hombo3 3.0 · Robot Control Center

ESP32-S3, мэдрэгч болон ONVIF/RTSP камертай гэрийн роботын удирдлагын төв. Хөдөлгөөн, телеметр, локал хараа, дуу хоолой, LLM/RAG болон OTA-г нэгтгэнэ.

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
