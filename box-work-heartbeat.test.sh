#!/usr/bin/env bash
# Lifecycle tests for the box-work job-scoped heartbeat (issue 305).
# Offline: stub `box`, throwaway HOME/repo, bounded fake agents, no Boxes.
# Contract: a waiting worker gets periodic heartbeats; normal exit, failure,
# interruption and termination stop the helper with no orphans and preserve
# the worker status; the heartbeat then goes stale; the recorded Box id and
# the repository cwd stay intact.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${BOX_WORK_UNDER_TEST:-$DIR/box-work}"
PASS=0
FAIL=0
pass() { echo "ok - $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL - $1"; echo "  $2"; FAIL=$((FAIL+1)); }

T=""
REPONAME=""
SENTINEL_PID=""
cleanup() {
  if [[ -n "$SENTINEL_PID" ]]; then kill "$SENTINEL_PID" 2>/dev/null || true; fi
  if [[ -n "$T" && -d "$T" ]]; then
    # Scoped to this run's fixture path: a global marker pkill could kill an
    # unrelated launcher heartbeat job that happens to carry the same marker.
    while read -r pid; do kill "$pid" 2>/dev/null || true; done \
      < <(pgrep -f "box-work-heartbeat-loop.*$T" 2>/dev/null)
    pkill -f "$T/captured-runner.sh" 2>/dev/null || true
    rm -rf "$T"
  fi
}
trap cleanup EXIT

mtime() { python3 -c 'import os,sys; print(int(os.stat(sys.argv[1]).st_mtime))' "$1"; }
# Marker plus fixture path in argv: matches only helpers this run started.
runner_live() { pgrep -f "box-work-heartbeat-loop.*$T" >/dev/null 2>&1; }
assert_no_helper() { runner_live && fail "$1" "scoped helper still alive" || pass "$1"; }
assert_stale() { # <file> <label>: mtime must not advance over ~2.5s
  local f="$1" lbl="$2" a b; a="$(mtime "$f")"; sleep 2.5; b="$(mtime "$f")"
  [ "$b" = "$a" ] && pass "$lbl" || fail "$lbl" "mtime $a -> $b"
}
fmtime() { python3 -c 'import os,sys; print(os.stat(sys.argv[1]).st_mtime)' "$1"; }
expect_rc() { [ "$1" = "$2" ] && pass "$3" || fail "$3" "rc=$1 want $2: $(cat "$4")"; }
expect_grep() { grep -q "$1" "$2" && pass "$3" || fail "$3" "$(cat "$4")"; }
expect_grepE() { grep -qE "$1" "$2" && pass "$3" || fail "$3" "$(cat "$4")"; }
expect_grepF() { grep -qF "$1" "$2" && pass "$3" || fail "$3" "$(cat "$4")"; }
expect_absent() { ! grep -qF "$1" "$2" && pass "$3" || fail "$3" "$1 still present"; }
assert_sentinel() { kill -0 "$SENTINEL_PID" 2>/dev/null && pass "$1" || fail "$1" "sentinel $SENTINEL_PID dead"; }
# Print every descendant PID of $1, one per line.
descendants() {
  local c
  for c in $(ps -o pid= --ppid "$1" 2>/dev/null); do
    printf '%s\n' "$c"
    descendants "$c"
  done
}
# Every listed PID must die within ~5s. Survivors are reported with cmdlines.
assert_all_dead() { # <label> <pid...>
  local label="$1"; shift
  local i pid alive report
  for i in $(seq 1 10); do
    alive=""
    for pid in "$@"; do
      [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && alive="$alive $pid"
    done
    if [[ -z "$alive" ]]; then pass "$label"; return; fi
    sleep 0.5
  done
  report=""
  for pid in $alive; do
    report="$report $pid[ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' '):$(ps -o args= -p "$pid" 2>/dev/null | head -c 100)]"
  done
  fail "$label" "still alive:$report"
}

write_stub() {
  cat > "$T/stubbin/box" <<'STUB'
#!/usr/bin/env bash
T="${BOX_WORK_TEST_T:?}"
printf 'box %s\n' "$*" >>"$T/exec.log"
sub="${1:-}"; shift || true
case "$sub" in
  info) printf '{"box":{"state":"ready","url":"-"}}' ;;
  scp) cp "$1" "$T/captured-runner.sh" ;;
  exec)
    if [[ " $* " == *" --json "* ]]; then
      b64="${@: -1}"
      HOME="${BOX_WORK_TEST_BOX:?}" PATH="${BOX_WORK_TEST_BOX:?}/.local/bin:$PATH" \
        bash "$T/captured-runner.sh" "$b64" >"$T/runner.out" 2>"$T/runner.err"
      rc=$?
      python3 - "$T/runner.out" "$T/runner.err" "$rc" <<'PY'
