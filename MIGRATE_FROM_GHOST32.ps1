param(
    [string]$DeviceUrl = "http://192.168.1.33",
    [Parameter(Mandatory=$true)]
    [string]$Token,
    [string]$RecoveryPassword = "",
    [string]$ProjectRoot = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
$DeviceUrl = $DeviceUrl.TrimEnd('/')
$DeviceDir = Join-Path $ProjectRoot "firmware\hombowifi_s3_micropython\device"
if (-not (Test-Path $DeviceDir)) { throw "Не найдена device-папка: $DeviceDir" }
if ($Token.Length -lt 8) { throw "Token слишком короткий; используй текущий Ghost32 API token." }
if (-not $RecoveryPassword) {
    $RecoveryPassword = if ($Token.Length -gt 63) { $Token.Substring(0,63) } else { $Token }
}
if ($RecoveryPassword.Length -lt 8 -or $RecoveryPassword.Length -gt 63) { throw "RecoveryPassword должен быть 8..63 символа." }

$headers = @{ "X-API-Token" = $Token }
Write-Host "[1/7] Проверка текущего Ghost32 API $DeviceUrl" -ForegroundColor Cyan
$auth = Invoke-RestMethod -Method Get -Uri "$DeviceUrl/api/auth/check" -Headers $headers -TimeoutSec 5
if (-not $auth.ok) { throw "Ghost32 не подтвердил token" }
Write-Host "  AUTH OK" -ForegroundColor Green

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $ProjectRoot "backup_ghost32_$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Write-Host "[2/7] Backup Ghost32 runtime -> $backupDir" -ForegroundColor Cyan
foreach ($name in @("boot.py","main.py","config_store.py","pin_manager.py","wifi_manager.py","server.py","config.json")) {
    try {
        $escaped = [uri]::EscapeDataString("/$name")
        Invoke-WebRequest -Method Get -Uri "$DeviceUrl/api/fs?path=$escaped" -Headers $headers -TimeoutSec 5 -OutFile (Join-Path $backupDir $name)
        Write-Host "  saved $name"
    } catch { Write-Host "  skip $name" -ForegroundColor DarkYellow }
}

$temp = Join-Path $ProjectRoot ".deploy-tmp"
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $temp | Out-Null
Copy-Item (Join-Path $DeviceDir "*") $temp -Force

function ConvertTo-PythonLiteral([string]$Value) {
    $v = $Value.Replace("\", "\\").Replace("'", "\'")
    return "'$v'"
}

Write-Host "[3/7] Привязываю Hombo3 API к тому же token и Recovery AP" -ForegroundColor Cyan
$secretsPath = Join-Path $temp "secrets.py"
$secrets = Get-Content $secretsPath -Raw -Encoding UTF8
$pyToken = ConvertTo-PythonLiteral $Token
$pyRecovery = ConvertTo-PythonLiteral $RecoveryPassword
if ($secrets -match '(?m)^API_TOKEN\s*=') { $secrets = [regex]::Replace($secrets,'(?m)^API_TOKEN\s*=.*$',"API_TOKEN = $pyToken") } else { $secrets += "`nAPI_TOKEN = $pyToken`n" }
if ($secrets -match '(?m)^RECOVERY_AP_PASSWORD\s*=') { $secrets = [regex]::Replace($secrets,'(?m)^RECOVERY_AP_PASSWORD\s*=.*$',"RECOVERY_AP_PASSWORD = $pyRecovery") } else { $secrets += "`nRECOVERY_AP_PASSWORD = $pyRecovery`n" }
Set-Content -Path $secretsPath -Value $secrets -Encoding UTF8

$envPath = Join-Path $ProjectRoot ".env"
$env = Get-Content $envPath -Raw -Encoding UTF8
if ($env -match '(?m)^ESP32_API_TOKEN=') { $env = [regex]::Replace($env,'(?m)^ESP32_API_TOKEN=.*$',"ESP32_API_TOKEN=$Token") } else { $env += "`nESP32_API_TOKEN=$Token`n" }
$hostOnly = ([uri]$DeviceUrl).Host
$env = [regex]::Replace($env,'(?m)^ESP32_BASE_URL=.*$',"ESP32_BASE_URL=$DeviceUrl")
$env = [regex]::Replace($env,'(?m)^ESP32_AUDIO_HOST=.*$',"ESP32_AUDIO_HOST=$hostOnly")
Set-Content -Path $envPath -Value $env -Encoding UTF8

$files = @(
    "board_config.py","motion.py","vl53l0x.py","sensors.py","audio_service.py","power.py",
    "ota_runtime.py","ota_core.py","secrets.py","wifi_manager.py","server.py",
    "boot.py","main.py"
)
Write-Host "[4/7] Загружаю Robot Control Center через ТЕКУЩУЮ Wi-Fi сеть" -ForegroundColor Cyan
foreach ($name in $files) {
    $src = Join-Path $temp $name
    $escaped = [uri]::EscapeDataString("/$name")
    Invoke-RestMethod -Method Put -Uri "$DeviceUrl/api/fs?path=$escaped" -Headers $headers -InFile $src -ContentType "application/octet-stream" -TimeoutSec 12 | Out-Null
    Write-Host "  OK $name ($((Get-Item $src).Length) bytes)" -ForegroundColor Green
}

Write-Host "[5/7] Перезагрузка ESP32-S3" -ForegroundColor Cyan
try { Invoke-RestMethod -Method Post -Uri "$DeviceUrl/api/reboot" -Headers $headers -ContentType "application/json" -Body "{}" -TimeoutSec 5 | Out-Null } catch {}

Write-Host "[6/7] Ожидаю Hombo3 3.0 на $DeviceUrl" -ForegroundColor Cyan
$online = $false
for ($i=0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $t = Invoke-RestMethod -Method Get -Uri "$DeviceUrl/api/telemetry" -TimeoutSec 2
        if ($t.ok -and $t.project -like "hombo3*") {
            $online = $true
            Write-Host "  ONLINE: $($t.project) $($t.runtime_version) $($t.board) IP=$($t.ip)" -ForegroundColor Green
            break
        }
    } catch {}
}
if (-not $online) { throw "Hombo3 не поднялся за 30 секунд. Используй COM5 + RECOVERY_PROVISION_COM.ps1." }

Write-Host "[7/7] Проверка нового token" -ForegroundColor Cyan
$newAuth = Invoke-RestMethod -Method Get -Uri "$DeviceUrl/api/auth/check" -Headers $headers -TimeoutSec 5
if (-not $newAuth.ok) { throw "Новый Hombo3 API не принял token" }
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "ГОТОВО. Дальше обновления Runtime идут по Wi-Fi из вкладки 'Прошивка / сеть'." -ForegroundColor Green
