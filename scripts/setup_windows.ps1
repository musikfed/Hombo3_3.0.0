$ErrorActionPreference = "Stop"
# Compatibility entry point. Hombo3 uses Python 3.13 + uv and the canonical bootstrap.
& (Join-Path $PSScriptRoot "bootstrap.ps1")