import json,sys
print(json.dumps({"stdout": open(sys.argv[1]).read(),
                  "stderr": open(sys.argv[2]).read(),
                  "exitCode": int(sys.argv[3])}))
PY
    else
      exit 0
    fi
    ;;
  *) echo "stub box: unknown subcommand $sub" >&2; exit 99 ;;
esac
STUB
  chmod +x "$T/stubbin/box"
}

setup() {
  T="$(mktemp -d "${TMPDIR:-/tmp}/box-work-hb-test.XXXXXX")"
  FAKEHOME="$T/home"
  FAKEBOX="$T/boxhome"
  # Unique fixture-owned repo path: no fixed /home/user/<name> is created or
  # asserted anywhere in this suite, so concurrent or repeated runs cannot
  # collide and nothing outside the fixture is touched.
  REPONAME="hbrepo-$BASHPID-$RANDOM"
  mkdir -p "$FAKEHOME/.agents" "$T/stubbin" "$T/xdg/box-work" \
    "$FAKEBOX/.agents" "$FAKEBOX/.local/bin" "$FAKEBOX/$REPONAME"
  REPO="$T/repo"
  git init -q "$REPO" 2>/dev/null
  git -C "$REPO" remote add origin "https://github.com/itsryanarmani/$REPONAME.git"
  printf 'bx_test123\n' > "$T/xdg/box-work/$REPONAME.id"
  : > "$T/exec.log"
  : > "$FAKEHOME/.agents/agent-clis.env"
  : > "$FAKEBOX/.agents/agent-clis.env"
  export BOX_WORK_TEST_T="$T" BOX_WORK_TEST_BOX="$FAKEBOX"
  write_stub
  cat > "$FAKEBOX/.local/bin/fake-agent" <<'FAKE'
#!/usr/bin/env bash
T="${BOX_WORK_TEST_T:?}"
echo "agent-invoke $(basename "$0") $*" >>"$T/calls.log"
case "${FAKE_AGENT_MODE:-ok}" in
  wait3) sleep 3; echo "AGENT-OUTPUT ${@: -1}" ;;
  # The child sleep carries a fixture-scoped argv[0] so stray descendants are
  # identifiable (and exactly reapable) without global name matching.
  wait30) trap 'exit 143' INT TERM; exec -a "hb-fake-sleep-${BOX_WORK_TEST_T:?}" sleep 30 & wait $!; echo "AGENT-OUTPUT ${@: -1}" ;;
  fail3) sleep 1; echo "agent failed" >&2; exit 3 ;;
  *) echo "AGENT-OUTPUT ${@: -1}" ;;
esac
FAKE
  chmod +x "$FAKEBOX/.local/bin/fake-agent"
  for a in pi muse kimi codex gemini; do
    ln -sf fake-agent "$FAKEBOX/.local/bin/$a"
  done
}

# Run box-work in agent mode; result lands in $T/bw.{out,err,rc}.
run_agent() { # <agent> <brief>
  HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
    BOX_WORK_HEARTBEAT_SECS=1 BOX_WORK_HEARTBEAT_FILE="$T/hb" \
    FAKE_AGENT_MODE="${FAKE_AGENT_MODE:-ok}" \
    bash "$SCRIPT" "$REPO" --agent "$1" "$2" >"$T/bw.out" 2>"$T/bw.err"
  printf '%s' "$?" >"$T/bw.rc"
}

