# Flipper Zero Wi‑Fi dev board

Notes and helpers for the **ESP32‑S2 Wi‑Fi Developer Board** (stacked on a Flipper or
plugged into a computer over USB). No device names, serial numbers, or local paths from
real machines appear here.

## What the board is

The official Wi‑Fi dev board **already contains an ESP32‑S2**. You do **not** need a
separate ESP32 module. Marauder and similar firmware run **on this board only**.

The Flipper main unit has **no Wi‑Fi radio**. Marauder‑style Wi‑Fi features require this
add‑on (or another ESP32 with Wi‑Fi).

## Two different “flash” targets (do not mix them up)

| Target | Tool | What it changes | Risk to Flipper apps / SD |
|--------|------|-----------------|-----------------------------|
| **Wi‑Fi dev board (ESP32)** | `esptool`, ESP Web Flasher, Flipper **ESP Flasher** app, or `flash-marauder.sh` | Firmware on the **add‑on** | **Low** — Flipper storage untouched |
| **Flipper “wireless stack” / `core2radio` / recovery `.bin` via qFlipper** | qFlipper CLI recovery | Bluetooth **coprocessor** on the Flipper | **High** — failed update can leave **DFU mode** (blank screen, won’t boot) |

**Never** install Marauder by pushing a “radio” or `core2radio` image through qFlipper
recovery. That path is for the Flipper’s internal wireless stack, not Marauder Wi‑Fi on
the dev board, and a failed coprocessor flash can brick normal boot until you run an
official **Full Repair** (which usually preserves SD card data but is stressful).

## Symptom: Flipper won’t turn on but USB shows “DFU in FS Mode”

The main MCU is stuck in **STM32 DFU / recovery**, often after a **failed wireless stack**
update—not because the battery is dead.

**Safe fix (data‑preserving in typical cases):**

1. Leave the Wi‑Fi board out or disconnected for this step.
2. Run qFlipper **Firmware Update / Repair** (CLI with no args, or the app)—**not** `wipe`
   or `erase`.
3. Wait for **Full Repair** to finish; the device should reappear as a normal Flipper USB
   serial device, not `PID_df11` DFU.

Keep a prior **internal storage backup** (`qFlipper-cli backup …`) if you have one; SD
card files are on the microSD and are separate from internal flash.

## Flash Marauder on the Wi‑Fi dev board (correct path)

### Option A — Mac/Linux helper in this folder

[`flash-marauder.sh`](flash-marauder.sh) downloads official Marauder **Flipper dev board**
binaries from GitHub releases and flashes with `esptool` (via `uvx` if needed).

1. Connect the **dev board only** to the computer with USB (direct port on the board, not
   only through the Flipper, if flashing fails).
2. Enter **download mode** on the board:
   - Hold **BOOT**
   - Press and release **RESET** (while still holding BOOT)
   - Wait a few seconds, release **BOOT**
3. Run `./flash-marauder.sh` (or `./flash-marauder.sh --port /dev/cu.…`).

In download mode, macOS often shows an Espressif USB device (`VID 0x303A`), not
“Blackmagic ESP32”. If `esptool` cannot connect, the board is still running Blackmagic
or normal firmware—repeat step 2.

4. Press **RESET** once after a successful flash.

### Option B — Flipper **ESP Flasher** app (no laptop esptool)

1. Copy the four `.bin` files to the microSD:
   `apps_data/esp_flasher/` (bootloader, partitions, `boot_app0`, and the release asset
   whose name ends in `_flipper.bin`).
2. Stack the board on the Flipper; put the board in download mode (board button combo per
   the app / wiki—often hold one side button, tap the other, release).
3. **Apps → GPIO → ESP Flasher → Manual Flash**, map each file, flash.

### After Marauder is on the board

1. Stack the board on the Flipper.
2. Install/open the **ESP32 Marauder** companion app on the Flipper (app catalog / SD).
3. Use only on networks you own or are allowed to test.

## Legal and safety

Wi‑Fi offensive features (deauth, etc.) can be illegal on networks you do not control.
Use a lab network you own.

## References

- [Flipper wiki — Marauder guide](https://flipper.wiki/tutorials/Marauder_guide/guide/)
- [ESP32Marauder releases](https://github.com/justcallmekoko/ESP32Marauder/releases)
  (asset name ends with `_flipper.bin` for the official dev board)
