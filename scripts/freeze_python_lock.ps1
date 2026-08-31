$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
$Out = Join-Path $Root "backend\requirements.lock.txt"
if (-not (Test-Path $Python)) { throw "Virtual environment not found. Run scripts\setup_windows.ps1 first." }
& $Python -m pip freeze | Set-Content -Encoding utf8 $Out
Write-Host "Python lock written to $Out"
