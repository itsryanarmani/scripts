#!/usr/bin/env bash
# Tests for box-work startup retry, explicit cwd, credential export, agent
# dispatch, and failure propagation. Offline: stub BOX_CLI, fake agent CLIs,
# generated runner executes locally. No Box is created; no secrets anywhere.
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${BOX_WORK_UNDER_TEST:-$DIR/box-work}"
PASS=0
FAIL=0

pass() { echo "ok - $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL - $1"; echo "  $2"; FAIL=$((FAIL+1)); }

cleanup() { rm -rf "${T:-}"; }
trap cleanup EXIT

write_stub() {
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
    if [[ "${cmd[0]:-}" == "true" ]]; then
      n="$(cat "$T/probe_fails")"
      if (( n > 0 )); then
        printf '%s' "$((n-1))" >"$T/probe_fails"
        echo '{"error":"box_starting"}' >&2; exit 1
      fi
      exit 0
    fi
    b64="${cmd[${#cmd[@]}-1]}"
    if [[ -f "$T/allow-env" ]]; then
      HOME="$T/home" PATH="/usr/bin:/bin" \
        bash "$T/captured-runner.sh" "$b64" >"$T/runner.out" 2>"$T/runner.err"
    else
      # Remote boundary: the runner carries only its files, never caller env.
      # BOX_WORK_TEST_T is harness plumbing for the fake recorders, not
      # product transport: no product variable crosses here.
      env -i HOME="$T/home" PATH="/usr/bin:/bin" BOX_WORK_TEST_T="$T" \
        bash "$T/captured-runner.sh" "$b64" >"$T/runner.out" 2>"$T/runner.err"
    fi
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
write_fake() { # <name> <body...>: body via stdin
  cat > "$FAKEHOME/.local/bin/$1"
  chmod +x "$FAKEHOME/.local/bin/$1"
}
setup() {
  T="$(mktemp -d "${TMPDIR:-/tmp}/box-work-test.XXXXXX")"
  FAKEHOME="$T/home"
  mkdir -p "$FAKEHOME/.agents" "$FAKEHOME/.local/bin" "$T/stubbin" "$T/xdg/box-work"
  REPO="$T/repo"
  git init -q "$REPO" 2>/dev/null
  git -C "$REPO" remote add origin https://github.com/itsryanarmani/fakerepo.git
  # Fixture-owned repo dir: the generated runner cds $HOME/$NAME, and the stub
  # runs it with HOME=$T/home, so no fixed /home/user path is needed here.
  mkdir -p "$FAKEHOME/fakerepo"
  printf 'bx_test123\n' > "$T/xdg/box-work/fakerepo.id"
  printf '0' > "$T/probe_fails"
  : > "$T/exec.log"
  printf 'GEMINI_API_KEY=test-fixture-no-secret\n' > "$FAKEHOME/.agents/agent-clis.env"
  GEMINI_ENV="$FAKEHOME/.gemini-personal/.gemini/.env"
  mkdir -p "${GEMINI_ENV%/*}" && printf 'GEMINI_API_KEY=test-fixture-no-secret\n' > "$GEMINI_ENV"
  export BOX_WORK_TEST_T="$T"
  write_stub
  write_fake cursor-agent <<'FAKE'
#!/usr/bin/env bash
echo "cursor-agent $*" >>"$BOX_WORK_TEST_T/calls.log"
if [[ -n "${FAKE_AGENT_EXIT:-}" && "${FAKE_AGENT_EXIT}" != "0" ]]; then exit "$FAKE_AGENT_EXIT"; fi
if [[ -z "${CURSOR_API_KEY:-}" ]]; then echo "CURSOR_API_KEY missing" >&2; exit 1; fi
echo "CURSOR-OK $*"
FAKE
  write_fake muse <<'FAKE'
#!/usr/bin/env bash
echo "muse $*" >>"$BOX_WORK_TEST_T/calls.log"
[[ " $* " == *" --yolo "* ]] || { echo "muse: missing --yolo" >&2; exit 1; }
[[ " $* " == *" --prompt-file "* ]] || { echo "muse: missing --prompt-file" >&2; exit 1; }
pf=""; prev=""
for a in "$@"; do [[ "$prev" == "--prompt-file" ]] && pf="$a"; prev="$a"; done
[[ -n "$pf" ]] || { echo "muse: empty prompt file" >&2; exit 1; }
cat "$pf"
FAKE
  write_fake devin <<'FAKE'
#!/usr/bin/env bash
echo "devin $*" >>"$BOX_WORK_TEST_T/calls.log"
if [[ -n "${DEVIN_API_KEY+set}" || -n "${DEVIN_TOKEN+set}" || -n "${WINDSURF_API_KEY+set}" ]]; then
  echo "devin: API env leaked into personal route" >&2; exit 1
fi
for f in --model --respect-workspace-trust --permission-mode --prompt-file -p; do
  [[ " $* " == *" $f "* ]] || { echo "devin: missing $f" >&2; exit 1; }
done
pf=""; prev=""
for a in "$@"; do [[ "$prev" == "--prompt-file" ]] && pf="$a"; prev="$a"; done
[[ -n "$pf" ]] || { echo "devin: missing --prompt-file value" >&2; exit 1; }
cat "$pf"
FAKE
  write_fake gemini <<'FAKE'
#!/usr/bin/env bash
echo "gemini $*" >>"$BOX_WORK_TEST_T/calls.log"
[[ "${GEMINI_CLI_HOME:-}" == "$HOME/.gemini-personal" ]] || { echo "gemini: wrong GEMINI_CLI_HOME" >&2; exit 1; }
if [[ -n "${GOOGLE_GENAI_USE_VERTEXAI+set}" || -n "${GOOGLE_APPLICATION_CREDENTIALS+set}" ]]; then
  echo "gemini: Vertex env leaked" >&2; exit 1
fi
[[ -n "${GEMINI_API_KEY:-}" ]] || { echo "gemini: missing key" >&2; exit 1; }
for f in --skip-trust --yolo -p; do
  [[ " $* " == *" $f "* ]] || { echo "gemini: missing $f" >&2; exit 1; }
done
echo "GEMINI-OK $*"
FAKE
}
# Run box-work in agent mode; result lands in $T/bw.{out,err,rc}.
run_agent() { # <agent> <brief>
  HOME="$FAKEHOME" XDG_STATE_HOME="$T/xdg" BOX_CLI="$T/stubbin/box" \
    BOX_WORK_READY_SECS="${BOX_WORK_READY_SECS:-60}" \
    bash "$SCRIPT" "$REPO" --agent "$1" "$2" >"$T/bw.out" 2>"$T/bw.err"
  printf '%s' "$?" >"$T/bw.rc"
}
ok_rc() {
  [ "$(cat "$T/bw.rc")" = "0" ] && pass "$1" || fail "$1" "rc=$(cat "$T/bw.rc") err: $(cat "$T/bw.err")"
}
expect_fail() {
  [ "$(cat "$T/bw.rc")" != "0" ] && pass "$1" || fail "$1" "rc=0 unexpectedly"
  grep -q "$3" "$T/bw.err" && pass "$2" || fail "$2" "$(cat "$T/bw.err")"
}
expect_cli_count() {
  [ "$(grep -c "$1" "$T/calls.log" 2>/dev/null || true)" = "$2" ] && pass "$3" || fail "$3" "$(cat "$T/calls.log")"
}
setup
printf 'CURSOR_API_KEY=test-fixture-no-secret\n' > "$FAKEHOME/.agents/cursor.env"
printf '2' > "$T/probe_fails"
run_agent cursor "compute seventeen times twenty three"
ok_rc "transient startup retried to success"
grep -qF -- '--cwd /home/user' "$T/exec.log" \
  && pass "readiness probes from explicit --cwd /home/user" \
  || fail "readiness probes from explicit --cwd /home/user" "$(cat "$T/exec.log")"
[ "$(grep -cF -- '-- true' "$T/exec.log")" = "3" ] \
  && pass "readiness retried twice before succeeding" \
  || fail "readiness retried twice before succeeding" "$(cat "$T/exec.log")"
[ ! -e "$T/new-called" ] \
  && pass "recorded Box reused, no replacement created" \
  || fail "recorded Box reused, no replacement created" "stub box new ran"
grep -q "CURSOR-OK" "$T/bw.out" \
  && pass "cursor dispatched with exported key" \
  || fail "cursor dispatched with exported key" "$(cat "$T/bw.out") $(cat "$T/bw.err")"
for flag in "--trust" "--force" "--model composer-2.5" "--output-format json"; do
  grep -qF -- "$flag" "$T/calls.log" \
    && pass "cursor headless flag: $flag" \
    || fail "cursor headless flag: $flag" "$(cat "$T/calls.log")"
done
grep -qF "seventeen times twenty three" "$T/bw.out" \
  && pass "multi-word brief arrives intact" \
  || fail "multi-word brief arrives intact" "$(cat "$T/bw.out")"
grep -qF -- '--cwd /home/user/fakerepo' "$T/exec.log" \
  && pass "dispatch exec uses explicit repository cwd" \
  || fail "dispatch exec uses explicit repository cwd" "$(cat "$T/exec.log")"
run_agent muse "say the word banana bread loudly"
ok_rc "muse headless dispatch succeeds"
grep -q "banana bread loudly" "$T/bw.out" \
  && pass "muse receives full brief via prompt file" \
  || fail "muse receives full brief via prompt file" "$(cat "$T/bw.out")"
grep -qF -- "--workspace /home/user/fakerepo" "$T/calls.log" \
  && pass "muse runs in the explicit repository path" \
  || fail "muse runs in the explicit repository path" "$(cat "$T/calls.log")"
touch "$T/allow-env"
DEVIN_API_KEY=should-be-scrubbed DEVIN_TOKEN=should-be-scrubbed WINDSURF_API_KEY=should-be-scrubbed \
  run_agent devin "report the number after six"
ok_rc "devin personal route succeeds"
grep -q "the number after six" "$T/bw.out" \
  && pass "devin personal route scrubs API env and runs" \
  || fail "devin personal route scrubs API env and runs" "$(cat "$T/bw.out") $(cat "$T/bw.err")"
# Prefix assignments persist on function calls; scrub for later cases.
unset DEVIN_API_KEY DEVIN_TOKEN WINDSURF_API_KEY
printf 'DEVIN_API_KEY=file-value-never-sourced\n' > "$FAKEHOME/.agents/devin.env"
DEVIN_API_KEY=should-be-scrubbed run_agent devin "second devin probe"
ok_rc "devin ignores unproven api file and scrubs env"
rm -f "$T/allow-env" "$FAKEHOME/.agents/devin.env"
unset DEVIN_API_KEY
run_agent gemini "name a green fruit"
ok_rc "gemini dispatched with personal env"
for flag in "--skip-trust" "--yolo" "-m gemini-3.8-flash"; do
  grep -qF -- "$flag" "$T/calls.log" \
    && pass "gemini headless flag: $flag" \
    || fail "gemini headless flag: $flag" "$(cat "$T/calls.log")"
done
rm -f "$GEMINI_ENV"
touch "$T/allow-env"
GEMINI_API_KEY=shadow-ambient-value run_agent gemini "anything"
expect_fail "ambient gemini key without file fails" "ambient gemini refusal names the cause" "refusing an ambient"
expect_cli_count "gemini " "1" "ambient gemini key never invokes the CLI"
printf 'OTHER_VAR=not-the-key\n' > "$GEMINI_ENV"
GEMINI_API_KEY=shadow-ambient-value run_agent gemini "anything"
expect_fail "gemini file without key fails" "missing gemini value names the file" "exported by"
expect_cli_count "gemini " "1" "keyless gemini file never invokes the CLI"
rm -f "$T/allow-env"
unset GEMINI_API_KEY
rm -f "$FAKEHOME/.agents/cursor.env"
run_agent cursor "anything"
expect_fail "missing cursor key fails loudly" "missing cursor key names the credential file" "cursor.env"
expect_cli_count "cursor-agent" "1" "missing cursor key never invokes the CLI"

touch "$T/allow-env"
CURSOR_API_KEY=shadow-ambient-value run_agent cursor "anything"
expect_fail "ambient cursor key without file fails" "ambient refusal names the cause" "refusing an ambient"
expect_cli_count "cursor-agent" "1" "ambient cursor key never invokes the CLI"
rm -f "$T/allow-env"
unset CURSOR_API_KEY
printf 'CURSOR_API_KEY=test-fixture-no-secret\n' > "$FAKEHOME/.agents/cursor.env"
touch "$T/allow-env"
FAKE_AGENT_EXIT=3 run_agent cursor "anything"
[ "$(cat "$T/bw.rc")" = "3" ] \
  && pass "agent failure exit code propagates" \
  || fail "agent failure exit code propagates" "rc=$(cat "$T/bw.rc") want 3"
rm -f "$T/allow-env"
unset FAKE_AGENT_EXIT
printf '999' > "$T/probe_fails"
SEC_START="$SECONDS"
BOX_WORK_READY_SECS=6 run_agent cursor "anything"
unset BOX_WORK_READY_SECS
elapsed=$((SECONDS - SEC_START))
expect_fail "unready Box fails instead of hanging" "unready Box names the bounded deadline" "never answered within"
[ "$elapsed" -lt 25 ] \
  && pass "readiness wait is bounded (${elapsed}s)" \
  || fail "readiness wait is bounded (${elapsed}s)" "took too long"

echo "pass=$PASS fail=$FAIL"
[ "$FAIL" = "0" ]
