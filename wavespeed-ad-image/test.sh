#!/usr/bin/env bash
# wavespeed-ad-image tests — no network, no API key, never touch secret files.
set -euo pipefail
PASS=0; FAIL=0
ok(){ echo "  ok   $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL $1"; FAIL=$((FAIL+1)); }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
HERE="$(cd "$(dirname "$0")" && pwd)"
HELP="$HERE/wavespeed-ad-image.sh"
run(){ env -u WAVESPEED_API_KEY bash "$HELP" "$@" 2>&1; }

echo "=== list and model pick ==="
out="$(run --list-models)"
echo "$out" | grep -q $'lo-fi\tbytedance/seedream-v5.5' && ok "lo-fi maps to seedream" || no "lo-fi maps to seedream"
echo "$out" | grep -q $'stickman\trecraft-ai/recraft-v4.1-flash' && ok "stickman maps to recraft" || no "stickman maps to recraft"
echo "$out" | grep -q $'notes\thtml' && ok "notes is html" || no "notes is html"
out="$(run --dry-run --format lo-fi --model wavespeed-ai/z-image/turbo --prompt "selfie" --output "$TMP/x.png")"
echo "$out" | grep -q "z-image/turbo" && ok "--model overrides --format" || no "--model overrides --format"

echo "=== dry-run and missing key ==="
out="$(run --dry-run --format lo-fi --prompt "a candid kitchen still" --output "$TMP/dry.png" --aspect 4:5)"
echo "$out" | grep -q "no API calls" && [ ! -f "$TMP/dry.png" ] && ok "dry-run skips API and output" || no "dry-run skips API and output"
set +e
out="$(run --format lo-fi --prompt "x" --output "$TMP/live.png" --aspect 4:5 2>&1)"
rc=$?
set -e
[ "$rc" -ne 0 ] && echo "$out" | grep -q "WAVESPEED_API_KEY is not set" && ok "live generate refuses without key" || no "live generate refuses without key"
echo "$out" | grep -q "/home/" && no "refusal mentions a home path" || ok "refusal mentions no home path"
echo "$out" | grep -qiE 'sk-[a-zA-Z0-9]' && no "refusal prints a key" || ok "refusal prints no key"

echo "=== html formats ==="
set +e
out="$(run --format notes --prompt "x" --output "$TMP/n.png" 2>&1)"
rc=$?
set -e
[ "$rc" -ne 0 ] && echo "$out" | grep -q "templates.mjs" && ok "notes points at the HTML renderer" || no "notes points at the HTML renderer"

echo "=== templates ==="
html="$(node "$HERE/templates.mjs" notes --aspect 4:5)"
echo "$html" | grep -q "<!doctype html>" && echo "$html" | grep -q "Notes" && echo "$html" | grep -q "Things nobody told me" && ok "notes template" || no "notes template"
html="$(node "$HERE/templates.mjs" imessage --aspect 9:16)"
echo "$html" | grep -q "iMessage" && echo "$html" | grep -q "0b84ff" && echo "$html" | grep -q "a friend" && ok "imessage template" || no "imessage template"
html="$(node "$HERE/templates.mjs" blurred-pdf --aspect 4:5)"
echo "$html" | grep -q "blur(8px)" && echo "$html" | grep -q "field guide" && ok "blurred-pdf template" || no "blurred-pdf template"
html="$(node --input-type=module -e "import { notesTemplate } from 'file://${HERE}/templates.mjs'; process.stdout.write(notesTemplate({headline:'A <script>alert(1)</script>'}))")"
echo "$html" | grep -q "&lt;script&gt;" && ! echo "$html" | grep -q "<script>" && ok "notes escapes markup" || no "notes escapes markup"

echo "=== renderer dry-run ==="
node "$HERE/templates.mjs" notes --aspect 4:5 > "$TMP/notes.html"
node "$HERE/renderer.mjs" --file "$TMP/notes.html" --out "$TMP/notes.png" --aspect 4:5 --dry-run >/dev/null
[ -f "$TMP/notes.html" ] && ok "renderer dry-run writes html" || no "renderer dry-run writes html"

echo "=== degrade-only ==="
ffmpeg -y -f lavfi -i color=c=salmon:s=1080x1350 -frames:v 1 "$TMP/src.png" >/dev/null 2>&1
run --degrade-only --input "$TMP/src.png" --output "$TMP/out.png" --aspect 4:5 >/dev/null
[ -f "$TMP/out.png" ] && ! cmp -s "$TMP/src.png" "$TMP/out.png" && ok "degrade writes a different png" || no "degrade writes a different png"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "wavespeed-ad-image: all tests passed"
exit "$FAIL"
