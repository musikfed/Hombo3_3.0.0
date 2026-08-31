param(
    [string]$Port = "COM5",
    [string]$ProjectRoot = $PSScriptRoot
)
$ErrorActionPreference="Stop"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
$dir = Join-Path $ProjectRoot "firmware\hombowifi_s3_micropython\device"
$files = @("board_config.py","motion.py","vl53l0x.py","sensors.py","audio_service.py","power.py","ota_runtime.py","ota_core.py","secrets.py","wifi_manager.py","server.py","boot.py","main.py")
Write-Host "Recovery provision через рабочий MicroPython REPL $Port" -ForegroundColor Cyan
foreach($name in $files){
  & $python -m mpremote connect $Port cp (Join-Path $dir $name) ":$name"
  if($LASTEXITCODE -ne 0){throw "mpremote failed: $name"}
}
& $python -m mpremote connect $Port reset
Write-Host "Готово. Это аварийный путь; обычные обновления после этого делаются по Wi-Fi." -ForegroundColor Green
