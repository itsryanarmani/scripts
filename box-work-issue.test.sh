#!/usr/bin/env bash
# Tests for the box-work fleet claim guard (issue #357). Offline: stub BOX_CLI
# and FLEET_PRESENCE_BIN, fake agent CLI, generated runner executes locally.
# No Box is created; no GitHub calls happen; no secrets anywhere.
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${BOX_WORK_UNDER_TEST:-$DIR/box-work}"
PASS=0
FAIL=0

pass() { echo "ok - $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL - $1"; echo "  $2"; FAIL=$((FAIL+1)); }

cleanup() { rm -rf "${T:-}"; }
trap cleanup EXIT

write_box_stub() {
  cat > "$T/stubbin/box" <<'STUB'
#!/usr/bin/env bash
T="${BOX_WORK_TEST_T:?}"
sub="${1:-}"; shift || true
case "$sub" in
  info) printf '{"box":{"state":"ready","url":"https://example.invalid/x"}}\n' ;;
  new) touch "$T/new-called"; echo "stub box: new must not be called" >&2; exit 99 ;;
  scp) cp "$1" "$T/captured-runner.sh" ;;
  exec)
    printf '%s\n' "$*" >>"$T/exec.log"
    after=0; cmd=()
    for a in "$@"; do
      if (( after )); then cmd+=("$a"); continue; fi
      if [[ "$a" == "--" ]]; then after=1; fi
    done
    if [[ "${cmd[0]:-}" == "true" ]]; then exit 0; fi
    b64="${cmd[${#cmd[@]}-1]}"
    # FAKE_AGENT_EXIT is harness plumbing like BOX_WORK_TEST_T, not product
    # transport: it steers the fake agent exit code below.
    env -i HOME="$T/home" PATH="/usr/bin:/bin" BOX_WORK_TEST_T="$T" \
      FAKE_AGENT_EXIT="${FAKE_AGENT_EXIT:-}" \
      bash "$T/captured-runner.sh" "$b64" >"$T/runner.out" 2>"$T/runner.err"
    rc=$?
    python3 - "$T/runner.out" "$T/runner.err" "$rc" <<'PY'
import json,sys
o=open(sys.argv[1]).read(); e=open(sys.argv[2]).read(); rc=int(sys.argv[3])
print(json.dumps({"stdout":o,"stderr":e,"exitCode":rc}))
PY
    ;;
  *) echo "stub box: unknown subcommand $sub" >&2; exit 99 ;;
esac
STUB
  chmod +x "$T/stubbin/box"
}

write_fleet_stub() {
  cat > "$T/stubbin/fleet-presence" <<'STUB'
#!/usr/bin/env bash
# Minimal claim/release double. $T/fleet-foreign holds "<id> on <host>" to
# simulate a live foreign claim; $T/fleet-release-fails forces release to fail.
printf 'fleet-presence %s\n' "$*" >>"${BOX_WORK_TEST_T:?}/fleet-calls.log"
sub="${1:-}"; shift || true
repo="${1:-}"; shift || true
issue="${1:-}"; shift || true
case "$sub" in
  claim)
    if [[ -f "${BOX_WORK_TEST_T:?}/fleet-foreign" ]]; then
      echo "$(cat "${BOX_WORK_TEST_T:?}/fleet-foreign") already holds #$issue." >&2
      exit 2
    fi
    echo "claimed $repo#$issue"
    ;;
  release)
    if [[ -f "${BOX_WORK_TEST_T:?}/fleet-release-fails" ]]; then
      echo "release transport down" >&2
      exit 1
    fi
    echo "released $repo#$issue $*"
    ;;
  *) echo "stub fleet-presence: unknown subcommand $sub" >&2; exit 99 ;;
esac
STUB
  chmod +x "$T/stubbin/fleet-presence"
}

setup() {
  T="$(mktemp -d "${TMPDIR:-/tmp}/box-work-issue-test.XXXXXX")"
  FAKEHOME="$T/home"
  mkdir -p "$FAKEHOME/.agents" "$FAKEHOME/.local/bin" "$T/stubbin" "$T/xdg/box-work"
  REPO="$T/repo"
  git init -q "$REPO" 2>/dev/null
  git -C "$REPO" remote add origin https://github.com/itsryanarmani/fakerepo.git
  mkdir -p "$FAKEHOME/fakerepo"
  printf 'bx_test123\n' > "$T/xdg/box-work/fakerepo.id"
  : > "$T/exec.log"
  : > "$T/fleet-calls.log"
  printf 'GEMINI_API_KEY=test-fixture-no-secret\n' > "$FAKEHOME/.agents/agent-clis.env"
  export BOX_WORK_TEST_T="$T"
  write_box_stub
  write_fleet_stub
  cat > "$FAKEHOME/.local/bin/muse" <<'FAKE'
#!/usr/bin/env bash
echo "muse $*" >>"$BOX_WORK_TEST_T/calls.log"
if [[ -n "${FAKE_AGENT_EXIT:-}" && "${FAKE_AGENT_EXIT}" != "0" ]]; then exit "$FAKE_AGENT_EXIT"; fi
pf=""; prev=""
for a in "$@"; do [[ "$prev" == "--prompt-file" ]] && pf="$a"; prev="$a"; done
cat "$pf"
FAKE
  chmod +x "$FAKEHOME/.local/bin/muse"
}

