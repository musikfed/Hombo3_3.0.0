# Hombo3 ↔ PegineLab WIFICAM T23N (SD-only)

## Архитектура / не зависеть от облака камеры

```text
T23N + Thingino/Raptor (локальная Wi-Fi сеть)
    ├── 8090 HTTP Basic Auth → PegineLab UI / CGI / JPEG snapshot
    ├── 554 RTSP ch0/ch1      → видеопоток + микрофон, если есть аудиодорожка
    ├── 80 ONVIF             → обнаружение / PTZ, если сервис поддерживает
    └── 22 Dropbear SSH      → обязательный recovery и опциональный динамик rac/play

                   ↓ LAN
Acer / Hombo3 FastAPI + CameraHub
    ├── низкочастотные JPEG кадры → Hombo3 YOLO/VectorProbe
    ├── FFmpeg/RTSP → микрофон в Hombo3 (MP3 relay)
    ├── опциональный TTS PCM → SSH → Raptor speaker/rac/play
    └── LLM/Ollama/GPT → семантические события/инструменты
```

Камера **не запускает LLM локально** (на T23N ~36 MiB RAM). GPT/мультимодальную
модель можно подключать отдельно на Acer/сервере; текущий Hombo3 передаёт
в контекст в основном YOLO/VectorProbe наблюдения, а не произвольно загружает
JPEG в GPT. Автоматическая загрузка кадров в облако не включена.

## Проверка прежде настройки

Камера и Acer должны быть в одной доверенной LAN. На Acer (Windows/WSL или Linux):

```sh
python scripts/probe_wificam.py --ip 192.168.1.55
```

Скрипт спросит Web UI пароль (не печатает его) и проверит порты, CGI JSON,
JPEG и аудио/видео дорожки RTSP через установленный `ffprobe`.

Если увидишь `#!/bin/sh` вместо JSON — это **ошибка исполнения BusyBox CGI**
старого `0.1_test`, а не ошибка Hombo3. Новая сборка WIFICAM принудительно
пересобирает target BusyBox и проверяет API при старте.

## Режим A: JPEG snapshot (без RTSP-декодера на Acer)

Настройка есть в `.env.wificam.example`. В локальном `.env` Hombo3
добавить / заменить `CAMERA_*`:

```env
CAMERA_VIDEO_BACKEND=http_snapshot
CAMERA_SNAPSHOT_URL=http://192.168.1.55:8090/cgi-bin/snapshot.jpg
CAMERA_SNAPSHOT_USERNAME=admin
CAMERA_SNAPSHOT_PASSWORD=ВАШ_ПАРОЛЬ
CAMERA_SNAPSHOT_INTERVAL_S=1.0
CAMERA_RTSP_URL=rtsp://192.168.1.55:554/ch0
CAMERA_ONVIF_HOST=192.168.1.55
CAMERA_ONVIF_PORT=80
CAMERA_AUDIO_ENABLED=true
```

Это **пример**, IP и пароль нужно заменить, а `.env` не отправлять в Git.
CameraHub забирает JPEG раз в секунду (configurable), проверяет сигнатуру
JPEG и направляет кадр существующему Hombo3 vision module. Этот режим не
включает звук через snapshot: микрофон по-прежнему требует RTSP.

Если RTSP подтвердится, можно вместо этого установить:

```env
CAMERA_VIDEO_BACKEND=auto
CAMERA_RTSP_URL=rtsp://192.168.1.55:554/ch0
```

В `auto` кадры идут через FFmpeg/OpenCV. URL и данные доступа к RTSP
могут **отличаться** от `admin` PegineLab.

## Микрофон (камера → Hombo3)

В Thingino/Raptor должны работать `rad` (аудио) и `rsd` (RTSP).
На Acer:

```sh
ffprobe -v error -rtsp_transport tcp -show_entries stream=codec_type,codec_name -of json rtsp://192.168.1.55:554/ch0
```

Нужна запись с `"codec_type": "audio"`. Наличие одного `rad` в `ps`
не доказывает, что RTSP публикует звук. Hombo3 уже содержит
`CameraHub.audio_stream()`, который принимает дорожку через FFmpeg и отдаёт
MP3 клиенту. Без реального аудиотрека это не заработает.

На самой камере через SSH:

```sh
pidof rad rsd rvd
microphone status
raptorctl config get audio enabled
raptorctl config get rtsp port
```

**Не включать микрофон/громкоговоритель для скрытой записи или удалённого
прослушивания**. Оставляем только локальную авторизованную интеграцию.

## Динамик (Hombo3 TTS → камера)

Pinned Thingino/Raptor содержит `play`, который через `rac` принимает PCM16
LE, MP3, AAC или Opus. Для PCM16 через stdin поддерживается
`play -s -r 16000 -`.

