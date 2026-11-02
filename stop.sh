#!/usr/bin/env bash
# STOP robot motion BEFORE stopping the PC control server.
# Fail closed if ESP32 doesn't confirm the stop; never kill unrelated Python.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || { echo "Hombo3 virtualenv missing: $PY" >&2; exit 2; }
command -v python3 >/dev/null || { echo "python3 required" >&2; exit 2; }
command -v curl >/dev/null || { echo "curl required for robot motor STOP safety" >&2; exit 2; }
mapfile -t PIDS < <(python3 - "$BACKEND" <<'PY'
import os, pathlib, sys
backend = os.path.realpath(sys.argv[1])
for p in pathlib.Path("/proc").iterdir():
    if not p.name.isdigit():
        continue
    try:
        cwd = os.path.realpath(str(p / "cwd"))
        raw = (p / "cmdline").read_bytes().split(b"\0")
        args = [x.decode(errors="replace") for x in raw if x]
        if cwd == backend and args and os.path.basename(args[0]).startswith("python") and "run.py" in args[1:]:
            print(p.name)
    except (OSError, PermissionError):
        continue
PY
)
if [ "${#PIDS[@]}" -eq 0 ]; then
  echo "Hombo3 backend is not running from this checkout."
  exit 0
fi
cd "$BACKEND"
PORT="$("$PY" -c 'from app.config import settings; print(settings.app_port)')"
case "$PORT" in *[!0-9]*|'') echo "ERROR: invalid Hombo3 port" >&2; exit 2;; esac
echo "Hombo3: sending motor STOP to ESP32 through localhost:$PORT before terminating backend..."
if ! curl --fail --silent --show-error --max-time 8 \
  -H 'Content-Type: application/json' -d '{"voice":false}' \
  -o /dev/null "http://127.0.0.1:$PORT/api/stop"; then
  echo "SAFETY: robot STOP could not be confirmed. Backend was NOT terminated." >&2
  echo "Securely stop motors on the robot itself before changing anything." >&2
  exit 1
fi
echo "Robot STOP acknowledged; stopping Hombo3 backend only."
for PID in "${PIDS[@]}"; do
  kill -TERM "$PID" 2>/dev/null || true
done
echo "Stop signal sent. Existing SSH, camera, ESP32 firmware and other services were not changed."