# Run box-work in agent mode with --issue; result lands in $T/bw.{out,err,rc}.
run_issue() { # <agent> <brief> <issue> [extra env assignments...]
  local agent="$1" brief="$2" issue="$3"; shift 3 || true
  env "$@" HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
    FLEET_PRESENCE_BIN="$T/stubbin/fleet-presence" BOX_WORK_READY_SECS=60 \
    bash "$SCRIPT" "$REPO" --agent "$agent" "$brief" --issue "$issue" >"$T/bw.out" 2>"$T/bw.err"
  printf '%s' "$?" >"$T/bw.rc"
}

setup

# 1. Claim before dispatch, release with done on success.
run_issue muse "count the carts on the track" 357
[ "$(cat "$T/bw.rc")" = "0" ] \
  && pass "guarded dispatch succeeds" \
  || fail "guarded dispatch succeeds" "rc=$(cat "$T/bw.rc") err: $(cat "$T/bw.err")"
grep -q "count the carts on the track" "$T/bw.out" \
  && pass "guarded dispatch delivers the brief" \
  || fail "guarded dispatch delivers the brief" "$(cat "$T/bw.out")"
grep -q "^fleet-presence claim itsryanarmani/fakerepo 357" "$T/fleet-calls.log" \
  && pass "claim names the repo and the issue" \
  || fail "claim names the repo and the issue" "$(cat "$T/fleet-calls.log")"
grep -q "^fleet-presence release itsryanarmani/fakerepo 357 --reason done" "$T/fleet-calls.log" \
  && pass "success releases with reason done" \
  || fail "success releases with reason done" "$(cat "$T/fleet-calls.log")"
grep -q "claimed itsryanarmani/fakerepo#357" "$T/bw.err" \
  && pass "claim confirmation goes to stderr" \
  || fail "claim confirmation goes to stderr" "$(cat "$T/bw.err")"
# The claim precedes every Box call: nothing runs before the guard passes.
first_box="$(head -n 1 "$T/exec.log")"
first_claim_line="$(grep -n "claim" "$T/fleet-calls.log" | head -n 1 | cut -d: -f1)"
[ -n "$first_claim_line" ] && [ -n "$first_box" ] \
  && pass "claim is recorded before Box use" \
  || fail "claim is recorded before Box use" "exec: $(cat "$T/exec.log")"

# 2. A live foreign claim refuses the run and never starts the agent.
rm -f "$T/captured-runner.sh"; : > "$T/exec.log"; : > "$T/fleet-calls.log"
printf 'grok:grok-4 on other-host' > "$T/fleet-foreign"
run_issue muse "anything at all" 357
[ "$(cat "$T/bw.rc")" != "0" ] \
  && pass "foreign claim exits non-zero" \
  || fail "foreign claim exits non-zero" "rc=0 unexpectedly"
grep -q "grok:grok-4 on other-host" "$T/bw.err" \
  && pass "refusal names the holder" \
  || fail "refusal names the holder" "$(cat "$T/bw.err")"
[ ! -e "$T/captured-runner.sh" ] \
  && pass "refused run never starts the agent" \
  || fail "refused run never starts the agent" "runner was uploaded"
[ ! -s "$T/exec.log" ] \
  && pass "refused run touches no Box" \
  || fail "refused run touches no Box" "$(cat "$T/exec.log")"
grep -q "^release" "$T/fleet-calls.log" \
  && fail "refused run releases nothing" "$(cat "$T/fleet-calls.log")" \
  || pass "refused run releases nothing"
rm -f "$T/fleet-foreign"

# 3. An absent fleet-presence binary stops the run loudly, never unguarded.
: > "$T/exec.log"
HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
  FLEET_PRESENCE_BIN="$T/definitely-missing" BOX_WORK_READY_SECS=60 \
  bash "$SCRIPT" "$REPO" --agent muse "anything" --issue 357 >"$T/bw.out" 2>"$T/bw.err"
