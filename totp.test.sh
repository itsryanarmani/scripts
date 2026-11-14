#!/usr/bin/env bash
# Tests for totp. Each row of totp.failure-modes.md marked "yes" has a case
# here. The code checks use the published RFC 6238 test vectors, so a pass
# means the codes match the standard and not just the script's own idea of it.
set -uo pipefail

fail=0
pass=0
ok() { echo "ok - $1"; pass=$((pass+1)); }
bad() { echo "FAIL - $1"; fail=$((fail+1)); }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOTP="$SCRIPT_DIR/totp"
d=$(mktemp -d)
trap 'rm -rf "$d"' EXIT

b32() { python3 -I -c "import base64,sys; print(base64.b32encode(sys.argv[1].encode()).decode().rstrip('='))" "$1"; }
S1=$(b32 "12345678901234567890")
S256=$(b32 "12345678901234567890123456789012")
S512=$(b32 "1234567890123456789012345678901234567890123456789012345678901234")

# run NAME ARGS... : stores stdout+stderr in $out and the exit status in $rc.
run() { out=$("$@" 2>&1); rc=$?; }
expect() { # label want_rc want_text
  if [ "$rc" = "$2" ] && { [ -z "${3:-}" ] || printf '%s' "$out" | grep -qF -- "$3"; }; then ok "$1"; else bad "$1 (rc=$rc out=$out)"; fi
}
save_uri() { printf '%s' "$1" | TOTP_NOW=0 "$TOTP" save "$2" "$3" 2>&1; }

env="$d/accounts.env"

# Row 11: RFC 6238 vectors.
save_uri "otpauth://totp/x?secret=$S1&digits=8" "$env" T1 >/dev/null
for pair in "59 94287082" "1111111109 07081804" "2000000000 69279037"; do
  set -- $pair
  run env TOTP_NOW="$1" "$TOTP" code "$env" T1
  expect "SHA1 at $1" 0 "$2"
done
save_uri "otpauth://totp/x?secret=$S256&digits=8&algorithm=SHA256" "$env" T256 >/dev/null
run env TOTP_NOW=59 "$TOTP" code "$env" T256; expect "SHA256 at 59" 0 "46119246"
save_uri "otpauth://totp/x?secret=$S512&digits=8&algorithm=SHA512" "$env" T512 >/dev/null
run env TOTP_NOW=59 "$TOTP" code "$env" T512; expect "SHA512 at 59" 0 "90693936"

# Six digits and a 30 second period are the defaults.
save_uri "otpauth://totp/x?secret=$S1" "$env" DEF >/dev/null
run env TOTP_NOW=59 "$TOTP" code "$env" DEF; expect "defaults give six digits" 0 "287082"
run env TOTP_NOW=29 "$TOTP" code "$env" DEF; first="$out"
run env TOTP_NOW=30 "$TOTP" code "$env" DEF
[ "$first" != "$out" ] && ok "code changes at the period edge" || bad "code did not change at 30s"

# Rows 1 to 6: refusals.
e2="$d/refuse.env"
run bash -c "printf '%s' 'otpauth://hotp/x?secret=$S1&counter=1' | '$TOTP' save '$e2' R"; expect "row 1 hotp refused" 2
run bash -c "printf '%s' 'https://example.test/x' | '$TOTP' save '$e2' R"; expect "row 1 non-otpauth refused" 2
run bash -c "printf '%s' 'otpauth://totp/x?digits=6' | '$TOTP' save '$e2' R"; expect "row 2 no secret refused" 2
run bash -c "printf '%s' 'otpauth://totp/x?secret=not*base32!' | '$TOTP' save '$e2' R"; expect "row 3 bad base32 refused on save" 2
run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1&algorithm=MD5' | '$TOTP' save '$e2' R"; expect "row 4 unknown algorithm refused" 2
run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1&digits=4' | '$TOTP' save '$e2' R"; expect "row 5 four digits refused" 2
run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1&period=0' | '$TOTP' save '$e2' R"; expect "row 5 zero period refused" 2
run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1' | '$TOTP' save '$e2' 'bad prefix'"; expect "row 6 bad prefix refused on save" 2
run "$TOTP" code "$env" "lower"; expect "row 6 bad prefix refused on code" 2
[ ! -e "$e2" ] && ok "a refused save writes no file" || bad "a refused save wrote a file"

bad32="$d/bad32.env"
printf 'X_TOTP_SECRET=not*base32!\n' > "$bad32"; chmod 600 "$bad32"
run "$TOTP" code "$bad32" X; expect "row 3 bad base32 refused on code" 2

# Row 7: file modes.
mode=$(stat -c '%a' "$env" 2>/dev/null || stat -f '%Lp' "$env")
[ "$mode" = "600" ] && ok "save leaves mode 600" || bad "mode is $mode"
chmod 644 "$env"
run "$TOTP" code "$env" T1; expect "row 7 world-readable file refused" 3 "chmod 600"
chmod 600 "$env"

# Row 8: missing key and missing file.
run "$TOTP" code "$env" NOPE; expect "row 8 missing key named" 4 "NOPE_TOTP_SECRET"
run "$TOTP" code "$d/absent.env" T1; expect "row 8 missing file refused" 4

# Row 9: a second save replaces, keeps other lines and other prefixes.
printf 'UNRELATED=keep-me\n' >> "$env"
save_uri "otpauth://totp/x?secret=$S256&algorithm=SHA256&digits=7" "$env" T1 >/dev/null
[ "$(grep -c '^T1_TOTP_SECRET=' "$env")" = 1 ] && ok "row 9 one secret line after two saves" || bad "duplicate secret lines"
grep -q '^UNRELATED=keep-me$' "$env" && ok "row 9 unrelated line kept" || bad "unrelated line lost"
grep -q "^T256_TOTP_SECRET=$S256\$" "$env" && ok "row 9 other prefix untouched" || bad "other prefix changed"

# Row 10: the secret never reaches output.
leak=0
for s in "$S1" "$S256" "$S512"; do
  for text in "$(save_uri "otpauth://totp/x?secret=$s" "$d/leak.env" L)" \
              "$(TOTP_NOW=59 "$TOTP" code "$d/leak.env" L 2>&1)" \
              "$(printf '%s' "otpauth://totp/x?secret=$s&algorithm=MD5" | "$TOTP" save "$d/leak2.env" L 2>&1)"; do
    printf '%s' "$text" | grep -qF "$s" && leak=1
  done
done
[ "$leak" = 0 ] && ok "row 10 secret absent from all output" || bad "secret appeared in output"
# Positive control: the same search must find a secret that is printed.
printf '%s' "echoed $S1 here" | grep -qF "$S1" && ok "row 10 control: the search finds a printed secret" || bad "leak search cannot see a secret"

echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
