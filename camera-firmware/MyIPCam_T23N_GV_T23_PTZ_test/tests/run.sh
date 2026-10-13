#!/usr/bin/env bash
# EN: Fast source checks; optionally pass a built .bin image.
# RU: Быстрые проверки исходников; можно передать готовый .bin образ.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
bash -n "$ROOT/build-stage2.sh"
python3 "$HERE/test_web_static.py" "$ROOT/web"
if [ "${1:-}" != "" ]; then python3 "$HERE/test_image_layout.py" "$1"; fi
echo "ALL TESTS PASSED"