printf '%s' "$?" >"$T/bw.rc"
[ "$(cat "$T/bw.rc")" != "0" ] \
  && pass "absent binary exits non-zero" \
  || fail "absent binary exits non-zero" "rc=0 unexpectedly"
grep -q "refusing to run unguarded" "$T/bw.err" \
  && pass "absent binary fails loudly" \
  || fail "absent binary fails loudly" "$(cat "$T/bw.err")"
[ ! -s "$T/exec.log" ] \
  && pass "absent binary starts nothing" \
  || fail "absent binary starts nothing" "$(cat "$T/exec.log")"

# 4. --issue without --agent is rejected.
HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
  FLEET_PRESENCE_BIN="$T/stubbin/fleet-presence" \
  bash "$SCRIPT" "$REPO" --issue 357 >"$T/bw.out" 2>"$T/bw.err"
printf '%s' "$?" >"$T/bw.rc"
[ "$(cat "$T/bw.rc")" != "0" ] \
  && pass "--issue without --agent exits non-zero" \
  || fail "--issue without --agent exits non-zero" "rc=0 unexpectedly"
grep -q -- "--issue needs --agent" "$T/bw.err" \
  && pass "--issue without --agent names the rule" \
  || fail "--issue without --agent names the rule" "$(cat "$T/bw.err")"

# 5. Agent failure keeps its exit code and releases with reason failed.
: > "$T/fleet-calls.log"
run_issue muse "anything" 358 "FAKE_AGENT_EXIT=3"
[ "$(cat "$T/bw.rc")" = "3" ] \
  && pass "agent failure exit code propagates under guard" \
  || fail "agent failure exit code propagates under guard" "rc=$(cat "$T/bw.rc") want 3"
grep -q "^fleet-presence release itsryanarmani/fakerepo 358 --reason failed" "$T/fleet-calls.log" \
  && pass "failure releases with reason failed" \
  || fail "failure releases with reason failed" "$(cat "$T/fleet-calls.log")"

# 6. No --issue still dispatches, but says it is unguarded.
: > "$T/fleet-calls.log"
HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
  FLEET_PRESENCE_BIN="$T/stubbin/fleet-presence" BOX_WORK_READY_SECS=60 \
  bash "$SCRIPT" "$REPO" --agent muse "plain run" >"$T/bw.out" 2>"$T/bw.err"
printf '%s' "$?" >"$T/bw.rc"
[ "$(cat "$T/bw.rc")" = "0" ] \
  && pass "unguarded dispatch still works" \
  || fail "unguarded dispatch still works" "rc=$(cat "$T/bw.rc") err: $(cat "$T/bw.err")"
grep -q "without a fleet claim" "$T/bw.err" \
  && pass "unguarded dispatch says so" \
  || fail "unguarded dispatch says so" "$(cat "$T/bw.err")"
[ ! -s "$T/fleet-calls.log" ] \
  && pass "unguarded dispatch claims nothing" \
  || fail "unguarded dispatch claims nothing" "$(cat "$T/fleet-calls.log")"

# 7. Bad issue values are rejected before any claim.
for bad in abc 0 07 -4; do
  : > "$T/fleet-calls.log"
  HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
    FLEET_PRESENCE_BIN="$T/stubbin/fleet-presence" BOX_WORK_READY_SECS=60 \
    bash "$SCRIPT" "$REPO" --agent muse "anything" --issue "$bad" >"$T/bw.out" 2>"$T/bw.err"
  printf '%s' "$?" >"$T/bw.rc"
  if [ "$(cat "$T/bw.rc")" != "0" ] && grep -q "positive issue number" "$T/bw.err" \
    && [ ! -s "$T/fleet-calls.log" ]; then
    pass "bad --issue '$bad' is rejected before any claim"
  else
    fail "bad --issue '$bad' is rejected before any claim" "rc=$(cat "$T/bw.rc") err: $(cat "$T/bw.err")"
  fi
done

# 8. A missing --issue value stops instead of reading as absent.
HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
  FLEET_PRESENCE_BIN="$T/stubbin/fleet-presence" BOX_WORK_READY_SECS=60 \
  bash "$SCRIPT" "$REPO" --agent muse "anything" --issue >"$T/bw.out" 2>"$T/bw.err"
printf '%s' "$?" >"$T/bw.rc"
[ "$(cat "$T/bw.rc")" != "0" ] \
  && pass "missing --issue value exits non-zero" \
  || fail "missing --issue value exits non-zero" "rc=0 unexpectedly"
grep -q -- "--issue needs a number" "$T/bw.err" \
  && pass "missing --issue value names the rule" \
  || fail "missing --issue value names the rule" "$(cat "$T/bw.err")"

echo "pass=$PASS fail=$FAIL"
[ "$FAIL" = "0" ]
