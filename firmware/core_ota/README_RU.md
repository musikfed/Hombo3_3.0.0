# Полное OTA-обновление MicroPython ядра

Hombo3 всегда умеет обновлять **прикладную MicroPython-прошивку (`*.py`) по Wi-Fi**.
Это основной и безопасный режим разработки робота.

Для обновления **самого ядра MicroPython (`.app-bin`) без USB** плата должна один раз получить
partition table с `ota_0 + ota_1 + otadata`. В этой папке дан вариант для 16 MB Flash.

После однократной USB-миграции дальнейшие `.app-bin` можно отправлять из вкладки `Система / OTA`.
Runtime сам проверяет SHA-256, записывает неактивный OTA-раздел и переключает boot partition.

MicroPython 1.28.0 для ESP32-S3 N16R8 следует использовать в варианте **SPIRAM_OCT**.
Для OTA нужен именно файл `.app-bin`, а не комбинированный `.bin`.

Сборка MicroPython выполняется на Linux/WSL с ESP-IDF. Базовая команда MicroPython для платы:

```bash
make -C ports/esp32 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT
```

Custom partition table должна быть подключена при сборке. Перед реальной прошивкой обязательно
проверить итоговую таблицу `esptool partition-table`/`esp32.Partition.find()`.