Проверить на камере:

```sh
command -v play
command -v rac
speaker status
raptorctl config get audio ao_enabled
```

Наличие утилиты ещё не доказывает, что усилитель/динамик аппаратно работает.
Сначала проверить местное воспроизведение.

Для удалённого TTS Hombo3 **не открывает незащищённый audio HTTP endpoint**.
Он может отправить PCM по уже включённому SSH, если доступен SSH-ключ:

```sh
# На компьютере Hombo3:
ssh-keygen -t ed25519 -f ~/.ssh/hombo_t23n_ed25519
cat ~/.ssh/hombo_t23n_ed25519.pub | ssh root@192.168.1.55 \
  'umask 077; mkdir -p /root/.ssh; cat >> /root/.ssh/authorized_keys'

ssh -i ~/.ssh/hombo_t23n_ed25519 -o BatchMode=yes \
  root@192.168.1.55 'command -v play; speaker status'
```

После аппаратного теста динамика в локальном `.env`:

```env
SPEECH_OUTPUT=camera_ssh
CAMERA_SPEAKER_SSH_HOST=192.168.1.55
CAMERA_SPEAKER_SSH_USER=root
CAMERA_SPEAKER_SSH_KEY=/home/obzor/.ssh/hombo_t23n_ed25519
```

Путь ключа на Windows должен быть Windows-путём к файлу, на WSL — Linux.
Если ничего не менять, `SPEECH_OUTPUT=esp32` и существующая озвучка Hombo3
работает как прежде. SSH не выключать: это и recovery, и защищённый звуковой
транспорт.

Альтернативно у Raptor есть RTSP ONVIF backchannel, но его фактическая
доступность требует `raptorctl config get rtsp backchannel` и отдельного
пробного сеанса. Нельзя считать динамик рабочим по одному RTSP видеопотоку.

## Готовность к 0.2_test

Принимать только после испытаний на камере: `CGI status JSON`, `JPEG`,
`ONVIF/PTZ`, `RTSP video`, `RTSP audio`, `Raptor speaker`, `SSH` после
reboot. Зафиксированный `0.1_test` не менять и не путать с обновлёнными
исходниками.

## PTZ, реверс, автофокус, оптический зум

В Hombo3 CameraPanel теперь есть:
- Стрелки с коротким импульсом ONVIF ContinuousMove и обязательным Stop;
- Переключатели реверса pan/tilt, сохраняемые на Acer в `data/camera-ptz-calibration.json`;
- Кнопки ONVIF Optical Zoom ± (в отличие от цифрового CSS-масштабирования);
- Кнопка Imaging AUTO focus; если в объективе нет автофокуса, сервер
  честно возвращает ошибку.

Реверс на уровне Hombo3 выполняется в CameraHub, а не в прошивке моторов.
Для управления из PegineLab на камере есть независимая калибровка в
`/opt/wificam/ptz-controls.conf`: не устанавливайте обратные настройки
в обеих системах, если используете разные пути управления моторчиками.
При отсутствии аппаратного Zoom/Imaging сервисы ONVIF могут вернуть
`unsupported`. Увеличение в браузере Hombo3 останется цифровым.

## Быстрый видеотракт

При исправном RTSP предпочтителен `CAMERA_VIDEO_BACKEND=auto`.
`CAMERA_RTSP_URL=rtsp://CAMERA_IP:554/ch1` — пример более лёгкого
substream; сначала проверьте существование `ch1` через ffprobe
(если его нет — используйте `ch0`). Настройка `CAMERA_MJPEG_FPS=12`
ограничивает нагрузку JPEG-конвертации на Acer. В WebSocket пользователь
получает **последний кадр без очереди старых кадров**, чтобы поворот
не отображался спустя несколько секунд. При неудаче RTSP режим `auto`
может перейти на авторизованный snapshot CGI. Последний путь медленнее.

Для самой WIFICAM Raptor RHD MJPEG доступен через защищённый URL
`http://CAMERA_IP:8090/cgi-bin/live.mjpg`. В pinned Raptor глобальный
JPEG FPS по умолчанию бывает всего 1; при тесте можно обратимо выставить
8–15 через `scripts/camera_preview_fps.sh` в репозитории WIFICAM.
Не надо выгружать `motor` или ISP модуль ядра и отключать `rvd`,
`rad`, `rsd`, `rhd`, `motors-daemon`, Wi-Fi или SSH.
Физические тесты FPS, задержки, мощности CPU и работы моторчиков
остаются обязательными до нового SD-релиза.

Проверки исходников: GitHub Actions с unittest-моками ONVIF, сборкой
React/TypeScript, отдельным shell-тестом Thingino motors в WIFICAM.
Это не заменяет аппаратную проверку PTZ, RTSP и фокуса.
