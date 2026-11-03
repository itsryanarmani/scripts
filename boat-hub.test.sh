#!/usr/bin/env bash
# boat-hub warm must show a clone error and prove GitHub login before the wait.
# Offline: stub boat and sleep. No box and no network.
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${BOAT_HUB_UNDER_TEST:-$DIR/boat-hub}"
PASS=0
FAIL=0

pass() { echo "ok - $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL - $1"; echo "  $2"; FAIL=$((FAIL+1)); }

T="$(mktemp -d "${TMPDIR:-/tmp}/boat-hub-test.XXXXXX")"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/stubbin"
export BOAT_HUB_TEST_T="$T"
: >"$T/boat.log"
: >"$T/exec.log"

cat >"$T/stubbin/boat" <<'STUB'
#!/usr/bin/env bash
T="${BOAT_HUB_TEST_T:?}"
printf '%s\n' "$*" >>"$T/boat.log"
sub="${1:-}"
shift || true
case "$sub" in
  new)
    printf '%s\n' '{"event":"ready","id":"box-test"}'
    ;;
  env)
    if [ -f "$T/repos-selected" ]; then
      printf '%s\n' '{"selectedRepositories":["example-repo"]}'
    else
      printf '%s\n' '{}'
    fi
    ;;
  exec)
    cmd=""
    prev=""
    for a in "$@"; do
      if [ "$prev" = "--" ]; then cmd="$a"; fi
      prev="$a"
    done
    printf '%s\n' "$cmd" >>"$T/exec.log"
    if printf '%s' "$cmd" | grep -q "gh auth status"; then
      if [ -f "$T/auth-ok" ]; then
        echo "logged in"
        exit 0
      fi
      echo "You are not logged into any GitHub hosts" >&2
      exit 1
    fi
    if printf '%s' "$cmd" | grep -q "gh repo clone"; then
      if [ -f "$T/clone-json-fail" ]; then
        printf '%s\n' '{"stdout":"","stderr":"fatal: GH_CLONE_TOKEN_REJECTED","exitCode":1}'
        exit 0
      fi
      if [ -f "$T/clone-ok" ]; then
        echo "cloned"
        exit 0
      fi
      echo "fatal: GH_CLONE_TOKEN_REJECTED" >&2
      exit 1
    fi
    if printf '%s' "$cmd" | grep -q "rev-parse"; then
      if [ -f "$T/head-ok" ]; then
        printf '%s\n' '{"stdout":"abc\n","stderr":"","exitCode":0}'
        exit 0
      fi
      printf '%s\n' '{"stdout":"","stderr":"fatal: not a git repository","exitCode":128}'
      exit 0
    fi
    echo "unexpected exec: $cmd" >&2
    exit 97
    ;;
  info)
    printf '%s\n' '{"sandbox":{"hydrated":true,"setupStatus":"done"}}'
    ;;
  snapshot)
    echo "snapshot ok"
    exit 0
    ;;
  delete)
    exit 0
    ;;
  *)
    echo "stub boat: unknown $sub" >&2
    exit 98
    ;;
esac
STUB

cat >"$T/stubbin/sleep" <<'STUB'
#!/usr/bin/env bash
echo "$1" >>"${BOAT_HUB_TEST_T:?}/sleep.log"
exit 0
STUB
chmod +x "$T/stubbin/boat" "$T/stubbin/sleep"
export PATH="$T/stubbin:$PATH"

reset_logs() {
  : >"$T/boat.log"
  : >"$T/exec.log"
  rm -f "$T/sleep.log" "$T/auth-ok" "$T/repos-selected" "$T/clone-ok" "$T/clone-json-fail" "$T/head-ok"
}

warm_clone=$(awk '/^cmd_warm\(\)/{p=1} /^cmd_new\(\)/{p=0} p && /gh repo clone/{print}' "$SCRIPT")
if [ -n "$warm_clone" ] && ! printf '%s\n' "$warm_clone" | grep -q '|| true' && ! printf '%s\n' "$warm_clone" | grep -q '/dev/null'; then
  pass "warm clone keeps its error output"
