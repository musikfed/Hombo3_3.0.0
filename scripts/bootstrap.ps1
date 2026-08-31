$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv not found. Install uv first." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm/Node.js not found. Install Node.js LTS first." }
Write-Host "[1/4] Python 3.13 + uv virtual environment"
if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }
uv venv --python 3.13 .venv
uv pip install --python .\.venv\Scripts\python.exe -r .\backend\requirements.txt
Write-Host "[2/4] Preserve environment configuration"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host "[3/4] React production build (bundled zero-dependency production panel remains as fallback)"
Set-Location "$Root\frontend"
try {
    npm ci --no-audit --no-fund
    npm run build
    Write-Host "React production build OK" -ForegroundColor Green
} catch {
    Write-Warning "npm build unavailable: $($_.Exception.Message)"
    if (-not (Test-Path "$Root\frontend\dist\index.html")) { throw "No frontend/dist fallback available" }
    Write-Host "Using bundled Hombo3 production panel from frontend/dist" -ForegroundColor Yellow
}
Write-Host "[4/4] Python source checks"
Set-Location $Root
& .\.venv\Scripts\python.exe -m compileall -q backend tools
& .\.venv\Scripts\python.exe .\tools\validate_project.py
Write-Host "Hombo3 3.0 setup complete. Run START_HOMBO3.cmd"
