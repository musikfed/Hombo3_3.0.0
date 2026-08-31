@echo off
cd /d "%~dp0"
echo Hombo3 3.0 - FIRST FLASH / dual COM ESP32-S3
set /p FLASHPORT=FLASH / bootloader COM (example COM4): 
set /p RUNTIMEPORT=MicroPython RUNTIME / REPL COM (example COM5, or auto): 
if "%RUNTIMEPORT%"=="" set RUNTIMEPORT=auto
".venv\Scripts\python.exe" ".\tools\provision_device.py" --flash-port %FLASHPORT% --runtime-port %RUNTIMEPORT%
pause
