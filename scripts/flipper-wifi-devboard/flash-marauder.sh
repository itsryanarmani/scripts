#!/usr/bin/env bash
# Flash ESP32Marauder onto a Flipper Zero Wi‑Fi dev board (ESP32-S2) via esptool.
# Does not touch the Flipper main firmware or qFlipper recovery radio images.
set -euo pipefail

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \?//'
  echo
  echo "Usage: $0 [--port /dev/cu.usbmodem…] [--version v1.20.0] [--cache-dir DIR] [--dry-run]"
  exit 2
}

PORT=""
MARAUDER_VERSION="v1.20.0"
CACHE_DIR="${TMPDIR:-/tmp}/flipper-marauder-flash"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage ;;
    --port) PORT="${2:?}"; shift 2 ;;
    --version) MARAUDER_VERSION="${2:?}"; shift 2 ;;
    --cache-dir) CACHE_DIR="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

run_esptool() {
  if command -v esptool >/dev/null 2>&1; then
    esptool "$@"
  elif command -v esptool.py >/dev/null 2>&1; then
    esptool.py "$@"
  else
    uvx --from esptool esptool "$@"
  fi
}

# zsh-friendly glob (no error when no matches)
usb_serial_ports() {
  local p
  for p in /dev/cu.usbmodem* /dev/tty.usbmodem*; do
    [ -e "$p" ] || continue
    case "$p" in *Bluetooth*) continue ;; esac
    echo "$p"
  done
}

esp32_s2_bootloader_port() {
  local p out fixed="${1:-}"
  if [ -n "$fixed" ]; then
    out=$(run_esptool --chip esp32s2 --port "$fixed" -b 115200 chip-id 2>&1) || true
    if echo "$out" | grep -qiE 'esp32-s2'; then
      echo "$fixed"
      return 0
    fi
    return 1
  fi
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    out=$(run_esptool --chip esp32s2 --port "$p" -b 115200 chip-id 2>&1) || true
    if echo "$out" | grep -qiE 'esp32-s2'; then
      echo "$p"
      return 0
    fi
  done < <(usb_serial_ports)
  return 1
}

mkdir -p "$CACHE_DIR"
FW_BIN="$CACHE_DIR/esp32_marauder_flipper.bin"
BOOT_BIN="$CACHE_DIR/bootloader.bin"
PART_BIN="$CACHE_DIR/partitions.bin"
APP0_BIN="$CACHE_DIR/boot_app0.bin"

fetch() {
  local url="$1" dest="$2"
  if [ -f "$dest" ] && [ -s "$dest" ]; then
    return
  fi
  echo "fetch $dest"
  curl -fsSL -o "$dest" "$url"
}

if [ ! -s "$FW_BIN" ]; then
  latest=$(
    curl -fsSL "https://api.github.com/repos/justcallmekoko/ESP32Marauder/releases/tags/${MARAUDER_VERSION}" \
      | python3 -c "import json,sys; r=json.load(sys.stdin); print(next(a['browser_download_url'] for a in r.get('assets',[]) if a['name'].endswith('_flipper.bin')))"
  )
  fetch "$latest" "$FW_BIN"
fi

fetch "https://github.com/justcallmekoko/ESP32Marauder/raw/master/FlashFiles/FlipperZeroDevBoard/esp32_marauder.ino.bootloader.bin" "$BOOT_BIN"
fetch "https://github.com/justcallmekoko/ESP32Marauder/raw/master/FlashFiles/FlipperZeroDevBoard/esp32_marauder.ino.partitions.bin" "$PART_BIN"
fetch "https://github.com/justcallmekoko/ESP32Marauder/raw/master/FlashFiles/FlipperZeroDevBoard/boot_app0.bin" "$APP0_BIN"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run: would wait for ESP32-S2 download mode, erase-flash, write-flash"
  echo "  firmware: $FW_BIN"
  exit 0
fi

echo "Board USB → this computer only (Flipper not required)."
echo "Download mode: hold BOOT, tap RESET, hold BOOT ~10s — or hold BOOT while plugging USB."
echo "Waiting for ESP32-S2 ROM bootloader (re-scanning ports)…"

deadline=$((SECONDS + 180))
ACTIVE_PORT=""
while [ "$SECONDS" -lt "$deadline" ]; do
  if ACTIVE_PORT=$(esp32_s2_bootloader_port "$PORT"); then
    break
  fi
  sleep 2
done

if [ -z "$ACTIVE_PORT" ]; then
  echo "Could not talk to ESP32-S2 in download mode." >&2
  echo "USB probably still shows Blackmagic — repeat BOOT+RESET or hold BOOT while replugging USB." >&2
  echo "Do not pass --port from Blackmagic; omit it or use the port that appears after download mode." >&2
  exit 1
fi

echo "Using port: $ACTIVE_PORT"

run_esptool --chip esp32s2 --port "$ACTIVE_PORT" -b 460800 erase-flash
run_esptool --chip esp32s2 --port "$ACTIVE_PORT" -b 460800 write-flash --flash-mode dio --flash-freq 80m --flash-size 4MB \
  0x1000 "$BOOT_BIN" \
  0x8000 "$PART_BIN" \
  0xE000 "$APP0_BIN" \
  0x10000 "$FW_BIN"
echo "Done. Press RESET on the dev board, stack on Flipper, open the Marauder companion app."
