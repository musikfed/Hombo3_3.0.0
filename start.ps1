$ErrorActionPreference = 'Stop'
# Foreground, same tested launcher as START_HOMBO3.cmd; no new backend.
& (Join-Path $PSScriptRoot 'scripts/run.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