setup

# Sentinel: an unrelated same-marker helper with no fixture path in its argv.
# Scoped cleanup and liveness checks must spare it; a global marker pkill
# would kill it. Killed by recorded PID in cleanup.
( exec bash -c 'while :; do sleep 60; done' box-work-heartbeat-loop ) &
SENTINEL_PID=$!
kill -0 "$SENTINEL_PID" 2>/dev/null \
  && pass "sentinel helper starts" \
  || fail "sentinel helper starts" "could not start sentinel"

# Dispatch once with caller-chosen heartbeat env; result in $T/gen.{out,err,rc}.
# Dynamic VAR=value words go through `env`: a quoted expansion result is never
# re-scanned as an assignment, so prefix position would try to execute it.
gen_dispatch() { # VAR=value... -- <agent> <brief>
  local envs=()
  while [[ "${1:-}" != "--" ]]; do envs+=("$1"); shift; done
  shift
  env HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
    FAKE_AGENT_MODE=ok "${envs[@]}" \
    bash "$SCRIPT" "$REPO" --agent "$1" "$2" >"$T/gen.out" 2>"$T/gen.err"
  printf '%s' "$?" >"$T/gen.rc"
}

# 1. A waiting worker receives periodic heartbeats, and the full brief arrives.
FAKE_AGENT_MODE=wait3 run_agent pi "compute seventeen times twenty three" &
bgpid=$!
sleep 1.5; m1="$(mtime "$T/hb")"; sleep 1.5; m2="$(mtime "$T/hb")"
[ "$m2" -gt "$m1" ] \
  && pass "waiting worker receives periodic heartbeats" \
  || fail "waiting worker receives periodic heartbeats" "m1=$m1 m2=$m2"
wait "$bgpid"
expect_rc "$(cat "$T/bw.rc")" 0 "waiting worker exits 0" "$T/bw.err"
expect_grep "seventeen times twenty three" "$T/bw.out" "multi-word brief arrives intact" "$T/bw.out"

# 2. Normal exit stops the helper: no orphans, heartbeat goes stale.
assert_no_helper "normal exit leaves no helper"
assert_stale "$T/hb" "heartbeat goes stale after exit"

# 3. Failure preserves the worker status and still cleans up.
FAKE_AGENT_MODE=fail3 run_agent pi "anything"
expect_rc "$(cat "$T/bw.rc")" 3 "agent failure exit code propagates" "$T/bw.err"
assert_no_helper "failure leaves no helper"
assert_stale "$T/hb" "heartbeat goes stale after failure"

# 4. Termination kills the whole job: no success masquerade, no orphans.
export HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
  FAKE_AGENT_MODE=wait30
export BOX_WORK_HEARTBEAT_SECS=1 BOX_WORK_HEARTBEAT_FILE="$T/hb-term"
setsid bash "$SCRIPT" "$REPO" --agent pi "long job" >"$T/bw.out" 2>"$T/bw.err" &
bgpid=$!
sleep 2
[ -f "$T/hb-term" ] \
  && pass "terminated job had a live heartbeat first" \
  || fail "terminated job had a live heartbeat first" "no hb-term file"
tree4="$(descendants "$bgpid" | tr '\n' ' ')"
[ -n "$tree4" ] \
  && pass "termination tree snapshot is non-empty" \
  || fail "termination tree snapshot is non-empty" "no descendants of $bgpid"
kill -TERM -"$bgpid"
wait "$bgpid"; trc=$?
[ "$trc" != "0" ] \
  && pass "termination does not report success (rc=$trc)" \
  || fail "termination does not report success" "rc=0"
# shellcheck disable=SC2086
assert_all_dead "termination kills every worker descendant" $tree4
assert_no_helper "termination leaves no helper"
assert_sentinel "sentinel survives scoped termination"
assert_stale "$T/hb-term" "heartbeat goes stale after termination"
unset FAKE_AGENT_MODE BOX_WORK_HEARTBEAT_SECS BOX_WORK_HEARTBEAT_FILE

