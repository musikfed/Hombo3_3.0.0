$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Virtual environment not found. Run SETUP.cmd first." }
Set-Location (Join-Path $Root "backend")
$Port = & $Python -c "from app.config import settings; print(settings.app_port)"
$Port = [int]$Port.Trim()
$Busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Busy) {
  $PidList = ($Busy | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
  throw "TCP port $Port is already in use (PID: $PidList). Stop the old Hombo3 process first."
}
$Url = "http://127.0.0.1:$Port"
Write-Host "Opening Hombo3 3.0 Robot Control Center at $Url"
Start-Process $Url
& $Python run.py
