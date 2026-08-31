# TEST STATUS — Hombo3 3.0.0

## Автоматически проверяется перед упаковкой

- Python backend/tools compileall;
- синтаксис всех MicroPython файлов;
- фиксированная GPIO-карта и запрет рискованных GPIO;
- батарея: 2S, GPIO2, divider ratio 4.0;
- наличие самодостаточного VL53L0X driver;
- normal Wi-Fi OTA не обновляет boot.py/secrets.py;
- OTA содержит pending marker + .prev rollback;
- provisioner имеет отдельные flash/runtime COM;
- версия 3.0.0 согласована;
- private/public packaging исключает caches/node_modules/.venv/logs и секреты из public.

## Аппаратный acceptance test после пайки

1. Прозвонка питания без ESP32.
2. Проверка 5 В / 3.3 В / 2S BMS.
3. ADC делитель: при измеренном BMS P+/P- сверить GPIO2 и откалибровать BATTERY_CALIBRATION.
4. HC-SR04 по одному, затем последовательный опрос трёх.
5. VL53L0X I2C 0x29 и контрольные расстояния.
6. MAX98357A при отключённом VM.
7. Борты на вывешенных колёсах, затем TTL/watchdog/STOP.
8. ONVIF/RTSP/mic/PTZ.
9. VectorProbe static map + live track.
10. Wired и wireless charging через единый штатный charge/BMS path.