# 5. The generated runner targets the recorded Box with the repo cwd baked in.
expect_grep "bx_test123" "$T/exec.log" "dispatch targets the recorded Box id" "$T/exec.log"
expect_grep "bash /home/user/box-work-run.sh" "$T/exec.log" "dispatch runs the uploaded runner script" "$T/exec.log"
expect_grepF "cd \"\$HOME/$REPONAME\"" "$T/captured-runner.sh" "runner keeps the explicit repository cwd" "$T/captured-runner.sh"
expect_grepF 'HEARTBEAT_SECS="1"' "$T/captured-runner.sh" "heartbeat interval is baked into the runner" "$T/captured-runner.sh"

# 6. Even an uncatchable kill stops the heartbeat: the helper exits on its own
# once its parent is gone. (A PID-only SIGKILL can still strand the worker
# subshell itself -- no shell can trap SIGKILL -- but the stranded worker no
# longer beats the heartbeat, so the reaper exemption ends with the job.)
b64="$(printf '%s' "probe" | base64 | tr -d '\n')"
FAKE_AGENT_MODE=wait30 HOME="$FAKEBOX" PATH="$FAKEBOX/.local/bin:$PATH" \
  bash "$T/captured-runner.sh" "$b64" >"$T/direct.out" 2>"$T/direct.err" &
rpid=$!
sleep 2
kill -KILL "$rpid" 2>/dev/null || true
wait "$rpid" 2>/dev/null || true
sleep 3
assert_no_helper "SIGKILL leaves no helper"
assert_stale "$T/hb-term" "heartbeat goes stale after SIGKILL"
# Reap the stranded SIGKILL subtree (no shell traps SIGKILL); fixture-scoped patterns only.
pkill -f "$T/captured-runner.sh" 2>/dev/null || true
pkill -f "hb-fake-sleep-$T" 2>/dev/null || true
assert_sentinel "sentinel survives SIGKILL cleanup"

# 7. Foreground SIGINT answers promptly with 130 (`timeout` foreground harness;
# `--preserve-status` keeps the runner status instead of masking it as 124).
b64="$(printf '%s' "trap probe" | base64 | tr -d '\n')"
# Watcher snapshots the worker subtree mid-run (timeout blocks); newest match wins.
( sleep 2
  intpid="$(pgrep -f "$T/captured-runner.sh" 2>/dev/null | sort -n | tail -1)"
  printf '%s\n' "$intpid" >"$T/int.pid"
  descendants "$intpid" >"$T/int.tree" 2>/dev/null
  ps -eo pid,ppid,args | grep -F "$T/" >"$T/int.ps" 2>/dev/null ) &
watcherpid=$!
FAKE_AGENT_MODE=wait30 HOME="$FAKEBOX" PATH="$FAKEBOX/.local/bin:$PATH" \
  timeout --preserve-status -s INT 4 bash "$T/captured-runner.sh" "$b64" >"$T/int.out" 2>"$T/int.err"
irc=$?
expect_rc "$irc" 130 "foreground SIGINT reports 130" "$T/int.err"
# Wait only for the watcher (waiting bare would hang on the live sentinel).
wait "$watcherpid" 2>/dev/null || true
# Non-empty snapshot required: an empty tree would let descendant checks pass vacuously.
[ -s "$T/int.tree" ] \
  && pass "SIGINT tree snapshot is non-empty" \
  || fail "SIGINT tree snapshot is non-empty" "snapshot empty; descendant checks below are vacuous"
# shellcheck disable=SC2046
assert_all_dead "SIGINT kills every worker descendant" $(cat "$T/int.tree" 2>/dev/null)
assert_no_helper "SIGINT leaves no helper"
assert_stale "$T/hb-term" "heartbeat goes stale after SIGINT"

FAKE_AGENT_MODE=wait30 HOME="$FAKEBOX" PATH="$FAKEBOX/.local/bin:$PATH" \
  bash "$T/captured-runner.sh" "$b64" >"$T/term.out" 2>"$T/term.err" &
