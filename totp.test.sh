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

if git -C "$d" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "FAIL - TMPDIR is inside a git work tree, so every save is refused; set TMPDIR outside it"; exit 1
fi
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

# Row 13: a non-ASCII digit is a refusal, not a crash.
run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1&digits=%C2%B2' | '$TOTP' save '$d/u.env' U"; expect "row 13 unicode digits refused" 2
run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1&period=%C2%B2' | '$TOTP' save '$d/u.env' U"; expect "row 13 unicode period refused" 2

# Row 14: parallel saves for different prefixes all survive.
par="$d/par.env"
for i in $(seq 1 30); do
  ( printf '%s' "otpauth://totp/x?secret=$S1" | "$TOTP" save "$par" "P$i" >/dev/null 2>&1 ) &
done
wait
[ "$(grep -c '_TOTP_SECRET=' "$par")" = 30 ] && ok "row 14 thirty parallel saves keep thirty secrets" || bad "parallel saves lost keys: $(grep -c '_TOTP_SECRET=' "$par") of 30"

# Row 15: a symlinked env file stays a link.
mkdir -p "$d/real"; : > "$d/real/target.env"; chmod 600 "$d/real/target.env"
ln -s "$d/real/target.env" "$d/link.env"
save_uri "otpauth://totp/x?secret=$S1" "$d/link.env" L1 >/dev/null
[ -L "$d/link.env" ] && ok "row 15 symlink is still a symlink" || bad "symlink was replaced by a file"
grep -q '^L1_TOTP_SECRET=' "$d/real/target.env" && ok "row 15 target holds the new keys" || bad "target did not get the keys"

# Row 16: an unwritable directory is a refusal and leaves nothing behind.
if [ "$(id -u)" != 0 ]; then
  mkdir -p "$d/ro"; chmod 500 "$d/ro"
  run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1' | '$TOTP' save '$d/ro/x.env' W"; expect "row 16 unwritable directory refused" 5
  chmod 700 "$d/ro"
  [ -z "$(ls -A "$d/ro")" ] && ok "row 16 no temp file left behind" || bad "left behind: $(ls -A "$d/ro")"
fi

# Row 17: save fixes a loose mode on an existing file.
printf 'KEEP=1\n' > "$d/loose.env"; chmod 644 "$d/loose.env"
save_uri "otpauth://totp/x?secret=$S1" "$d/loose.env" M >/dev/null
mode=$(stat -c '%a' "$d/loose.env" 2>/dev/null || stat -f '%Lp' "$d/loose.env")
[ "$mode" = "600" ] && ok "row 17 loose mode becomes 600" || bad "mode is $mode"

# Row 18: no secret file inside a git work tree.
mkdir -p "$d/repo/sub"; git init -q "$d/repo"
run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1' | '$TOTP' save '$d/repo/a.env' G"; expect "row 18 save refused in a repo" 6
run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1' | '$TOTP' save '$d/repo/sub/a.env' G"; expect "row 18 save refused in a repo subfolder" 6
run bash -c "printf '%s' 'recovery-value' | '$TOTP' put '$d/repo/a.env' REC_CODE"; expect "row 18 put refused in a repo" 6
[ ! -e "$d/repo/a.env" ] && ok "row 18 nothing written in the repo" || bad "a file was written in the repo"

# Row 19: put stores one value without echoing it.
pe="$d/put.env"; secret_val="R3COVERY-c0de-9f2a"
run bash -c "printf '%s\n' '$secret_val' | '$TOTP' put '$pe' REC_CODE"; expect "row 19 put stores a value" 0
grep -qxF "REC_CODE=$secret_val" "$pe" && ok "row 19 value stored on one line" || bad "value not stored"
printf '%s' "$out" | grep -qF "$secret_val" && bad "put echoed the value" || ok "row 19 put does not echo the value"
bash -c "printf '%s' 'second' | '$TOTP' put '$pe' REC_CODE" >/dev/null 2>&1
[ "$(grep -c '^REC_CODE=' "$pe")" = 1 ] && grep -qx 'REC_CODE=second' "$pe" && ok "row 19 second put replaces" || bad "put did not replace"
run bash -c "printf '%s' 'v' | '$TOTP' put '$pe' lower_key"; expect "row 19 bad key refused" 2
run bash -c "printf '' | '$TOTP' put '$pe' REC_CODE"; expect "row 19 empty value refused" 2
run bash -c "printf 'line1\nline2\n' | '$TOTP' put '$pe' REC_CODE"; expect "row 19 two-line value refused" 2
mode=$(stat -c '%a' "$pe" 2>/dev/null || stat -f '%Lp' "$pe")
[ "$mode" = "600" ] && ok "row 19 put leaves mode 600" || bad "put mode is $mode"
run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1&digits=8' | '$TOTP' save '$pe' PE"; run env TOTP_NOW=59 "$TOTP" code "$pe" PE
expect "row 19 put keeps the other keys working" 0 "94287082"

