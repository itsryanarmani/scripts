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

**Setup for flashing:** Wi‑Fi board **USB → computer only**. Flipper can stay in a drawer;
it is **not** needed until after Marauder is written.

### Download mode (step by step)

The board ships with **Blackmagic** firmware. `esptool` only works in **ROM download
mode**. The USB name **changes** when you succeed — do not keep using an old port path.

| USB label (typical macOS) | Meaning |
|---------------------------|---------|
| **Blackmagic ESP32** + `cu.usbmodemblackmagic*` | Normal / Blackmagic — **not** ready for `esptool` |
| **ESP32-S2** + `cu.usbmodem01` (or similar short name) | Download mode — **flash now** (window is short) |

**Method A — buttons (board already plugged in):**

1. Hold **BOOT** on the dev board.
2. While holding BOOT, **tap RESET** once.
3. Keep holding BOOT **~10 seconds**, then release.
4. Within **~30 seconds**, run `./flash-marauder.sh` (omit `--port` so the script scans
   ports, or pass the new `cu.usbmodem…` device).

**Method B — plug while holding BOOT (often more reliable):**

1. Unplug USB from the board.
2. Hold **BOOT**.
3. Plug USB into the Mac **while still holding BOOT**.
4. Keep holding **5–10 seconds**, release BOOT.
5. Run `./flash-marauder.sh` immediately.

**If flash fails:** unplug USB, repeat Method A or B. Download mode **times out** quickly;
seeing **ESP32-S2** in System Information for a moment then losing it is normal if you
wait too long.

**After success:** press **RESET** once, unplug USB, stack board on Flipper, open the
Marauder companion app.

### Option A — Mac/Linux helper in this folder

[`flash-marauder.sh`](flash-marauder.sh) downloads official Marauder **Flipper dev board**
binaries from GitHub releases and flashes with `esptool` (via `uvx` if needed).

1. Connect the **dev board only** to the computer with USB (see **Download mode** above).
2. Enter download mode (Method A or B).
3. Run `./flash-marauder.sh` — **do not** pass a stale `--port` from Blackmagic; let the
   script find the bootloader port, or pass the port that appears **after** download mode
   (often `cu.usbmodem01` on macOS).

The script waits up to three minutes, **re-scanning** serial ports each pass.

4. Press **RESET** once after a successful flash.

### Option B — Flipper **ESP Flasher** app (no laptop esptool)

1. Copy the four `.bin` files to the microSD:
   `apps_data/esp_flasher/` (bootloader, partitions, `boot_app0`, and the release asset
   whose name ends in `_flipper.bin`).
2. Stack the board on the Flipper; put the board in download mode (board button combo per
   the app / wiki—often hold one side button, tap the other, release).
3. **Apps → GPIO → ESP Flasher → Manual Flash**, map each file, flash.

### After Marauder is on the board