rpid=$!
sleep 2
termtree="$(descendants "$rpid" | tr '\n' ' ')"
[ -n "$termtree" ] \
  && pass "TERM tree snapshot is non-empty" \
  || fail "TERM tree snapshot is non-empty" "no descendants of $rpid"
kill -TERM "$rpid" 2>/dev/null || true
wait "$rpid" 2>/dev/null; trc2=$?
expect_rc "$trc2" 143 "SIGTERM to the runner reports 143" "$T/term.err"
# shellcheck disable=SC2086
assert_all_dead "SIGTERM kills every worker descendant" $termtree
assert_no_helper "SIGTERM leaves no helper"

# 8. Invalid intervals fail clearly (30 is omitted-default only, never fallback).
for bad in bogus 0 00 000 ""; do
  gen_dispatch "BOX_WORK_HEARTBEAT_SECS=$bad" "BOX_WORK_HEARTBEAT_FILE=$T/hb-bad" -- pi "anything"
  expect_rc "$(cat "$T/gen.rc")" 2 "invalid interval '$bad' exits 2" "$T/gen.err"
  expect_grep "invalid BOX_WORK_HEARTBEAT_SECS" "$T/gen.err" "invalid interval '$bad' names the variable" "$T/gen.err"
done

# 9. An omitted interval keeps 30 as the default through the generated runner.
HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
  FAKE_AGENT_MODE=ok BOX_WORK_HEARTBEAT_FILE="$T/hb" \
  env -u BOX_WORK_HEARTBEAT_SECS \
  bash "$SCRIPT" "$REPO" --agent pi "anything" >"$T/gen.out" 2>"$T/gen.err"
genrc=$?
expect_rc "$genrc" 0 "omitted interval dispatches cleanly" "$T/gen.err"
expect_grepF 'HEARTBEAT_SECS="30"' "$T/captured-runner.sh" "omitted interval bakes the 30s default" "$T/captured-runner.sh"

# 10. An unwritable heartbeat file warns loudly but does not fail the job.
HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
  BOX_WORK_HEARTBEAT_SECS=1 BOX_WORK_HEARTBEAT_FILE="$T/no-such-dir/hb" \
  FAKE_AGENT_MODE=ok \
  bash "$SCRIPT" "$REPO" --agent pi "anything" >"$T/bw.out" 2>"$T/bw.err"
rc9=$?
expect_rc "$rc9" 0 "unwritable heartbeat still runs the job" "$T/bw.err"
expect_grep "idle-reaper exemption inactive" "$T/bw.err" "unwritable heartbeat warns on stderr" "$T/bw.err"

# 11. Canonical identity: no kill-0 fallback; ps + parent start required.
expect_absent 'kill -0 "$_hp_pid"' "$T/captured-runner.sh" "no kill-0 fallback for parent identity"
expect_absent '[ -n "$_hp_start" ]' "$T/captured-runner.sh" "start-time check is unconditional"
mkdir -p "$T/fakeps" "$T/emptybin"
printf '#!/usr/bin/env bash\nexit 1\n' >"$T/fakeps/ps"; chmod +x "$T/fakeps/ps"
b64="$(printf '%s' "identity probe" | base64 | tr -d '\n')"
HOME="$FAKEBOX" PATH="$T/fakeps:/usr/bin:/bin" bash "$T/captured-runner.sh" "$b64" >"$T/ps-bad.out" 2>"$T/ps-bad.err"; rc=$?
expect_rc "$rc" 2 "broken ps exits 2" "$T/ps-bad.err"
expect_grepE "ps|start time" "$T/ps-bad.err" "broken ps names the cause" "$T/ps-bad.err"
HOME="$FAKEBOX" PATH="$T/emptybin" "$BASH" "$T/captured-runner.sh" "$b64" >"$T/ps-abs.out" 2>"$T/ps-abs.err"; rc=$?
expect_rc "$rc" 2 "absent ps exits 2" "$T/ps-abs.err"
expect_grepE "ps|start time" "$T/ps-abs.err" "absent ps names the cause" "$T/ps-abs.err"
assert_no_helper "ps failure launches no helper"