else
  fail "warm clone keeps its error output" "${warm_clone:-no clone line in cmd_warm}"
fi

reset_logs
bash "$SCRIPT" warm example-repo >"$T/out1" 2>"$T/err1"
rc1=$?
cat "$T/out1" "$T/err1" >"$T/both1"
if [ "$rc1" != 0 ]; then pass "missing login exits non-zero"; else fail "missing login exits non-zero" "rc=$rc1"; fi
if grep -q "not logged in" "$T/both1"; then
  pass "missing login names the check"
else
  fail "missing login names the check" "$(cat "$T/both1")"
fi
if grep -q "gh repo clone" "$T/exec.log"; then
  fail "missing login does not clone" "$(cat "$T/exec.log")"
else
  pass "missing login does not clone"
fi
if [ -f "$T/sleep.log" ]; then
  fail "missing login does not wait" "$(wc -l <"$T/sleep.log" | tr -d ' ') sleeps"
else
  pass "missing login does not wait"
fi

reset_logs
touch "$T/auth-ok"
bash "$SCRIPT" warm example-repo >"$T/out2" 2>"$T/err2"
rc2=$?
cat "$T/out2" "$T/err2" >"$T/both2"
if [ "$rc2" != 0 ]; then pass "clone failure exits non-zero"; else fail "clone failure exits non-zero" "rc=$rc2"; fi
if grep -q "GH_CLONE_TOKEN_REJECTED" "$T/both2"; then
  pass "clone failure prints the error"
else
  fail "clone failure prints the error" "$(cat "$T/both2")"
fi
if [ -f "$T/sleep.log" ]; then
  fail "clone failure does not wait" "$(wc -l <"$T/sleep.log" | tr -d ' ') sleeps"
else
  pass "clone failure does not wait"
fi

reset_logs
touch "$T/auth-ok" "$T/clone-json-fail"
bash "$SCRIPT" warm example-repo >"$T/out4" 2>"$T/err4"
rc4=$?
cat "$T/out4" "$T/err4" >"$T/both4"
if [ "$rc4" != 0 ] && grep -q "GH_CLONE_TOKEN_REJECTED" "$T/both4" && [ ! -f "$T/sleep.log" ]; then
  pass "json clone failure is printed and does not wait"
else
  fail "json clone failure is printed and does not wait" "rc=$rc4 sleep=$( [ -f "$T/sleep.log" ] && echo yes || echo no ) text=$(cat "$T/both4")"
fi

reset_logs
touch "$T/auth-ok" "$T/repos-selected" "$T/head-ok"
bash "$SCRIPT" warm example-repo >"$T/out3" 2>"$T/err3"
rc3=$?
if [ "$rc3" = 0 ] && grep -q "example-repo-ready" "$T/out3"; then
  pass "ready repo finishes"
else
  fail "ready repo finishes" "rc=$rc3 out=$(cat "$T/out3") err=$(cat "$T/err3")"
fi
if grep -q "gh repo clone" "$T/exec.log"; then
  fail "selected repo is not cloned again" "$(cat "$T/exec.log")"
else
  pass "selected repo is not cloned again"
fi
auth_line=$(grep -n "gh auth status" "$T/exec.log" | head -1 | cut -d: -f1)
parse_line=$(grep -n "rev-parse" "$T/exec.log" | head -1 | cut -d: -f1)
if [ -n "$auth_line" ] && [ -n "$parse_line" ] && [ "$auth_line" -lt "$parse_line" ]; then
  pass "login check runs before the clone wait"
else
  fail "login check runs before the clone wait" "auth=$auth_line parse=$parse_line log=$(cat "$T/exec.log")"
fi

echo "pass=$PASS fail=$FAIL"
[ "$FAIL" = "0" ]