See **[Daily use (step by step)](#daily-use-step-by-step)** below.

## Daily use (step by step)

Assumes Marauder (or another ESP32 Wi‑Fi firmware) is already on the dev board.

### 1. Physical setup

1. **Power off** the Flipper or at least close apps using GPIO (optional but avoids glitches).
2. **Line up the dev board** with the Flipper’s GPIO pins on the back (board stacks on top of
   the Flipper body).
3. **Press firmly** until seated — all pins must connect.
4. **Do not** plug the dev board’s USB‑C into the Mac for normal use; the Flipper battery
   powers the stack. USB on the board is for **flashing** or **Blackmagic Wi‑Fi debugging**,
   not required for Marauder day‑to‑day.

### 2. Turn on and open the right app

1. Short‑press the Flipper **Back** button to wake/boot.
2. Open the app menu: **OK** on the desktop, or navigate to **Apps**.
3. For Marauder, open the companion app (name varies by install), commonly:
   - **Apps → GPIO → [ESP32 Marauder]** or **WiFi Marauder**, or
   - **Apps → Tools → …** if you installed from the catalog into another folder.
4. If you do not see it: on the Flipper open **Hub / Catalog** (or install from
   [lab.flipper.net](https://lab.flipper.net)) and search **Marauder** or **ESP32 Marauder**,
   then sync to SD and reopen **Apps**.

The Flipper app is a **remote screen and menu** for the ESP32. The actual Wi‑Fi work runs
**on the dev board**, not inside the Flipper main CPU.

### 3. First launch checklist

| Step | What to do |
|------|------------|
| Wait for connect | First open can take **10–30 seconds** while the app talks to the board over GPIO/UART. |
| If it hangs | **Back** out, reseat the board, reboot Flipper, try again. |
| Serial / debug | Only needed for troubleshooting; normal use is all on‑screen menus. |

### 4. What you **can** do (with Marauder on the board)

These are **Wi‑Fi** features on **your lab network** (networks you own or have permission
to test):

| Area | Examples (names vary by Marauder version) |
|------|---------------------------------------------|
| Scan | List nearby Wi‑Fi networks, AP info, channels |
| Sniff / capture | Monitor mode‑style captures (save for analysis on a PC later) |
| Probe / beacon tools | Test how devices behave (lab only) |
| Wardriving‑style logging | GPS needs extra hardware; Flipper alone has no GPS on the board |
| Evil Portal–style setups | **Separate firmware or add‑ons**; not all Marauder builds expose this from the Flipper UI |

Your Flipper **still does** everything it did before **without** the board:

- Sub‑GHz, NFC, RFID, IR, iButton, GPIO (when not used by the board stack), Bluetooth as
  shipped — **unchanged**.

### 5. What you **cannot** do (common misconceptions)

| Myth | Reality |
|------|---------|
| “Wi‑Fi board gives Flipper Wi‑Fi in every app” | **No.** Only apps written to talk to the ESP32 (Marauder companion, WiFi Scanner, etc.) use the board. |
| “Marauder replaces Sub‑GHz or NFC” | **No.** Different hardware. |
| “Flipper alone deauths Wi‑Fi after Marauder flash on the board” | **No** unless you open the Marauder (or similar) app and the firmware supports that action. |
| “Flash Marauder through qFlipper radio recovery” | **Wrong target** — that flashes the Flipper BT coprocessor and can brick boot (see above). |
| “Use offensive Wi‑Fi anywhere” | **Illegal** on others’ networks in most places. |

### 6. Other firmware / apps (not only Marauder)

You can reflash the dev board with other ESP32 projects (each has its own Flipper companion
or UART protocol):

| Firmware type | Typical Flipper side | Use |
|---------------|----------------------|-----|
| **Marauder** | ESP32 Marauder app | Wi‑Fi test / sniff toolkit |
| **Blackmagic** | WiFi dev tools / debugger | Wi‑Fi debugging for developers |
| **Evil Portal** (often separate flash) | Evil Portal app | Captive portal lab demos |
| **WiFi Scanner** (official-style) | WiFi Scanner app | Simpler scanning than full Marauder |

Switching firmware = **reflash the dev board only** (same BOOT+RESET + `flash-marauder.sh`
or ESP Flasher). Flipper SD data stays put.

### 7. How to **extend** features

| Goal | Approach |
|------|----------|
| More Marauder menus / fixes | Reflash board to a **newer** [Marauder `_flipper.bin` release](https://github.com/justcallmekoko/ESP32Marauder/releases); update companion app from catalog if needed. |
| Evil Portal, etc. | Flash firmware built for that project, install matching **Flipper app** from catalog or community bundles. |
| Save captures on PC | Marauder/sniff workflows often export via **serial/USB** or SD on the ESP32 mod — official dev board has **no microSD on the board itself**; check your firmware docs. |
| Flipper automation | **Bad USB / scripts** on Flipper cannot magically drive Marauder unless an app exposes it; use the companion app menus or a PC serial client. |
| Stronger antenna / range | Hardware mods only (antenna, enclosure); software cannot fix bad RF. |
| Developer path | **Blackmagic** firmware + PC tools; or build Marauder from source and flash with `esptool`. |

### 8. Troubleshooting quick table

| Problem | Try |
|---------|-----|
| App says no connection | Reseat board; reboot Flipper; confirm you flashed **`_flipper.bin`**, not WROOM/S3 builds. |
| Board hot / high drain | Normal under heavy Wi‑Fi; remove board when not in use to save battery. |
| Still shows Blackmagic on PC USB | That is the **old firmware label** until you flash Marauder in download mode. |
| Flipper won’t boot | **Unplug/remove Wi‑Fi board**, charge, qFlipper repair — do not assume the board caused it until Flipper boots alone. |

## Legal and safety

Wi‑Fi offensive features (deauth, etc.) can be illegal on networks you do not control.
Use a lab network you own.

## References

- [Flipper wiki — Marauder guide](https://flipper.wiki/tutorials/Marauder_guide/guide/)
- [ESP32Marauder releases](https://github.com/justcallmekoko/ESP32Marauder/releases)
  (asset name ends with `_flipper.bin` for the official dev board)