# 12. Post-sleep recheck: a parent that exits mid-sleep buys no fresh
# exemption; any post-mortem touch advances mtime within 2.5s below.
gen_dispatch "BOX_WORK_HEARTBEAT_SECS=1" "BOX_WORK_HEARTBEAT_FILE=$T/hb-post" -- pi "anything"
b64="$(printf '%s' "post-sleep probe" | base64 | tr -d '\n')"
FAKE_AGENT_MODE=wait30 HOME="$FAKEBOX" PATH="$FAKEBOX/.local/bin:$PATH" \
  bash "$T/captured-runner.sh" "$b64" >"$T/post.out" 2>"$T/post.err" &
rpid=$!
sleep 2
kill -KILL "$rpid" 2>/dev/null || true
wait "$rpid" 2>/dev/null || true
m_post="$(fmtime "$T/hb-post")"
sleep 2.5
[ "$(fmtime "$T/hb-post")" = "$m_post" ] \
  && pass "no heartbeat after parent exits mid-sleep" \
  || fail "no heartbeat after parent exits mid-sleep" "mtime advanced post-mortem"
assert_no_helper "post-sleep exit leaves no helper"
pkill -f "$T/captured-runner.sh" 2>/dev/null || true
pkill -f "hb-fake-sleep-$T" 2>/dev/null || true

# 13. reap_tree records identity and revalidates before delayed SIGKILL.
# Shipped functions run verbatim with stub ps/kill/sleep; TERM flips the
# fake start time (simulating PID reuse), sparing only the recycled PID.
sed -n '/^kill_tree()/,/^}/p;/^reap_tree()/,/^}/p' "$T/captured-runner.sh" >"$T/reap.funcs"
expect_grep "_rt_want" "$T/reap.funcs" "reap_tree records descendant identity" "$T/reap.funcs"
expect_absent 'kill -0 "$_rt_p"' "$T/reap.funcs" "reap_tree has no kill-0 identity check"
( FAKE_START="START-A"; KILLS=""; SCEN="reuse"
  sleep() { :; }
  kill() { case "$1" in -TERM) [ "$SCEN" = reuse ] && { FAKE_START="START-B"; SCEN="done"; };; -KILL) KILLS="$KILLS$2 ";; esac; return 0; }
  ps() { case "$*" in *--ppid\ 99999*) printf '424242\n';; *--ppid*) :;; *stat=*) printf 'S\n';; *lstart=*) printf '%s\n' "$FAKE_START";; *) command ps "$@";; esac; }
  . "$T/reap.funcs"
  reap_tree 99999 >/dev/null 2>&1
  case "$KILLS" in *424242*) echo "REUSE-424242-KILLED:$KILLS";; *) echo "REUSE-424242-SPARED";; esac
  case "$KILLS" in *99999*) echo "REUSE-ROOT-KILLED";; *) echo "REUSE-ROOT-SPARED:$KILLS";; esac
  SCEN="same"; KILLS=""; FAKE_START="START-A"
  reap_tree 99999 >/dev/null 2>&1
  case "$KILLS" in *424242*) echo "SAME-KILLED";; *) echo "SAME-SPARED:$KILLS";; esac
) >"$T/reap.probe" 2>&1
expect_grep "REUSE-424242-SPARED" "$T/reap.probe" "recycled PID is spared SIGKILL" "$T/reap.probe"
expect_grep "REUSE-ROOT-KILLED" "$T/reap.probe" "genuine survivor still gets SIGKILL" "$T/reap.probe"
expect_grep "SAME-KILLED" "$T/reap.probe" "matched survivor still gets SIGKILL" "$T/reap.probe"

# Final scoping proof: the unrelated sentinel survived the whole suite.
assert_sentinel "sentinel survives the full suite"

echo "pass=$PASS fail=$FAIL"
[ "$FAIL" = "0" ]
