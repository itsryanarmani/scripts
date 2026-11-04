#!/usr/bin/env bash
# Tests for vm-orchestrate. Runs offline: a fake `ssh` runs each remote command
# in a temp "VM home" with a restricted PATH (no gh), and a fake agent records
# its rounds. Row numbers refer to vm-orchestrate.failure-modes.md.
#
# To run against a modified copy: VM_ORCHESTRATE_UNDER_TEST=/tmp/mutant bash vm-orchestrate.test.sh
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${VM_ORCHESTRATE_UNDER_TEST:-$DIR/vm-orchestrate}"
PASS=0; FAIL=0
pass() { echo "ok - $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL - $1"; echo "  $2"; FAIL=$((FAIL+1)); }
check() { if eval "$2"; then pass "$1"; else fail "$1" "$2"; fi; }

T="$(mktemp -d)"
cleanup() { for f in "$T"/home*/orch/runner.pid "$T"/home*/orch/agent.pid; do [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null; done; rm -rf "$T"; return 0; }
trap cleanup EXIT

RBIN="$T/rbin"; mkdir -p "$RBIN" "$T/bin"
for tool in bash sh tar gzip find chmod mkdir cat awk sleep seq date rm mv tail head pkill setsid nohup dirname grep env stat touch rmdir wc; do
  p="$(command -v "$tool" 2>/dev/null)" && ln -s "$p" "$RBIN/$tool"
done
cat > "$T/bin/ssh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_SSH_LOG"
[ "${FAKE_SSH_FAIL:-}" = 1 ] && exit 255
cmd="${*: -1}"
HOME="$FAKE_HOME" PATH="$FAKE_RBIN" exec bash -c "$cmd"
EOF
cat > "$RBIN/fake-agent" <<'EOF'
#!/usr/bin/env bash
cd "$HOME"
echo "$ORCH_ROUND|$ORCH_PROMPT" >> calls.log
[ -n "${TEST_SECRET:-}" ] && touch secret-seen
[ "$(cat done-at 2>/dev/null)" = "$ORCH_ROUND" ] && touch orch/DONE
sleep "$(cat agent-sleep 2>/dev/null || echo 0)"
exit "$(cat exit-code 2>/dev/null || echo 0)"
EOF
chmod +x "$T/bin/ssh" "$RBIN/fake-agent"
export PATH="$T/bin:$PATH" FAKE_RBIN="$RBIN" VM_ORCHESTRATE_VERIFY_WAIT=2
SECRET="s3cr3t-$RANDOM-value"

n=0
# Fresh VM home and bundle for each case; sets H (home), B (bundle), L (ssh log).
fresh() {
  n=$((n+1)); H="$T/home$n"; B="$T/bundle$n"; L="$T/ssh$n.log"
  mkdir -p "$H" "$B"; : > "$L"
  printf '# Brief\n\n## Goals\n- one\n\n## Rules\n- be careful\n' > "$B/BRIEF.md"
  printf "TEST_SECRET='%s'\n" "$SECRET" > "$B/secrets.env"; chmod 600 "$B/secrets.env"
  export FAKE_HOME="$H" FAKE_SSH_LOG="$L" VM_ORCHESTRATE_SSH="ssh user@vm.example"
}
run() { OUT="$("$SCRIPT" "$@" 2>&1)"; CODE=$?; }
start() { run start "$B" --agent-cmd fake-agent --sleep 0 "$@"; }
wait_for() { for _ in $(seq 1 100); do grep -q "$2" "$1" 2>/dev/null && return 0; sleep 0.1; done; return 1; }

fresh; VM_ORCHESTRATE_SSH= run status
check "1: no SSH command exits 2" '[ $CODE -eq 2 ] && [ ! -s "$L" ]'
run frobnicate
check "2: unknown subcommand exits 2" '[ $CODE -eq 2 ]'

fresh; rm "$B/BRIEF.md"; start
check "3: missing BRIEF.md exits 2 before SSH" '[ $CODE -eq 2 ] && [ ! -s "$L" ]'
fresh; chmod 644 "$B/secrets.env"; start
check "4: secrets.env not 600 exits 2 before SSH" '[ $CODE -eq 2 ] && [ ! -s "$L" ]'

fresh; touch "$B/._BRIEF.md"; echo 3 > "$H/agent-sleep"; echo 2 > "$H/done-at"
start --rounds 5
check "8: start returns while the runner works" '[ $CODE -eq 0 ] && kill -0 "$(cat "$H/orch/runner.pid")" 2>/dev/null'
check "20: missing gh on the VM warns" '[[ "$OUT" == *"gh is not installed"* ]]'
OUT1="$OUT"; start
check "5: a live runner refuses a second start" '[ $CODE -eq 1 ]'
wait_for "$H/orch/runner.log" "runner finished"
check "11: DONE stops the runner after round 2" '[ "$(wc -l < "$H/calls.log")" -eq 2 ] && [ -f "$H/orch/DONE" ]'
check "10: each round resumes from BRIEF.md and STATUS.md" 'grep -q "^2|.*BRIEF.md.*STATUS.md.*round 2" "$H/calls.log"'
# Row 6 bites only where GNU tar extracts (a Linux VM, and CI). macOS bsdtar
# folds a ._ entry into extended attributes on extract, so this check cannot
# fail on a Mac.
check "6: no ._ files reach the VM" '[ -z "$(find "$H/orch" -name "._*")" ]'
check "7: secrets reach the agent but never argv" '[ -f "$H/secret-seen" ] && ! grep -q "$SECRET" "$L" && [[ "$OUT1" != *"$SECRET"* ]]'
check "4: secrets.env stays 600 on the VM" '[ "$(stat -c %a "$H/orch/secrets.env" 2>/dev/null || stat -f %Lp "$H/orch/secrets.env")" = 600 ]'
printf 'saw %s\napi_key: abcdef123456\nnormal line\n' "$SECRET" >> "$H/orch/STATUS.md"
run status
check "28: status hides secret values and credential-looking lines" '[[ "$OUT" != *abcdef123456* ]] && [[ "$OUT" == *"normal line"* ]] && [[ "$OUT" == *"line hidden"* ]]'
check "27: the VM folder and logs are private" '[ "$(stat -c %a "$H/orch" 2>/dev/null || stat -f %Lp "$H/orch")" = 700 ] && [ "$(stat -c %a "$H/orch/runner.log" 2>/dev/null || stat -f %Lp "$H/orch/runner.log")" = 600 ]'
check "14: status shows state, never secrets" '[ $CODE -eq 0 ] && [[ "$OUT" == *"DONE: yes"* ]] && [[ "$OUT" != *"$SECRET"* ]]'

rm -f "$H/done-at" "$H/agent-sleep"; start --rounds 1
wait_for "$H/orch/runner.log" "round 1 exit=0" && sleep 0.3
check "24: a new start clears the old DONE and runs" '[ $CODE -eq 0 ] && [ "$(wc -l < "$H/calls.log")" -eq 3 ]'

fresh; echo 1 > "$H/done-at"; start --rounds 3
check "25: a job that ends inside the check exits 0" '[ $CODE -eq 0 ] && [[ "$OUT" == *"already finished"* ]]'

race_ok=0
race_outcomes=()
for _ in 1 2 3 4 5; do
  fresh; echo 3 > "$H/agent-sleep"
  ( start; echo $CODE > "$T/race1" ) & ( start; echo $CODE > "$T/race2" ) & wait
  race_codes="$(cat "$T/race1" "$T/race2" | sort | tr "\n" " ")"
  race_outcomes+=("$race_codes")
  if [ "$race_codes" = "0 1 " ]; then race_ok=1; break; fi
done
if [ "$race_ok" -ne 1 ]; then
  for attempt in "${!race_outcomes[@]}"; do
    printf 'race attempt %s: exit codes %s\n' "$((attempt+1))" "${race_outcomes[$attempt]}"
  done
fi
check "22: of two racing starts, exactly one runs" '[ "$race_ok" = 1 ]'
run stop

fresh; mkdir -p "$H/orch/.lock"; start
check "23: a lock without a runner refuses start" '[ $CODE -eq 1 ] && [[ "$OUT" == *"run stop"* ]]'
run stop; start
check "23: stop clears the lock" '[ $CODE -eq 0 ]'
run stop

fresh; run start "$B" --dir 'x;touch $HOME/pwned' --agent-cmd fake-agent
check "26: shell syntax in --dir exits 2 before SSH" '[ $CODE -eq 2 ] && [ ! -s "$L" ]'

fresh; printf "TEST_SECRET='%s'\nCMD=\$(touch \"\$HOME/pwned\")\n" "$SECRET" > "$B/secrets.env"; echo 1 > "$H/done-at"; start
check "29: a command in a value stays data" '[ $CODE -eq 0 ] && [ ! -e "$H/pwned" ] && [ -f "$H/secret-seen" ]'
fresh; printf 'A=1\ntouch "$HOME/pwned"\n' > "$B/secrets.env"; start
check "29: a line that is not KEY=VALUE stops the runner" '[ $CODE -eq 3 ] && [[ "$OUT" == *"line 2 is not KEY=VALUE"* ]] && [ ! -e "$H/pwned" ]'

fresh; echo 7 > "$H/exit-code"; start --rounds 2
wait_for "$H/orch/runner.log" "runner finished"
check "10: a failing agent gets another round" 'grep -q "round 1 exit=7" "$H/orch/runner.log" && grep -q "round 2 exit=7" "$H/orch/runner.log"'
check "12: the round cap stops the runner" '[ "$(wc -l < "$H/calls.log")" -eq 2 ]'

fresh; printf "TEST_SECRET='%s\n" "$SECRET" > "$B/secrets.env"; start
check "9: a runner that dies at start exits 3 with the result" '[ $CODE -eq 3 ] && [[ "$OUT" == *"failed: secrets.env line 1"* ]] && [[ "$OUT" != *"$SECRET"* ]]'

fresh; FAKE_SSH_FAIL=1 run status
check "13: SSH failure exits 4 with the allowlist hint" '[ $CODE -eq 4 ] && [[ "$OUT" == *"public IP"* ]]'

fresh; mkdir -p "$H/orch"; cp "$B/BRIEF.md" "$H/orch/"
printf -- '## Goal 9\nUse "quotes", $HOME and `ticks` as is.\n' > "$T/goal.md"
run add-goal "$T/goal.md"
check "15/16: the goal lands verbatim before ## Rules" '[ $CODE -eq 0 ] && awk "/Goal 9/{g=NR} /^## Rules/{r=NR} END{exit !(g && r && g<r)}" "$H/orch/BRIEF.md" && grep -qF "Use \"quotes\", \$HOME and \`ticks\` as is." "$H/orch/BRIEF.md"'
printf '# Brief\n' > "$H/orch/BRIEF.md"; run add-goal "$T/goal.md"
check "17: without ## Rules the goal is appended" '[ "$(tail -n 3 "$H/orch/BRIEF.md" | head -n 1)" = "## Goal 9" ]'
: > "$T/empty.md"; : > "$L"; run add-goal "$T/empty.md"
check "18: an empty goal file exits 2 before SSH" '[ $CODE -eq 2 ] && [ ! -s "$L" ]'

fresh; echo 30 > "$H/agent-sleep"; start
echo 30 > "$T/agent-sleep"; HOME="$T" "$RBIN/fake-agent" >/dev/null 2>&1 & OTHER=$!
apid="$(cat "$H/orch/agent.pid")"; rpid="$(cat "$H/orch/runner.pid")"
run stop
sleep 0.5
check "19: stop kills only the PIDs it started" '! kill -0 "$apid" 2>/dev/null && ! kill -0 "$rpid" 2>/dev/null && kill -0 "$OTHER" 2>/dev/null'
kill "$OTHER" 2>/dev/null

echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
