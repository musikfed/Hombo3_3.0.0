#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
command -v uv >/dev/null 2>&1 || { echo "uv not found" >&2; exit 1; }
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r backend/requirements.txt
[ -f .env ] || cp .env.example .env
if command -v npm >/dev/null 2>&1; then
  if ! (cd frontend && npm ci --no-audit --no-fund && npm run build); then
    echo "WARNING: npm build unavailable; keeping bundled frontend/dist production panel." >&2
    test -f frontend/dist/index.html
  fi
else
  echo "WARNING: npm/Node.js absent; keeping bundled frontend/dist production panel." >&2
fi
.venv/bin/python -m compileall -q backend tools
.venv/bin/python tools/validate_project.py
printf 'Hombo3 3.0 setup complete. Run ./START_HOMBO3_LINUX.sh\n'
