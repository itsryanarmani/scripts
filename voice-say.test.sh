#!/usr/bin/env bash
# E2E for voice-say. One real call (about $0.001). Controls must fail.
# A stub `wavespeed` counts calls, so a refusal proves nothing was sent.
# Needs the saved voice record and key. Writes a JSON verdict to $1 or stdout.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
res="$tmp/res"; : > "$res"
ok() { printf '%s\t%s\n' "$1" "$2" >> "$res"; }

mkdir "$tmp/stub"
cat > "$tmp/stub/wavespeed" <<'STUB'
#!/usr/bin/env bash
echo x >> "$STUB_CALLS"
[[ -n "${STUB_LEAK:-}" ]] && { echo "boom key=$WAVESPEED_API_KEY"; exit 1; }
exit 0
STUB
chmod +x "$tmp/stub/wavespeed"
export STUB_CALLS="$tmp/calls"

# Run with the stub first on PATH. Prints the exit status.
stub() { : > "$STUB_CALLS"; PATH="$tmp/stub:$PATH" WAVESPEED_API_KEY="${KEY_FOR_STUB:-fake-key-123}" \
  "$here/voice-say" "$@" </dev/null >"$tmp/o" 2>"$tmp/e"; echo $?; }
calls() { wc -l < "$STUB_CALLS" | tr -d ' '; }
t() { if "$@"; then :; else return 1; fi; }

# 1. A dry run prints the price and sends nothing.
rc=$(stub "$(python3 -c 'print("a"*1000)')" "$tmp/d.mp3" --dry-run)
{ grep -q 'about \$0.1000' "$tmp/o" && [[ $rc == 0 && $(calls) == 0 && ! -e "$tmp/d.mp3" ]]; } \
  && ok dry_run_prices_and_sends_nothing true || ok dry_run_prices_and_sends_nothing false

# 2. CONTROL: over the cap without --yes is refused and makes zero calls.
rc=$(stub "$(python3 -c 'print("a"*12000)')" "$tmp/c.mp3")
{ [[ $rc == 2 && $(calls) == 0 ]] && grep -q 'over the cap' "$tmp/e"; } \
  && ok control_over_cap_refused_zero_calls true || ok control_over_cap_refused_zero_calls false

# 3. CONTROL: a missing voice record is refused with zero calls.
rc=$(stub "hi" "$tmp/m.mp3" --voice-file "$tmp/none.json")
{ [[ $rc == 2 && $(calls) == 0 ]] && grep -q 'no voice record' "$tmp/e"; } \
  && ok control_missing_voice_refused_zero_calls true || ok control_missing_voice_refused_zero_calls false

# 4. CONTROL: empty text, bad extension, NaN cap, bad cap, a missing flag value. All exit 2, zero calls.
bad=0
for args in '"" X.mp3' '"hi" X.txt' '"hi" X.mp3 --cap NaN' '"hi" X.mp3 --cap -1' '"hi" X.mp3 --cap' '"hi" X.mp3 --voice-file'; do
  rc=$(eval "stub $args"); [[ $rc == 2 && $(calls) == 0 ]] || bad=1
done
[[ $bad == 0 ]] && ok control_bad_input_refused_zero_calls true || ok control_bad_input_refused_zero_calls false

# 5. A failing call does not print the key (a stub that echoes it).
rc=$(STUB_LEAK=1 stub "hi" "$tmp/l.mp3")
{ [[ $rc == 1 ]] && ! grep -q 'fake-key-123' "$tmp/o" "$tmp/e" && grep -q 'redacted' "$tmp/e"; } \
  && ok failed_call_redacts_key true || ok failed_call_redacts_key false

# 6. A real call: audible speech of a sane length, and the key it used never appears.
"$here/voice-say" "Hello. This is a short test of my voice." "$tmp/real.mp3" </dev/null >"$tmp/o" 2>"$tmp/e"; rc=$?
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$tmp/real.mp3" 2>/dev/null || echo 0)
mx=$(ffmpeg -hide_banner -i "$tmp/real.mp3" -af volumedetect -f null - 2>&1 </dev/null | sed -n 's/.*max_volume: \(-\{0,1\}[0-9.]*\) dB.*/\1/p')
python3 -I - "$rc" "$dur" "${mx:--99}" <<'PY' && ok real_clip_audible_and_sane_length true || ok real_clip_audible_and_sane_length false
import sys
rc, dur, mx = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
sys.exit(0 if rc == 0 and 1.0 <= dur <= 15 and mx > -30 else 1)
PY
# The key voice-say used: the environment first, else the env file, loaded with the same shell rules.
# It goes to Python in the environment, never on a command line.
SECRETS="${VOICE_SECRETS:-$HOME/Documents/Personal/.secrets}"
used_key="${WAVESPEED_API_KEY:-$( . "$SECRETS/wavespeed.env" 2>/dev/null; printf %s "${WAVESPEED_API_KEY:-}" )}"
USED_KEY="$used_key" python3 -I - "$tmp/o" "$tmp/e" <<'PY' && ok real_call_key_not_printed true || ok real_call_key_not_printed false
import os, sys
key = os.environ.get("USED_KEY", "")
if not key: sys.exit(1)
sys.exit(1 if any(key in open(p).read() for p in sys.argv[1:]) else 0)
PY

python3 -I - "$res" "${1:-}" <<'PY'
import json, sys
checks = dict((a, b == "true") for a, b in (l.rstrip("\n").split("\t") for l in open(sys.argv[1])))
v = {"checks": checks, "pass": all(checks.values()) and len(checks) == 7}
s = json.dumps(v, indent=2)
print(s)
if sys.argv[2]: open(sys.argv[2], "w").write(s + "\n")
sys.exit(0 if v["pass"] else 1)
PY
