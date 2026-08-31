#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
read -rp "FLASH / bootloader port (example /dev/ttyACM0): " FLASHPORT
read -rp "MicroPython RUNTIME / REPL port (or auto): " RUNTIMEPORT
RUNTIMEPORT=${RUNTIMEPORT:-auto}
.venv/bin/python ./tools/provision_device.py --flash-port "$FLASHPORT" --runtime-port "$RUNTIMEPORT"
