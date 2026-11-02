$ErrorActionPreference = 'Stop'
# Windows: first command the robot to stop motors, THEN stop this repo's
# backend process only. Do NOT kill the ESP32, camera, or unrelated Python.
$Root = $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Hombo3 virtualenv missing; no robot shutdown performed.' }
$Expected = [IO.Path]::GetFullPath($Python)
$Matches = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
    Where-Object {
        $_.ExecutablePath -and
        ([IO.Path]::GetFullPath($_.ExecutablePath) -ieq $Expected) -and
        ($_.CommandLine -match '(^|\s)run\.py(\s|$)')
    })
if ($Matches.Count -eq 0) {
    Write-Host 'Hombo3 backend not running from this checkout.'
    return
}
Push-Location (Join-Path $Root 'backend')
try {
    $Port = [int](& $Python -c 'from app.config import settings; print(settings.app_port)')
}
finally { Pop-Location }
Write-Host "Sending safe motor STOP through Hombo3 localhost:$Port ..."
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/stop" `
        -Method Post -ContentType 'application/json' -Body '{"voice":false}' -TimeoutSec 8
}
catch {
    throw "SAFETY: ESP32 motor stop not confirmed. Backend remains running. $_"
}
foreach ($Process in $Matches) {
    Stop-Process -Id $Process.ProcessId -ErrorAction Stop
    Write-Host "Stopped Hombo3 backend process $($Process.ProcessId)."
}
Write-Host 'Other projects, camera and ESP32 firmware were not touched.'
