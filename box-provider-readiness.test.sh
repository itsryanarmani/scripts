#!/usr/bin/env bash
# Tests for box-provider-readiness. Offline stub BOX_CLI; the runner executes
# locally modeling the Box (home is BOX_PROBE_BASE, never local test HOME).
# Tests drive the REAL helper and gate a REAL sentinel with fake gh/git and
# fixture credentials; no live network, and no fixture values in output.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${BOX_READINESS_UNDER_TEST:-$DIR/box-provider-readiness}"
PASS=0; FAIL=0
pass() { echo "ok - $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL - $1"; echo "  $2"; FAIL=$((FAIL+1)); }
cleanup() { rm -rf "${T:-}" "${T2:-}"; }
trap cleanup EXIT
need_ok() { (( rc == 0 )) && [[ -e "$T/sentinel" ]] && pass "$1" || fail "$1" "rc=$rc out=$out"; }
need_fail() { (( rc != 0 )) && [[ ! -e "$T/sentinel" ]] && echo "$out" | grep -q "$2" && pass "$1" || fail "$1" "rc=$rc out=$out"; }
write_stub() {
  cat > "$T/stubbin/box" <<'STUB'
#!/usr/bin/env bash
T="${READINESS_TEST_T:?}"
sub="${1:-}"; shift || true
case "$sub" in
  new) touch "$T/new-called"; echo "stub box: new must not be called" >&2; exit 99 ;;
  scp) dest="${2#*:}"; cp "$1" "$dest" ;;
  exec)
    printf '%s\n' "$*" >>"$T/exec.log"
    after=0; cmd=()
    for a in "$@"; do
      if (( after )); then cmd+=("$a"); continue; fi
      if [[ "$a" == "--" ]]; then after=1; fi
    done
    jout() { python3 -c 'import json,sys; print(json.dumps({"stdout":open(sys.argv[1]).read(),"stderr":open(sys.argv[2]).read(),"exitCode":int(sys.argv[3])}))' "$1" "$2" "$3"; }
    case "${cmd[0]:-}" in
      true) n="$(cat "$T/probe_fails")"
        if (( n > 0 )); then printf '%s' "$((n-1))" >"$T/probe_fails"; echo '{"error":"box_starting"}' >&2; exit 1; fi; exit 0 ;;
      command) if [[ -f "$T/no-binary" ]]; then printf '{"stdout":"","stderr":"","exitCode":1}\n'; else printf '{"stdout":"/home/user/.local/bin/%s","stderr":"","exitCode":0}\n' "${cmd[2]}"; fi ;;
      test)
        case "${cmd[2]:-}" in *github-personal.token) [[ -f "$T/no-gh" ]] && ec=1 || ec=0 ;; *) [[ -f "$T/no-cred" ]] && ec=1 || ec=0 ;; esac
        printf '{"stdout":"","stderr":"","exitCode":%d}\n' "$ec" ;;
      mktemp) d="$(mktemp -d "${cmd[2]}")"; o="$(mktemp)"; printf '%s\n' "$d" >"$o"; e="$(mktemp)"; : >"$e"; jout "$o" "$e" 0 ;;
      bash)
        if [[ -f "$T/timeout" ]]; then echo "box: exec timed out after 30s" >&2; exit 124; fi
        extra=(); [[ -f "$T/stale-env" ]] && extra=(GH_TOKEN=stale-inherited-1 GITHUB_TOKEN=stale-inherited-2)
        env -i PATH="$T/fakebin:/usr/bin:/bin" READINESS_TEST_T="$T" BOX_PROBE_BASE="$T/home" "${extra[@]}" \
          bash "${cmd[@]:1}" >"$T/probe.out" 2>"$T/probe.err"; jout "$T/probe.out" "$T/probe.err" "$?" ;;
      cat) o="$(mktemp)"; e="$(mktemp)"; "${cmd[@]}" >"$o" 2>"$e"; rc=$?; jout "$o" "$e" "$rc" ;;
      rm) printf '%s\n' "${cmd[*]}" >>"$T/rm.log"; "${cmd[@]}" >/dev/null 2>&1; printf '{"stdout":"","stderr":"","exitCode":0}\n' ;;
      *) echo "stub box exec: unknown: ${cmd[*]}" >&2; exit 99 ;;
    esac
    ;;
  *) echo "stub box: unknown subcommand $sub" >&2; exit 99 ;;