# Row 20: other read failures are a refusal with no traceback.
nu="$d/nonutf8.env"; printf 'A_TOTP_SECRET=\xff\xfe\n' > "$nu"; chmod 600 "$nu"
run "$TOTP" code "$nu" A; expect "row 20 non-UTF-8 file refused" 5
printf '%s' "$out" | grep -q "Traceback" && bad "row 20 printed a traceback" || ok "row 20 no traceback"
mkdir -p "$d/adir"; chmod 700 "$d/adir"
run "$TOTP" code "$d/adir" A; expect "row 20 a directory refused" 5
if [ "$(id -u)" != 0 ]; then
  printf 'A_TOTP_SECRET=%s\n' "$S1" > "$d/unread.env"; chmod 000 "$d/unread.env"
  run "$TOTP" code "$d/unread.env" A; expect "row 20 unreadable file refused" 5
  chmod 600 "$d/unread.env"
else
  echo "skip - rows 16 and 20 permission cases need a non-root user"
fi

# Row 1: a URI that cannot be parsed is a refusal, not a traceback.
run bash -c "printf '%s' 'otpauth://[totp/x?secret=$S1' | '$TOTP' save '$d/bad.env' B"; expect "row 1 unparsable URI refused" 2
printf '%s' "$out" | grep -q Traceback && bad "row 1 printed a traceback" || ok "row 1 no traceback"

# Row 19: control and line-separator characters in a put value are refused.
for name in "form feed:\\f" "unit separator:\\x1f" "next line:\\xc2\\x85" "line separator U+2028:\\xe2\\x80\\xa8" "tab:\\t"; do
  run bash -c "printf 'AB${name#*:}CD' | '$TOTP' put '$d/ctl.env' CTL"; expect "row 19 refuses $name" 2
done
run bash -c "printf 'x' | '$TOTP' put '$d/ctl.env' 1START"; expect "row 19 key may not start with a digit" 2

# Row 22: an existing line with a separator character survives a later write.
printf 'ODD=AB\xe2\x80\xa8CD\nFF=1\x0c2\n' > "$d/odd.env"; chmod 600 "$d/odd.env"
bash -c "printf 'v' | '$TOTP' put '$d/odd.env' NEXT" >/dev/null 2>&1
[ "$(grep -c '' "$d/odd.env")" = 3 ] && grep -q "^ODD=AB.*CD$" "$d/odd.env" && grep -qE "^FF=1.2$" "$d/odd.env" && ok "row 22 odd lines stay whole" || bad "row 22 odd lines were split: $(cat -v "$d/odd.env" | tr '\n' '|')"

# Row 18: also through a symlink into a repo, and with a .git file.
ln -s "$d/repo/sub" "$d/linkdir"
run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1' | '$TOTP' save '$d/linkdir/s.env' G"; expect "row 18 symlinked folder into a repo refused" 6
mkdir -p "$d/wt"; printf 'gitdir: /nonexistent\n' > "$d/wt/.git"
run bash -c "printf '%s' 'otpauth://totp/x?secret=$S1' | '$TOTP' save '$d/wt/s.env' G"; expect "row 18 a .git file counts as a work tree" 6

# Row 14: parallel puts keep every key too.
pp="$d/pp.env"
for i in $(seq 1 30); do ( printf 'v%s' "$i" | "$TOTP" put "$pp" "K$i" >/dev/null 2>&1 ) & done
wait
[ "$(grep -c '^K[0-9]*=' "$pp")" = 30 ] && ok "row 14 thirty parallel puts keep thirty keys" || bad "parallel puts lost keys: $(grep -c '^K[0-9]*=' "$pp") of 30"

echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
