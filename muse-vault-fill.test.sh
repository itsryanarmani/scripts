#!/bin/bash
# muse-vault-fill never touches a live Muse app in CI. These tests pin the
# parts that don't need one: it compiles, --help works, a missing entries
# file fails loudly, and the state machine drives correctly — a stub
# `peekaboo` on PATH serves canned snapshots (list / dialog / detail /
# list-with-row) so the skip path and the full add path both get exercised.
set -uo pipefail

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

fails=0
check() { # $1 desc  $2 condition-result
  if [ "$2" -eq 0 ]; then echo "ok - $1"; else echo "FAIL - $1"; fails=$((fails+1)); fi
}

# 1. compiles
python3 -m py_compile "$SCRIPT_DIR/muse-vault-fill"
check "script compiles" $?

# 2. --help prints usage without touching the app
out=$(python3 "$SCRIPT_DIR/muse-vault-fill" --help 2>&1)
echo "$out" | grep -q 'entries'
check "--help documents the entries argument" $?

# 3. a missing entries file fails loudly, not silently
python3 "$SCRIPT_DIR/muse-vault-fill" "$TMP/does-not-exist.json" >/dev/null 2>&1
[ $? -ne 0 ]
check "missing entries.json exits non-zero" $?

# --- stub peekaboo -------------------------------------------------------
# Each `see` call returns the snapshot named by line N of $STUB_DIR/order
# (last line repeats). click/paste/hotkey are no-ops.
mkdir "$TMP/stub"
cat > "$TMP/stub/peekaboo" <<'S'
#!/bin/bash
d="$STUB_DIR"
# `list windows` resolves the Settings window id
if [ "$1" = "list" ]; then
  printf '{"data":{"windows":[{"title":"Settings","window_id":42},{"title":"Muse","window_id":41}]}}'
  exit 0
fi
# only `see` consumes a fixture slot; click/paste/hotkey are silent no-ops
[ "$1" != "see" ] && exit 0
c="$d/count"; n=$(cat "$c" 2>/dev/null || echo 0); echo $((n+1)) > "$c"
src=$(sed -n "$((n+1))p" "$d/order"); [ -z "$src" ] && src=$(tail -1 "$d/order")
printf '{"data":{"snapshot_id":"stub","ui_map":"%s/%s.uimap.json","ui_elements":[]}}' "$d" "$src"
exit 0
S
chmod +x "$TMP/stub/peekaboo"
# stub osascript too — activate_app would otherwise launch the real Muse
cat > "$TMP/stub/osascript" <<'S'
#!/bin/bash
exit 0
S
chmod +x "$TMP/stub/osascript"

uimap() { # $1 file  $2 json-body
  cat > "$TMP/stub/$1.uimap.json" <<J
{"uiMap": $2, "windowBounds": [[421,198],[800,600]]}
J
}

# menu noise the real uimap always carries — a menu-bar AXMenu 'Edit' at y=0
# and zero-size AXMenuItem 'Delete' at the screen bottom. Without window-
# bounds filtering these read as a detail view that is not there.
MENU_NOISE='"me":{"id":"me","role":"AXMenu","label":"Edit","title":"Edit","frame":[[99,0],[44,29]],"isActionable":false},"md":{"id":"md","role":"AXUnknown","label":"Delete","title":"Delete","frame":[[0,967],[0,0]],"isActionable":false}'

# fixture: Secure store list, one example.com row
uimap list_with_row "{\"r\":{\"id\":\"r\",\"role\":\"AXButton\",\"label\":\"Add\",\"title\":\"Add\",\"frame\":[[1147,258],[51,32]],\"isActionable\":true},\"row\":{\"id\":\"row\",\"role\":\"AXButton\",\"label\":\"example.com\",\"title\":\"example.com\",\"frame\":[[676,346],[515,44]],\"isActionable\":true},$MENU_NOISE}"
# fixture: empty list
uimap list_empty "{\"r\":{\"id\":\"r\",\"role\":\"AXButton\",\"label\":\"Add\",\"title\":\"Add\",\"frame\":[[1147,258],[51,32]],\"isActionable\":true},$MENU_NOISE}"
# fixture: detail view of example.com row, username testuser@example.com
uimap detail '{"b":{"id":"b","role":"AXButton","label":"Go back","title":"Go back","frame":[[662,214],[28,28]],"isActionable":true},"e":{"id":"e","role":"AXButton","label":"Edit","title":"Edit","frame":[[1129,272],[50,32]],"isActionable":true},"d":{"id":"d","role":"AXButton","label":"Delete","title":"Delete","frame":[[676,637],[515,44]],"isActionable":true},"u":{"id":"u","role":"AXUnknown","label":"testuser@example.com","title":"testuser@example.com","frame":[[700,385],[200,17]],"isActionable":false}}'
# fixture: Add dialog with three fields
uimap dialog '{"fu":{"id":"fu","role":"AXTextField","label":"URL","title":"URL","frame":[[923,272],[256,36]],"isActionable":true},"fn":{"id":"fn","role":"AXTextField","label":"Username","title":"Username","frame":[[923,325],[256,36]],"isActionable":true},"fp":{"id":"fp","role":"AXTextField","label":"Password","title":"Password","frame":[[923,378],[256,36]],"isActionable":true},"c":{"id":"c","role":"AXButton","label":"Cancel","title":"Cancel","frame":[[1061,440],[74,36]],"isActionable":true},"a":{"id":"a","role":"AXButton","label":"Add","title":"Add","frame":[[1142,440],[56,36]],"isActionable":true}}'

# 4. skip path: store already holds example.com + testuser@example.com
#    see#1 = ensure_list, see#2 = loop re-check, see#3 = row detail view
printf 'list_with_row\nlist_with_row\ndetail\nlist_with_row\n' > "$TMP/stub/order"
cat > "$TMP/entries.json" <<'J'
[{"name":"Example","url":"https://example.com/","username":"testuser@example.com","password":"p"}]
J
out=$(STUB_DIR="$TMP/stub" PATH="$TMP/stub:$PATH" python3 "$SCRIPT_DIR/muse-vault-fill" "$TMP/entries.json" --settle 0 2>&1)
echo "$out" | grep -q 'DONE ok=0 fail=0 skip=1'
check "entry already in store is skipped, not refilled" $?

# 5. add path: empty list -> Add -> dialog -> list shows the new row
printf 'list_empty\nlist_empty\ndialog\nlist_with_row\n' > "$TMP/stub/order"
rm -f "$TMP/stub/count"
out=$(STUB_DIR="$TMP/stub" PATH="$TMP/stub:$PATH" python3 "$SCRIPT_DIR/muse-vault-fill" "$TMP/entries.json" --settle 0 2>&1)
echo "$out" | grep -q 'DONE ok=1 fail=0 skip=0'
check "entry is added when the list lacks its domain" $?

echo; [ $fails -eq 0 ] && echo "all tests passed" || { echo "$fails failed"; exit 1; }
