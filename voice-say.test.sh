#!/usr/bin/env bash
# E2E for voice-say. One real call (about $0.001). Controls must fail.
# Needs the saved voice record and key. Writes a JSON verdict to $1 or stdout.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
res="$tmp/res"; : > "$res"
ok() { printf '%s\t%s\n' "$1" "$2" >> "$res"; }
run() { "$here/voice-say" "$@" </dev/null >"$tmp/o" 2>"$tmp/e"; echo $?; }

# 1. A dry run prints the price and sends nothing.
rc=$(run "$(python3 -c 'print("a"*1000)')" "$tmp/d.mp3" --dry-run)
grep -q 'about \$0.1000' "$tmp/o" && [[ $rc == 0 && ! -e "$tmp/d.mp3" ]] && ok dry_run_prices_and_sends_nothing true || ok dry_run_prices_and_sends_nothing false

# 2. CONTROL: over the cap without --yes is refused (exit 2) and sends nothing.
rc=$(run "$(python3 -c 'print("a"*12000)')" "$tmp/c.mp3")
[[ $rc == 2 && ! -e "$tmp/c.mp3" ]] && grep -q 'over the cap' "$tmp/e" && ok control_over_cap_refused true || ok control_over_cap_refused false

# 3. CONTROL: a missing voice record is refused (exit 2).
rc=$(run "hi" "$tmp/m.mp3" --voice-file "$tmp/none.json")
[[ $rc == 2 ]] && grep -q 'no voice record' "$tmp/e" && ok control_missing_voice_refused true || ok control_missing_voice_refused false

# 4. CONTROL: empty text and a bad extension are refused (exit 2).
r1=$(run "" "$tmp/e.mp3"); r2=$(run "hi" "$tmp/e.txt")
[[ $r1 == 2 && $r2 == 2 ]] && ok control_empty_text_and_bad_extension_refused true || ok control_empty_text_and_bad_extension_refused false

# 5. A real call: audible speech of a sane length, and no key in the output.
rc=$(run "Hello. This is a short test of my voice." "$tmp/real.mp3")
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$tmp/real.mp3" 2>/dev/null || echo 0)
mx=$(ffmpeg -hide_banner -i "$tmp/real.mp3" -af volumedetect -f null - 2>&1 </dev/null | sed -n 's/.*max_volume: \(-\{0,1\}[0-9.]*\) dB.*/\1/p')
python3 -I - "$rc" "$dur" "${mx:--99}" <<'PY' && ok real_clip_audible_and_sane_length true || ok real_clip_audible_and_sane_length false
import sys
rc, dur, mx = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
sys.exit(0 if rc == 0 and 1.0 <= dur <= 15 and mx > -30 else 1)
PY
key="$(. "${VOICE_SECRETS:-$HOME/Documents/Personal/.secrets}/wavespeed.env" 2>/dev/null; echo "${WAVESPEED_API_KEY:-}")"
if [[ -n "$key" ]] && ! grep -qF "$key" "$tmp/o" "$tmp/e"; then ok key_not_printed true; else ok key_not_printed false; fi

python3 -I - "$res" "${1:-}" <<'PY'
import json, sys
checks = dict((a, b == "true") for a, b in (l.rstrip("\n").split("\t") for l in open(sys.argv[1])))
v = {"checks": checks, "pass": all(checks.values()) and len(checks) == 6}
s = json.dumps(v, indent=2)
print(s)
if sys.argv[2]: open(sys.argv[2], "w").write(s + "\n")
sys.exit(0 if v["pass"] else 1)
PY
