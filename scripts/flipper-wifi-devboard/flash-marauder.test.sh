#!/usr/bin/env bash
# Offline tests for flash-marauder.sh — no network, no USB, no esptool.
set -uo pipefail

fail=0
pass=0
ok() { echo "ok - $1"; pass=$((pass+1)); }
bad() { echo "FAIL - $1"; fail=$((fail+1)); }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SCRIPT_DIR/flash-marauder.sh"

ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
mkdir -p "$ROOT/bin" "$ROOT/cache"
for f in bootloader.bin partitions.bin boot_app0.bin esp32_marauder_flipper.bin; do
  echo x > "$ROOT/cache/$f"
done

cat > "$ROOT/bin/curl" <<'STUB'
#!/usr/bin/env bash
echo "curl should not run in dry-run with prefilled cache" >&2
exit 1
STUB
chmod +x "$ROOT/bin/curl"

cat > "$ROOT/bin/esptool" <<'STUB'
#!/usr/bin/env bash
if [ "$1" = "--chip" ] && [ "$4" = "chip-id" ]; then
  echo "Chip is ESP32-S2 (stub)"
  exit 0
fi
echo "esptool stub: $*" >&2
exit 0
STUB
chmod +x "$ROOT/bin/esptool"

FAKE_PORT="$ROOT/fake.port"
touch "$FAKE_PORT"

out=$(PATH="$ROOT/bin:$PATH" "$SCRIPT" --port "$FAKE_PORT" --cache-dir "$ROOT/cache" --dry-run 2>&1)
case "$out" in
  *dry-run*) ok "dry-run prints intent" ;;
  *) bad "dry-run output: $out" ;;
esac

grep -q 'qFlipper' "$SCRIPT_DIR/README.md" && ok "README warns about qFlipper radio path" || bad "README missing qFlipper warning"
grep -q '303A' "$SCRIPT_DIR/README.md" && ok "README mentions download-mode USB hint" || bad "README missing download-mode hint"

echo
echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
