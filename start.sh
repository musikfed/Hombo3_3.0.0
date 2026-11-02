#!/usr/bin/env bash
# Existing Hombo3 starter remains authoritative. Foreground by design.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$ROOT/START_HOMBO3_LINUX.sh" "$@"
