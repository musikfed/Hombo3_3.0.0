#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || { echo "Virtual environment not found. Run ./SETUP_LINUX.sh first." >&2; exit 1; }
cd "$ROOT/backend"
PORT="$($PY -c 'from app.config import settings; print(settings.app_port)')"
if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$PORT" | grep -q LISTEN; then
  echo "TCP port $PORT is already in use. Stop the old Hombo3 process first." >&2
  exit 1
fi
URL="http://127.0.0.1:$PORT"
echo "Opening Hombo3 3.0 at $URL"
if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true; fi
exec "$PY" run.py