esac
STUB
  chmod +x "$T/stubbin/box"
}
mkcli() { # <dir>: one generic fake provider CLI (muse/cursor-agent/pi) asserting its pinned route
  cat > "$1/provider-fake" <<'FAKE'
#!/usr/bin/env bash
T="${READINESS_TEST_T:?}"
name="$(basename "$0")"
case "$name" in
  muse) [[ " $* " == *" --yolo "* && " $* " == *" --model muse-spark-1.3-contributor "* && " $* " == *" --prompt-file "* && " $* " == *" --workspace "* ]] || exit 1 ;;
  cursor-agent) [[ " $* " == *" --output-format json "* && " $* " == *" --model composer-2.5 "* ]] || exit 1 ;;
  pi) [[ " $* " == *" -p "* && " $* " == *" --provider zai-api "* && " $* " == *" --model glm-5.3-flash "* && " $* " == *" --no-extensions "* && " $* " == *" -a "* ]] || exit 1 ;;
  codex) [[ "${CODEX_HOME:-}" == *.codex-personal && " $* " == *" --skip-git-repo-check "* ]] || exit 1
    echo "codex-home=${CODEX_HOME:-unset}" >>"$T/calls.log" ;;
  *) exit 99 ;;
esac
echo "$name $*" >>"$T/calls.log"
if [[ "$name" == muse ]]; then pf=""; prev=""; for a in "$@"; do [[ "$prev" == "--prompt-file" ]] && pf="$a"; prev="$a"; done; prompt="$(cat "$pf")"
else prompt="${@: -1}"; fi
[[ "$prompt" =~ ([0-9]+)\*([0-9]+) ]] || exit 1
prod=$((BASH_REMATCH[1] * BASH_REMATCH[2]))
[[ "$prompt" =~ to\ ([^[:space:]]+/result\.txt) ]] || exit 1
res="${BASH_REMATCH[1]}"
if [[ "$name" == muse && -f "$T/auth-fail" ]]; then echo "muse: Authentication required (test-fixture). MUSE_API_KEY=fake-leak-999" >&2; exit 1; fi
if [[ -f "$T/wrong-write" ]]; then printf '%s\n' "$prod"; printf '%s\n' "$((prod+1))" >"$res"; exit 0; fi
printf '%s\n' "$prod" >"$res"
if [[ "$name" == cursor-agent ]]; then printf '{"result":"%s","usage":{"requests":1}}\n' "$prod"; else printf '%s\n' "$prod"; fi
FAKE
  chmod +x "$1/provider-fake"; ln -s provider-fake "$1/muse"; ln -s provider-fake "$1/cursor-agent"; ln -s provider-fake "$1/pi"; ln -s provider-fake "$1/codex"
}
# Cursor's faithful shape is one JSON object carrying the answer in `result`
# (observed --output-format flag contract); the helper must read that field,
# never the whole line.
write_fakes() {
  cat > "$T/fakebin/gh" <<'FAKE'
#!/usr/bin/env bash
# Fake gh: proves the runner selects the canonical token file over any stale
# inherited GH_TOKEN/GITHUB_TOKEN. Never prints values, only a login name.
C="$(cat "$READINESS_TEST_T/home/.agents/github-personal.token" 2>/dev/null)"
if [[ -f "$READINESS_TEST_T/gh-401" ]]; then echo "Bad credentials (HTTP 401)" >&2; exit 1; fi
[[ -n "$C" && "${GH_TOKEN:-}" == "$C" && "${GITHUB_TOKEN:-}" == "$C" ]] \
  || { echo "fake-gh: expected the canonical token in GH_TOKEN and GITHUB_TOKEN" >&2; exit 1; }
echo "gh-ok" >>"$READINESS_TEST_T/calls.log"
if [[ -f "$READINESS_TEST_T/gh-wrong-login" ]]; then printf 'someone-else\n'; else printf 'pooriaarab\n'; fi
FAKE
  chmod +x "$T/fakebin/gh"
  cat > "$T/fakebin/git" <<'FAKE'
#!/usr/bin/env bash
# Fake git: proves ls-remote carries the canonical token as a Bearer header
# for the intended repo. Never prints the header value.
C="$(cat "$READINESS_TEST_T/home/.agents/github-personal.token" 2>/dev/null)"
if [[ -f "$READINESS_TEST_T/git-fail" ]]; then echo "fake-git: ls-remote failed" >&2; exit 1; fi
[[ -n "$C" && " $* " == *"http.extraHeader=Authorization: Bearer $C"* && " $* " == *"github.com/testowner/testrepo.git"* ]] \
  || { echo "fake-git: missing canonical Bearer header or wrong repo" >&2; exit 1; }
FAKE
  chmod +x "$T/fakebin/git"
}
setup() { # flags become $T/<flag> markers (no-cred, no-gh, stale-env, gh-401, git-fail, timeout, auth-fail, wrong-write, no-binary)
  T="$(mktemp -d "${TMPDIR:-/tmp}/box-readiness-test.XXXXXX")"
  mkdir -p "$T/stubbin" "$T/fakebin" "$T/home/.config/muse" "$T/home/.codex-personal" "$T/home/.agents"
  printf '{"fixture":"test-fixture-no-secret"}\n' > "$T/home/.config/muse/auth.json"
  printf '{"fixture":"test-fixture-no-secret"}\n' > "$T/home/.codex-personal/auth.json"
  printf 'CURSOR_API_KEY=fixture-cursor-no-secret\n' > "$T/home/.agents/cursor.env"
  printf 'fixture-canonical-gh-token-000' > "$T/home/.agents/github-personal.token"
  printf '0' > "$T/probe_fails"; : > "$T/exec.log"; : > "$T/calls.log"; : > "$T/rm.log"
  for f in "$@"; do touch "$T/$f"; done; [[ -f "$T/no-gh" ]] && rm -f "$T/home/.agents/github-personal.token"
  export READINESS_TEST_T="$T"
  write_stub; mkcli "$T/fakebin"; write_fakes
}
run_helper() { # <provider> -- <sentinel...>: always pins --repo so ls-remote is exercised
  local p="$1"; shift
  out=$(BOX_CLI="$T/stubbin/box" BOX_PROBE_BASE="$T/home" \
    "$SCRIPT" --box bx_test123 --provider "$p" --cwd /home/user/fakerepo \
    --repo testowner/testrepo --ready-secs 30 --timeout 30 "$@" 2>&1)
  rc=$?
}
run_github_only() { # [-- <sentinel...>]: pre-clone gate from an existing cwd, no provider probe
  out=$(BOX_CLI="$T/stubbin/box" BOX_PROBE_BASE="$T/home" \
    "$SCRIPT" --box bx_test123 --cwd /home/user/work \
    --repo testowner/testrepo --ready-secs 30 --timeout 30 --github-only "$@" 2>&1)
  rc=$?
}
run_raw() {
  out=$(BOX_CLI="$T/stubbin/box" BOX_PROBE_BASE="$T/home" "$SCRIPT" "$@" 2>&1)
  rc=$?
}
no_leak() { ! grep -q "test-fixture-no-secret\|fixture-cursor-no-secret\|canonical-gh-token" <<<"$out" && pass "$1" || fail "$1" "$out"; }
cleaned() { grep -q "box-provider-readiness-" "$T/rm.log" && pass "$1" || fail "$1" "$(cat "$T/rm.log")"; }
test_fresh_success() {
  setup
  run_helper muse -- touch "$T/sentinel"
  need_ok "fresh box: valid muse probe reaches the sentinel"
  no_leak "fresh box: no credential values logged"
  cleaned "fresh box: unique probe dir cleaned on success"
}
test_resumed_transient_success() {
  setup; printf '2' > "$T/probe_fails"
  run_helper muse -- touch "$T/sentinel"
  (( rc == 0 )) && [[ -e "$T/sentinel" && ! -e "$T/new-called" ]] \
    && pass "resumed box: transient startup reuses the recorded id" || fail "resumed box: transient reuse" "rc=$rc out=$out"
}
test_missing_binary() {
  setup no-binary
  run_helper muse -- touch "$T/sentinel"
  need_fail "missing binary fails before the sentinel" "binary 'muse' not found"
}
test_missing_credential() {
  setup no-cred
  run_helper muse -- touch "$T/sentinel"
  need_fail "missing credential fails explicitly with no fallback" "canonical credential.*missing or empty"
  no_leak "missing credential: no values logged"
}
test_invalid_auth() {
  setup auth-fail
  run_helper muse -- touch "$T/sentinel"
  need_fail "invalid auth fails before the sentinel" "provider bootstrap"
  ! grep -q "fake-leak-999" <<<"$out" && grep -q "redacted" <<<"$out" \
    && pass "invalid auth: output sanitized" || fail "invalid auth: output sanitized" "$out"
}
test_wrong_write() {
  setup wrong-write
  run_helper muse -- touch "$T/sentinel"
  need_fail "wrong probe file fails before the sentinel" "wrote.*expected"
  cleaned "wrong write: unique probe dir cleaned on failure"
}
test_timeout() {
  setup timeout
  run_helper muse -- touch "$T/sentinel"
  need_fail "probe timeout fails before the sentinel" "failed before returning"
}
test_cursor_json_success() {
  setup
  run_helper cursor -- touch "$T/sentinel"
  need_ok "cursor: JSON result reply reaches the sentinel"
  grep -q -- "--output-format json" "$T/calls.log" && grep -q -- "--model composer-2.5" "$T/calls.log" \
    && pass "cursor: pinned model forwarded as JSON" || fail "cursor: route" "$(cat "$T/calls.log")"
  grep -q "model=composer-2.5" <<<"$out" && pass "cursor: log claims the actual model" || fail "cursor: model log" "$out"
  no_leak "cursor: no credential values logged"
}
test_stale_env() {
  setup stale-env
  run_helper muse -- touch "$T/sentinel"
  need_ok "stale GH_TOKEN+GITHUB_TOKEN: canonical file still wins"
  grep -q "gh-ok" "$T/calls.log" && pass "stale env: REST identity via canonical token" || fail "stale env: identity" "$out"
}
test_expired_gh() {
  setup gh-401
  run_helper muse -- touch "$T/sentinel"
  need_fail "expired canonical token fails as bootstrap failure" "bootstrap failure"
}
test_missing_gh() {
  setup no-gh
  run_helper muse -- touch "$T/sentinel"
  need_fail "missing github token fails explicitly" "canonical github token.*missing"
}
test_git_repo_fail() {
  setup git-fail
  run_helper muse -- touch "$T/sentinel"
  need_fail "ls-remote failure fails as bootstrap failure" "bootstrap failure"
}
test_wrong_login() {
  setup gh-wrong-login
  run_helper muse -- touch "$T/sentinel"
  need_fail "wrong github identity fails before the sentinel" "not the canonical personal account"
}
test_github_only() {
  setup
  run_github_only -- touch "$T/sentinel"
  need_ok "github-only gate reaches the sentinel without a provider probe"
  grep -q "READY github=pooriaarab repo=testowner/testrepo" <<<"$out" \
    && pass "github-only gate proves the personal identity and repo access" || fail "github-only gate identity proof" "$out"
  grep -q "box-provider-github-" "$T/exec.log" && ! grep -q "box-provider-probe-" "$T/exec.log" \
    && pass "github-only gate ships only the identity runner, no provider probe" || fail "github-only gate runners" "$(cat "$T/exec.log")"
  rm -rf "$T"; setup gh-wrong-login
  run_github_only -- touch "$T/sentinel"
  need_fail "github-only gate rejects a wrong identity" "not the canonical personal account"
}
test_codex_personal() {
  setup
  run_helper codex -- touch "$T/sentinel"
  need_ok "codex probe selects the personal profile and reaches the sentinel"
  grep -q "codex-home=.*\.codex-personal" "$T/calls.log" \
    && pass "codex probe runs under CODEX_HOME=*.codex-personal" || fail "codex personal route" "$(cat "$T/calls.log")"
}
test_timeouts_rejected() {
  setup
  run_raw --box bx --provider muse --cwd /home/user/f --ready-secs 0 --timeout 30 -- touch "$T/sentinel"
  need_fail "ready-secs 0 rejected" "above zero"
  run_raw --box bx --provider muse --cwd /home/user/f --ready-secs 30 --timeout 00 -- touch "$T/sentinel"
  need_fail "timeout 00 rejected" "above zero"
  run_raw --box bx --provider muse --cwd /home/user/f --ready-secs 30 --timeout 1801 -- touch "$T/sentinel"
  need_fail "timeout over the bound rejected" "bound"
}
test_models_rejected() {
  setup
  run_raw --box bx --provider muse --model wrong-model --cwd /home/user/f -- touch "$T/sentinel"
  need_fail "muse wrong model fails before any probe" "needs model 'muse-spark-1.3-contributor'"
  run_raw --box bx --provider cursor --model wrong-model --cwd /home/user/f -- touch "$T/sentinel"
  need_fail "cursor wrong model fails before any probe" "needs model 'composer-2.5'"
  run_raw --box bx --provider codex --model anything --cwd /home/user/f -- touch "$T/sentinel"
  need_fail "codex takes no --model" "takes no --model"
  run_raw --box bx --provider deepseek --cwd /home/user/f -- touch "$T/sentinel"
  need_fail "unsupported provider fails before any probe" "unsupported provider"
  [[ -s "$T/exec.log" ]] && fail "model/provider rejects run no probe" "$(cat "$T/exec.log")" || pass "model/provider rejects run no probe"
}
gate_setup() { # stub Box serving the real box-agent and the real helper, provider pi
  # Args become $T2/<marker> files: no-cred, gh-401, git-fail, gh-wrong-login, stale-clone-env.
  T2="$(mktemp -d "${TMPDIR:-/tmp}/box-gate-test.XXXXXX")"
  mkdir -p "$T2/stubbin" "$T2/fakebin" "$T2/boxhome/.pi/agent" "$T2/boxhome/.agents"
  for m in "$@"; do touch "$T2/$m"; done
  [[ -f "$T2/no-cred" ]] || printf '{"provider":"zai","fixture":"no-secret"}\n' > "$T2/boxhome/.pi/agent/auth.json"
  printf 'fixture-canonical-gh-token-000' > "$T2/boxhome/.agents/github-personal.token"
  export GATE_T="$T2" READINESS_TEST_T="$T2"
  mkcli "$T2/fakebin"
  cat > "$T2/fakebin/gh" <<'FAKE'
#!/usr/bin/env bash
# Fake gh: canonical token wins over stale inheritance; repo clone creates
# the checkout. Never prints values, only a login name.
C="$(cat "$GATE_T/boxhome/.agents/github-personal.token" 2>/dev/null)"
if [[ "${1:-}" == "repo" && "${2:-}" == "clone" ]]; then
  [[ -f "$GATE_T/gh-401" ]] && { echo "Bad credentials (HTTP 401)" >&2; exit 1; }
  [[ -n "$C" && "${GH_TOKEN:-}" == "$C" && "${GITHUB_TOKEN:-}" == "$C" ]] \
    || { echo "fake-gh-clone: expected the canonical token" >&2; exit 1; }
  mkdir -p "${4:?}"; echo "gh-clone-ok $3" >>"$GATE_T/calls.log"; exit 0
fi
[[ -f "$GATE_T/gh-401" ]] && { echo "Bad credentials (HTTP 401)" >&2; exit 1; }
[[ -n "$C" && "${GH_TOKEN:-}" == "$C" && "${GITHUB_TOKEN:-}" == "$C" ]] || exit 1
echo "gh-ok" >>"$GATE_T/calls.log"
if [[ -f "$GATE_T/gh-wrong-login" ]]; then printf 'someone-else\n'; else printf 'pooriaarab\n'; fi
FAKE
  chmod +x "$T2/fakebin/gh"
  cat > "$T2/fakebin/git" <<'FAKE'
#!/usr/bin/env bash
# Fake git: proves ls-remote carries the canonical token for the repo.
C="$(cat "$GATE_T/boxhome/.agents/github-personal.token" 2>/dev/null)"
[[ -f "$GATE_T/git-fail" ]] && { echo "fake-git: ls-remote failed" >&2; exit 1; }
[[ -n "$C" && " $* " == *"http.extraHeader=Authorization: Bearer $C"* && " $* " == *"github.com/testowner/testrepo.git"* ]] || exit 1
FAKE
  chmod +x "$T2/fakebin/git"
  cat > "$T2/stubbin/box" <<'STUB'
#!/usr/bin/env bash
T="${GATE_T:?}"
map() { case "$1" in /home/user/*) printf '%s/%s' "$T/boxhome" "${1#/home/user/}" ;; *) printf '%s' "$1" ;; esac; }
jout() { python3 -c 'import json,sys; print(json.dumps({"stdout":open(sys.argv[1]).read(),"stderr":open(sys.argv[2]).read(),"exitCode":int(sys.argv[3])}))' "$1" "$2" "$3"; }
sub="${1:-}"; shift || true
case "$sub" in
  new) printf '1' >>"$T/new-count"; echo '{"id":"bx_9gate7x"}' ;;
  scp) cp "$1" "$(map "${2#*:}")"; printf '%s\n' "${2#*:}" >>"$T/scp.log" ;;
  stop) printf '%s\n' "$*" >>"$T/stop.log" ;;
  list) echo '[]' ;;
  exec)
    printf '%s\n' "$*" >>"$T/exec.log"
    after=0; cmd=(); json=0
    for a in "$@"; do
      [[ "$a" == "--json" ]] && json=1
      if (( after )); then cmd+=("$a"); continue; fi
      [[ "$a" == "--" ]] && after=1
    done
    (( json )) || exit 0
    case "${cmd[0]:-}" in
      command) printf '{"stdout":"/home/user/.local/bin/pi","stderr":"","exitCode":0}\n' ;;
      test) if [[ -s "$(map "${cmd[2]}")" ]]; then printf '{"stdout":"","stderr":"","exitCode":0}\n'; else printf '{"stdout":"","stderr":"","exitCode":1}\n'; fi ;;
      mktemp) d="$(mktemp -d "$(map "${cmd[2]}")")"; o="$(mktemp)"; printf '%s\n' "$d" >"$o"; e="$(mktemp)"; : >"$e"; jout "$o" "$e" 0 ;;
      bash) if [[ "$(map "${cmd[1]}")" == *box-agent-run.sh ]]; then printf 'runner-executed\n' >>"$T/runner.log"; printf '{"stdout":"simulated agent run","stderr":"","exitCode":0}\n';
        else margs=(); for a in "${cmd[@]:2}"; do case "$a" in /home/user/*) margs+=("$(map "$a")");; *) margs+=("$a");; esac; done
          extra=(); [[ -f "$T/stale-clone-env" ]] && extra=(GH_TOKEN=stale-inherited-9 GITHUB_TOKEN=stale-inherited-9)
          env -i PATH="$T/fakebin:/usr/bin:/bin" GATE_T="$T" READINESS_TEST_T="$T" BOX_PROBE_BASE="$T/boxhome" "${extra[@]}" \
            bash "$(map "${cmd[1]}")" "${margs[@]}" >"$T/probe.out" 2>"$T/probe.err"; jout "$T/probe.out" "$T/probe.err" "$?"; fi ;;
      cat) o="$(mktemp)"; e="$(mktemp)"; cat "$(map "${cmd[1]}")" >"$o" 2>"$e"; rc=$?; jout "$o" "$e" "$rc" ;;
      rm|mkdir|true|gh|git) printf '{"stdout":"","stderr":"","exitCode":0}\n' ;;
      *) echo "gate stub box exec: unknown: ${cmd[*]}" >&2; exit 99 ;;
    esac
    ;;
  *) echo "gate stub box: unknown $sub" >&2; exit 99 ;;
esac
STUB
  chmod +x "$T2/stubbin/box"
}
test_gate_success() {
  gate_setup
  out=$(BOX_BIN="$T2/stubbin/box" PATH="$T2/stubbin:$PATH" GATE_T="$T2" BOX_PROBE_BASE="$T2/boxhome" "$DIR/box-agent" pi --repo testowner/testrepo "add a probe note" 2>&1); rc=$?
  ok=1; (( rc == 0 )) || ok=0
  for p in "READY github=pooriaarab" "READY box=bx_9gate7x provider=pi" "box-agent: NO diff"; do grep -q "$p" <<<"$out" || ok=0; done
  grep -q "box-agent-run.sh" "$T2/scp.log" 2>/dev/null || ok=0
  grep -q "runner-executed" "$T2/runner.log" 2>/dev/null || ok=0
  [[ "$(cat "$T2/new-count" 2>/dev/null)" == "1" ]] || ok=0
  grep -q -- "--provider zai-api" "$T2/calls.log" 2>/dev/null || ok=0
  rm -rf "$T2"
  (( ok )) && pass "dispatch gate: ready Box passes the live probe, then the runner ships once" || fail "dispatch gate: ready Box passes the probe, then runs" "rc=$rc out=$out"
}
test_gate_bootstrap_failure() {
  gate_setup no-cred
  out=$(BOX_BIN="$T2/stubbin/box" PATH="$T2/stubbin:$PATH" GATE_T="$T2" BOX_PROBE_BASE="$T2/boxhome" "$DIR/box-agent" pi --repo testowner/testrepo "add a probe note" 2>&1); rc=$?
  ok=1; (( rc == 3 )) || ok=0
  for p in "canonical credential.*missing or empty" "provider bootstrap"; do grep -q "$p" <<<"$out" || ok=0; done
  grep -q "box-agent-clone-" "$T2/scp.log" 2>/dev/null || ok=0
  [[ -e "$T2/runner.log" ]] && ok=0
  grep -q "box-agent-run.sh" "$T2/scp.log" 2>/dev/null && ok=0
  [[ -s "$T2/stop.log" ]] || ok=0
  [[ "$(cat "$T2/new-count" 2>/dev/null)" == "1" ]] || ok=0
  rm -rf "$T2"
  (( ok )) && pass "dispatch gate: bootstrap failure exits 3, worker runner never ships, Box stopped" || fail "dispatch gate: bootstrap failure exits 3 with no worker runner" "rc=$rc out=$out"
}
test_gate_clone_ordering() {
  gate_setup stale-clone-env
  out=$(BOX_BIN="$T2/stubbin/box" PATH="$T2/stubbin:$PATH" GATE_T="$T2" BOX_PROBE_BASE="$T2/boxhome" "$DIR/box-agent" pi --repo testowner/testrepo "add a probe note" 2>&1); rc=$?
  ok=1; (( rc == 0 )) || ok=0
  for p in "READY github=pooriaarab" "READY box=bx_9gate7x provider=pi" "box-agent: NO diff"; do grep -q "$p" <<<"$out" || ok=0; done
  for p in "gh-ok" "gh-clone-ok testowner/testrepo"; do grep -q "$p" "$T2/calls.log" 2>/dev/null || ok=0; done
  g=$(grep -n "box-provider-github-" "$T2/exec.log" 2>/dev/null | head -1 | cut -d: -f1)
  c=$(grep -n "box-agent-clone-" "$T2/exec.log" 2>/dev/null | head -1 | cut -d: -f1)
  pr=$(grep -n "box-provider-probe-" "$T2/exec.log" 2>/dev/null | head -1 | cut -d: -f1)
  w=$(grep -n "box-agent-run.sh" "$T2/exec.log" 2>/dev/null | head -1 | cut -d: -f1)
  [[ -n "$g" && -n "$c" && -n "$pr" && -n "$w" && "$g" -lt "$c" && "$c" -lt "$pr" && "$pr" -lt "$w" ]] || ok=0
  [[ "$(cat "$T2/new-count" 2>/dev/null)" == "1" ]] || ok=0
  rm -rf "$T2"
  (( ok )) && pass "dispatch gate: stale inheritance loses, canonical clone runs after the identity gate, worker ships last" || fail "dispatch gate: clone ordering with stale env" "rc=$rc out=$out"
}
test_gate_github_failure_no_clone() {
  gate_setup gh-401
  out=$(BOX_BIN="$T2/stubbin/box" PATH="$T2/stubbin:$PATH" GATE_T="$T2" BOX_PROBE_BASE="$T2/boxhome" "$DIR/box-agent" pi --repo testowner/testrepo "add a probe note" 2>&1); rc=$?
  ok=1; (( rc == 3 )) || ok=0
  grep -q "bootstrap failure" <<<"$out" || ok=0
  grep -q "box-agent-clone-" "$T2/exec.log" 2>/dev/null && ok=0
  grep -q "box-agent-run.sh" "$T2/scp.log" 2>/dev/null && ok=0
  [[ -e "$T2/runner.log" ]] && ok=0
  [[ -s "$T2/stop.log" ]] || ok=0
  [[ "$(cat "$T2/new-count" 2>/dev/null)" == "1" ]] || ok=0
  rm -rf "$T2"
  (( ok )) && pass "dispatch gate: expired canonical token fails before clone, worker never ships, Box stopped" || fail "dispatch gate: github failure blocks clone" "rc=$rc out=$out"
}
for t in test_fresh_success test_resumed_transient_success test_missing_binary \
  test_missing_credential test_invalid_auth test_wrong_write test_timeout \
  test_cursor_json_success test_stale_env test_expired_gh test_missing_gh \
  test_git_repo_fail test_wrong_login test_github_only test_codex_personal \
  test_timeouts_rejected test_models_rejected \
  test_gate_success test_gate_bootstrap_failure \
  test_gate_clone_ordering test_gate_github_failure_no_clone; do "$t"; done
echo
echo "pass=$PASS fail=$FAIL"
(( FAIL == 0 ))
