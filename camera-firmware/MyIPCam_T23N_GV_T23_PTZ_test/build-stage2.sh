#!/usr/bin/env bash
# MyIPCam OS Stage2 image builder.
# EN: Rebuilds a clean test image from the known-good Thingino donor output.
# RU: Пересобирает чистый тестовый образ из проверенного донорского вывода Thingino.
#
# This script does NOT patch an already modified Stage1 rootfs.
# Этот скрипт НЕ патчит уже изменённый rootfs Stage1.
set -euo pipefail

CAMERA="${MYIPCAM_CAMERA_PROFILE:-galayou_g2_t23n_sc2336_atbm6012bx}"
OUT="${MYIPCAM_THINGINO_OUT:-$HOME/thingino-firmware/output/ciao/${CAMERA}-3.10.14-uclibc}"
BASE="${MYIPCAM_BASE_IMAGE:-$OUT/images/thingino-${CAMERA}.bin}"
ORIG_ROOTFS="${MYIPCAM_ROOTFS_IMAGE:-$OUT/images/rootfs.ext2}"
EXPECTED_BASE_SHA="${MYIPCAM_EXPECTED_BASE_SHA:-038d032f20c90b444f13f936f6f4bbae88b3f07bd148f3cfc733607ca736e30d}"

HERE="$(cd "$(dirname "$0")" && pwd)"
WEB="$HERE/web"
DEST="${MYIPCAM_DEST:-/mnt/f/MyIPCam/build}"
WORK="${MYIPCAM_WORK:-/mnt/f/MyIPCam/stage2-work}"
ROOT="$WORK/rootfs-stage2.ext2"
IMG="$DEST/MyIPCam_OS_3.1_T23N_stage2.bin"

mkdir -p "$DEST" "$WORK"

# EN: Fail early if any build input is missing.
# RU: Сразу останавливаемся, если не хватает исходных файлов.
for f in "$BASE" "$ORIG_ROOTFS" "$WEB/index.html" "$WEB/style.css" "$WEB/app.js" "$WEB/boot.js"; do
  [ -f "$f" ] || { echo "ERROR: missing $f"; exit 1; }
done

echo "=== VERIFY KNOWN-GOOD BASE ==="
BASE_SHA=$(sha256sum "$BASE" | awk '{print $1}')
echo "BASE SHA256: $BASE_SHA"
[ "$BASE_SHA" = "$EXPECTED_BASE_SHA" ] || {
  echo "ERROR: donor image is not the expected known-good base."
  echo "Expected: $EXPECTED_BASE_SHA"
  exit 1
}

echo "=== FRESH COPY FROM ORIGINAL ROOTFS ==="
rm -f "$ROOT" "$IMG"
cp --sparse=always "$ORIG_ROOTFS" "$ROOT"
cp "$BASE" "$IMG"

echo "=== INSTALL MYIPCAM STAGE2 ==="
CMDS="$WORK/debugfs-stage2.cmd"
cat > "$CMDS" <<EOF2
rm /var/www/index.html
write $WEB/index.html /var/www/index.html
mkdir /var/www/myipcam
write $WEB/style.css /var/www/myipcam/style.css
write $WEB/app.js /var/www/myipcam/app.js
write $WEB/boot.js /var/www/myipcam/boot.js
EOF2

debugfs -w -f "$CMDS" "$ROOT" >/dev/null

echo "=== VERIFY WEB ==="
# EN: Dump first, then grep. This avoids SIGPIPE + pipefail false failures.
# RU: Сначала выгружаем файл, потом grep — так pipefail не ловит ложный SIGPIPE.
debugfs -R 'cat /var/www/index.html' "$ROOT" 2>/dev/null > "$WORK/verify-index.html"
debugfs -R 'cat /var/www/myipcam/boot.js' "$ROOT" 2>/dev/null > "$WORK/verify-boot.js"
debugfs -R 'cat /var/www/myipcam/app.js' "$ROOT" 2>/dev/null > "$WORK/verify-app.js"
grep -Fq 'MyIPCam OS 3.1' "$WORK/verify-index.html"
grep -Fq '/x/login.cgi' "$WORK/verify-boot.js"
grep -Fq 'credentials:"same-origin"' "$WORK/verify-app.js"
echo "MyIPCam UI      : OK"
echo "MyIPCam login   : OK"
echo "Session backend : OK"

echo "=== ROOTFS CHECK ==="
e2fsck -fn "$ROOT"

read -r P2_START P2_SIZE < <(
python3 - "$BASE" <<'PY'
import struct, sys
with open(sys.argv[1], "rb") as f:
    mbr = f.read(512)
entry = mbr[446 + 16:446 + 32]
print(*struct.unpack_from("<II", entry, 8))
PY
)
ROOT_SECTORS=$(( ($(stat -c%s "$ROOT") + 511) / 512 ))
echo "P2 start sectors : $P2_START"
echo "P2 size sectors  : $P2_SIZE"
echo "Rootfs sectors   : $ROOT_SECTORS"
[ "$ROOT_SECTORS" -le "$P2_SIZE" ] || { echo "ERROR: rootfs too large"; exit 1; }

echo "=== PATCH ROOTFS INTO IMAGE ==="
dd if="$ROOT" of="$IMG" bs=512 seek="$P2_START" conv=notrunc status=progress
sync

echo "=== VERIFY BOOT/FAT UNCHANGED ==="
cmp -n $((P2_START * 512)) "$BASE" "$IMG"
echo "BOOT/FAT: IDENTICAL"

echo "=== VERIFY ROOTFS READBACK ==="
A=$(sha256sum "$ROOT" | awk '{print $1}')
B=$(dd if="$IMG" bs=512 skip="$P2_START" count="$ROOT_SECTORS" status=none | sha256sum | awk '{print $1}')
echo "ROOTFS SOURCE   : $A"
echo "ROOTFS IN IMAGE : $B"
[ "$A" = "$B" ] || { echo "ERROR: rootfs mismatch"; exit 1; }

# EN: Validate the final SD layout and web files.
# RU: Проверяем итоговую разметку SD и статические файлы веб-интерфейса.
python3 "$HERE/tests/test_image_layout.py" "$IMG"
python3 "$HERE/tests/test_web_static.py" "$HERE/web"

echo
echo "=== FINAL STAGE2 IMAGE ==="
ls -lh "$IMG"
sha256sum "$IMG"
echo
echo "READY: $IMG"
