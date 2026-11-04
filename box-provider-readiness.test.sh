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
        # Timeout fixture: the transport gives up while the owned runner is
        # still computing. Plant a REAL local sleeping-child tree (root plus
        # child plus grandchild) and record its root pid where the helper's
        # reaper looks, so reap-and-verify executes for real. Only the
        # timed-out runner is faked; the reaper below runs for real.
        runner=""; case "${cmd[1]:-}" in
          *box-provider-probe-*) runner=probe ;;
          *box-provider-github-*) runner=github ;;
        esac
        if [[ "$runner" == probe && -f "$T/timeout" ]] || [[ "$runner" == github && -f "$T/github-timeout" ]]; then
          if [[ "$runner" == probe ]]; then pidf="${cmd[6]}/pid"; else pidf="${cmd[5]}"; fi
          nonce="$(basename "${cmd[1]}" .sh)"; nonce="${nonce#box-provider-probe-}"; nonce="${nonce#box-provider-github-}"
          tree="$T/fixture-tree-$nonce.sh"
          printf '#!/usr/bin/env bash\nsleep 120 &\n( sleep 120 & wait ) &\nwait\n' >"$tree"
          chmod +x "$tree"
          setsid "$tree" >/dev/null 2>&1 < /dev/null &
          echo $! >"$T/fixture.pid"; echo $! >"$pidf"
          echo "box: exec timed out after 30s" >&2; exit 124
        fi
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
mkcli() { # <dir>: one generic fake provider CLI (muse/cursor-agent/pi/gemini/devin/kimi/codex) asserting its pinned route
  cat > "$1/provider-fake" <<'FAKE'
#!/usr/bin/env bash
T="${READINESS_TEST_T:?}"
name="$(basename "$0")"
case "$name" in
  muse) [[ " $* " == *" --yolo "* && " $* " == *" --model muse-spark-1.3-contributor "* && " $* " == *" --prompt-file "* && " $* " == *" --workspace "* ]] || exit 1 ;;
  cursor-agent) [[ " $* " == *" --output-format json "* && " $* " == *" --model composer-2.5 "* ]] || exit 1 ;;
  pi) [[ "${PI_WORKER:-}" == "1" && " $* " == *" -p "* && " $* " == *" --provider zai-api "* && " $* " == *" --model glm-5.3-flash "* && " $* " == *" --no-extensions "* && " $* " == *" -a "* && " $* " == *" --tools read,grep,find,ls,edit,write,bash "* ]] || exit 1 ;;
  gemini) [[ "${GEMINI_API_KEY:-}" == fixture-gemini-no-secret && "${GEMINI_CLI_HOME:-}" == *.gemini-personal && -z "${GOOGLE_GENAI_USE_VERTEXAI:-}${GOOGLE_APPLICATION_CREDENTIALS:-}${GOOGLE_CLOUD_PROJECT:-}${GOOGLE_CLOUD_LOCATION:-}" && " $* " == *" --skip-trust "* && " $* " == *" --yolo "* && " $* " == *" -m gemini-3.8-flash "* && " $* " == *" -p "* ]] || exit 1
    echo "gemini-home=${GEMINI_CLI_HOME:-unset}" >>"$T/calls.log" ;;
  devin) [[ -z "${DEVIN_API_KEY:-}${DEVIN_TOKEN:-}${WINDSURF_API_KEY:-}" && " $* " == *" --model swe-1.7 "* && " $* " == *" --respect-workspace-trust false "* && " $* " == *" --permission-mode dangerous "* && " $* " == *" -p "* ]] || exit 1 ;;
  kimi) [[ " $* " == *" -m moonshot-ai/kimi-k3 "* && " $* " == *" -p "* ]] || exit 1 ;;
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
if [[ -f "$T/scrub-leak" ]]; then printf 'api_key: leak-lower-1\n{"apiKey": "leak-json-2"}\nSECRET_TOKEN=leak-upper-3\n' >&2; exit 1; fi
if [[ -f "$T/wrong-write" ]]; then printf '%s\n' "$prod"; printf '%s\n' "$((prod+1))" >"$res"; exit 0; fi
# Non-canonical reply envelopes. The file stays correct so each case proves
# the reply gate itself rejects: chatter around the digits, a JSON envelope
# where digits are required, and cursor JSON missing its result contract.
if [[ -f "$T/chatty-head" ]]; then printf 'working on it\n%s\n' "$prod"; printf '%s\n' "$prod" >"$res"; exit 0; fi
if [[ -f "$T/chatty-tail" ]]; then printf '%s\ntool event 7\n' "$prod"; printf '%s\n' "$prod" >"$res"; exit 0; fi
if [[ "$name" == muse && -f "$T/muse-json" ]]; then printf '{"result":"%s"}\n' "$prod"; printf '%s\n' "$prod" >"$res"; exit 0; fi
if [[ "$name" == cursor-agent && -f "$T/cursor-noresult" ]]; then printf '{"output":"%s"}\n' "$prod"; printf '%s\n' "$prod" >"$res"; exit 0; fi
if [[ "$name" == cursor-agent && -f "$T/cursor-badjson" ]]; then printf 'not-json{\n'; printf '%s\n' "$prod" >"$res"; exit 0; fi
if [[ "$name" == cursor-agent && -f "$T/cursor-nondigit" ]]; then printf '{"result":"12a"}\n'; printf '%s\n' "$prod" >"$res"; exit 0; fi
printf '%s\n' "$prod" >"$res"
if [[ "$name" == cursor-agent ]]; then printf '{"result":"%s","usage":{"requests":1}}\n' "$prod"; else printf '%s\n' "$prod"; fi
FAKE
  chmod +x "$1/provider-fake"; for n in muse cursor-agent pi gemini devin kimi codex; do ln -s provider-fake "$1/$n"; done
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
# for the intended repo through a 0600 include.path config file, and that
# the token itself never appears on argv. Never prints the header value.
C="$(cat "$READINESS_TEST_T/home/.agents/github-personal.token" 2>/dev/null)"
if [[ -f "$READINESS_TEST_T/git-fail" ]]; then echo "fake-git: ls-remote failed" >&2; exit 1; fi
[[ -n "$C" && " $* " != *"$C"* && " $* " != *"extraHeader=Authorization"* && " $* " == *"github.com/testowner/testrepo.git"* ]] \
  || { echo "fake-git: token leaked on argv or wrong repo" >&2; exit 1; }
inc=""; for a in "$@"; do case "$a" in include.path=*) inc="${a#include.path=}" ;; esac; done
[[ -n "$inc" && -f "$inc" ]] || { echo "fake-git: no include.path credential config on argv" >&2; exit 1; }
mode="$(stat -f%Lp "$inc" 2>/dev/null || stat -c%a "$inc" 2>/dev/null)"
[[ "$mode" == "600" ]] || { echo "fake-git: credential config is not 0600 (got '$mode')" >&2; exit 1; }
grep -qF "extraHeader = Authorization: Bearer $C" "$inc" \
  || { echo "fake-git: include config missing the canonical Bearer header" >&2; exit 1; }
FAKE
  chmod +x "$T/fakebin/git"
}
setup() { # flags become $T/<flag> markers (no-cred, no-gh, stale-env, gh-401, git-fail, timeout, auth-fail, wrong-write, no-binary)
  T="$(mktemp -d "${TMPDIR:-/tmp}/box-readiness-test.XXXXXX")"
  mkdir -p "$T/stubbin" "$T/fakebin" "$T/home/.config/muse" "$T/home/.codex-personal" "$T/home/.agents" \
    "$T/home/.pi/agent" "$T/home/.gemini-personal/.gemini" "$T/home/.local/share/devin" "$T/home/.kimi-code"
  printf '{"fixture":"test-fixture-no-secret"}\n' > "$T/home/.config/muse/auth.json"
  printf '{"fixture":"test-fixture-no-secret"}\n' > "$T/home/.codex-personal/auth.json"
  printf 'CURSOR_API_KEY=fixture-cursor-no-secret\n' > "$T/home/.agents/cursor.env"
  printf '{"provider":"zai","fixture":"test-fixture-no-secret"}\n' > "$T/home/.pi/agent/auth.json"
  printf 'GEMINI_API_KEY=fixture-gemini-no-secret\n' > "$T/home/.gemini-personal/.gemini/.env"
  printf '[auth]\ntoken = "test-fixture-no-secret"\n' > "$T/home/.local/share/devin/credentials.toml"
  printf '[auth]\ntoken = "test-fixture-no-secret"\n' > "$T/home/.kimi-code/config.toml"
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
# After a timeout run: every pid the reaper reported must be dead (checked
# with kill -0, the same predicate the reaper used), and exec.log must show
# no global kill. Lingering fixture pids are killed by explicit pid only.
fixture_dead() { # <label>
  local p dead=1 all
  all="$(grep -oE 'confirmed dead \(reaped(-after-kill)?:[0-9 ]+\)' <<<"$out" | grep -oE '[0-9]+')"
  [[ -n "$all" ]] || { fail "$1: no reaped pid list" "$out"; return; }
  for p in $all; do kill -0 "$p" 2>/dev/null && dead=0; done
  (( dead )) && pass "$1: every reaped pid is dead" || fail "$1: a reaped pid survived" "$all"
  ! grep -qE 'pkill|killall' "$T/exec.log" \
    && pass "$1: no global kills issued" || fail "$1: global kill" "$(cat "$T/exec.log")"
  for p in $all; do kill -KILL "$p" 2>/dev/null || true; done
}
test_timeout() {
  setup timeout
  run_helper muse -- touch "$T/sentinel"
  need_fail "probe timeout fails before the sentinel" "owned probe tree confirmed dead"
  fixture_dead "probe timeout"
}
test_github_timeout() {
  setup github-timeout
  run_github_only -- touch "$T/sentinel"
  need_fail "github-gate timeout fails before the sentinel" "owned gate tree confirmed dead"
  fixture_dead "github-gate timeout"
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
# Unknown envelopes fail explicitly: leading chatter, a trailing tool-event
# line carrying a digit, a JSON envelope where digits are required, and
# cursor JSON without its result contract. The probe file stays correct in
# every case, so each rejection proves the reply gate, not the file gate.
test_reply_envelopes_rejected() {
  setup chatty-head
  run_helper muse -- touch "$T/sentinel"
  need_fail "leading chatter is not a canonical muse reply" "reply rejected"
  rm -rf "$T"; setup chatty-tail
  run_helper muse -- touch "$T/sentinel"
  need_fail "trailing tool-event digit is not a canonical muse reply" "reply rejected"
  rm -rf "$T"; setup muse-json
  run_helper muse -- touch "$T/sentinel"
  need_fail "JSON envelope is not a canonical muse reply" "reply rejected"
  rm -rf "$T"; setup cursor-noresult
  run_helper cursor -- touch "$T/sentinel"
  need_fail "cursor JSON without a result field fails explicitly" "no result field"
  rm -rf "$T"; setup cursor-badjson
  run_helper cursor -- touch "$T/sentinel"
  need_fail "cursor non-JSON reply fails explicitly" "not one JSON object"
  rm -rf "$T"; setup cursor-nondigit
  run_helper cursor -- touch "$T/sentinel"
  need_fail "cursor non-digit result fails explicitly" "not canonical"
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
test_github_only_sentinel_failure() {
  setup
  run_github_only -- sh -c 'exit 7'
  (( rc == 7 )) && pass "github-only gate propagates the sentinel's exit status" \
    || fail "github-only gate propagates the sentinel's exit status" "rc=$rc out=$out"
}
test_codex_personal() {
  setup
  run_helper codex -- touch "$T/sentinel"
  need_ok "codex probe selects the personal profile and reaches the sentinel"
  grep -q "codex-home=.*\.codex-personal" "$T/calls.log" \
    && pass "codex probe runs under CODEX_HOME=*.codex-personal" || fail "codex personal route" "$(cat "$T/calls.log")"
}
# Each remaining provider's case branch builds a real CLI invocation the
# fakes assert flag-for-flag; calls.log then proves the produced string.
test_pi_invocation() {
  setup
  run_helper pi -- touch "$T/sentinel"
  need_ok "pi probe reaches the sentinel"
  grep -qF -- "-p --no-extensions --provider zai-api --model glm-5.3-flash -a --tools read,grep,find,ls,edit,write,bash" "$T/calls.log" \
    && pass "pi probe runs the pinned zai-api invocation" || fail "pi invocation" "$(cat "$T/calls.log")"
}
test_gemini_invocation() {
  setup
  run_helper gemini -- touch "$T/sentinel"
  need_ok "gemini probe reaches the sentinel"
  grep -qF -- "--skip-trust --yolo -m gemini-3.8-flash -p" "$T/calls.log" \
    && pass "gemini probe runs the pinned personal invocation" || fail "gemini invocation" "$(cat "$T/calls.log")"
  grep -q "gemini-home=.*\.gemini-personal" "$T/calls.log" \
    && pass "gemini probe runs under GEMINI_CLI_HOME=*.gemini-personal" || fail "gemini personal route" "$(cat "$T/calls.log")"
}
test_devin_invocation() {
  setup
  run_helper devin -- touch "$T/sentinel"
  need_ok "devin probe reaches the sentinel"
  grep -qF -- "--model swe-1.7 --respect-workspace-trust false --permission-mode dangerous -p" "$T/calls.log" \
    && pass "devin probe runs the pinned invocation" || fail "devin invocation" "$(cat "$T/calls.log")"
}
test_kimi_invocation() {
  setup
  run_helper kimi -- touch "$T/sentinel"
  need_ok "kimi probe reaches the sentinel"
  grep -qF -- "kimi -m moonshot-ai/kimi-k3 -p" "$T/calls.log" \
    && pass "kimi probe runs the pinned invocation" || fail "kimi invocation" "$(cat "$T/calls.log")"
}
test_scrub_shapes() {
  setup scrub-leak
  run_helper muse -- touch "$T/sentinel"
  need_fail "provider stderr leak fails before the sentinel" "provider bootstrap"
  ! grep -qE "leak-lower-1|leak-json-2|leak-upper-3" <<<"$out" && grep -q "redacted" <<<"$out" \
    && pass "scrub redacts lowercase, colon and JSON secret shapes" || fail "scrub shapes" "$out"
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
# Fake gh: canonical token wins over stale inheritance. Never prints values,
# only a login name. Clone goes through git now, not gh (see fake git below).
C="$(cat "$GATE_T/boxhome/.agents/github-personal.token" 2>/dev/null)"
[[ -f "$GATE_T/gh-401" ]] && { echo "Bad credentials (HTTP 401)" >&2; exit 1; }
[[ -n "$C" && "${GH_TOKEN:-}" == "$C" && "${GITHUB_TOKEN:-}" == "$C" ]] || exit 1
echo "gh-ok" >>"$GATE_T/calls.log"
if [[ -f "$GATE_T/gh-wrong-login" ]]; then printf 'someone-else\n'; else printf 'pooriaarab\n'; fi
FAKE
  chmod +x "$T2/fakebin/gh"
  cat > "$T2/fakebin/git" <<'FAKE'
#!/usr/bin/env bash
# Fake git: proves ls-remote and clone carry the canonical token for the
# repo via an explicit https URL (never gh repo clone -- that would honor
# the Box's configured git_protocol and could clone over ambient SSH). The
# token must ride a 0600 include.path config file, never argv.
C="$(cat "$GATE_T/boxhome/.agents/github-personal.token" 2>/dev/null)"
[[ -n "$C" && " $* " != *"$C"* && " $* " != *"extraHeader=Authorization"* && " $* " == *"github.com/testowner/testrepo.git"* ]] \
  || { echo "fake-git: token leaked on argv or wrong repo" >&2; exit 1; }
inc=""; for a in "$@"; do case "$a" in include.path=*) inc="${a#include.path=}" ;; esac; done
[[ -n "$inc" && -f "$inc" ]] || { echo "fake-git: no include.path credential config on argv" >&2; exit 1; }
mode="$(stat -f%Lp "$inc" 2>/dev/null || stat -c%a "$inc" 2>/dev/null)"
[[ "$mode" == "600" ]] || { echo "fake-git: credential config is not 0600 (got '$mode')" >&2; exit 1; }
grep -qF "Bearer $C" "$inc" || { echo "fake-git: include config missing the canonical token" >&2; exit 1; }
if [[ " $* " == *" clone "* ]]; then
  [[ -f "$GATE_T/git-fail" ]] && { echo "fake-git: clone failed" >&2; exit 1; }
  dest="${@: -1}"
  mkdir -p "$dest"; echo "git-clone-ok testowner/testrepo" >>"$GATE_T/calls.log"; exit 0
fi
[[ -f "$GATE_T/git-fail" ]] && { echo "fake-git: ls-remote failed" >&2; exit 1; }
exit 0
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
      bash) if [[ -f "$T/timeout" && "${cmd[1]:-}" == *box-provider-probe-* ]]; then
          nonce="$(basename "${cmd[1]}" .sh)"; nonce="${nonce#box-provider-probe-}"
          tree="$T/fixture-tree-$nonce.sh"
          printf '#!/usr/bin/env bash\nsleep 120 &\n( sleep 120 & wait ) &\nwait\n' >"$tree"
          chmod +x "$tree"
          setsid "$tree" >/dev/null 2>&1 < /dev/null &
          echo $! >"$T/fixture.pid"; echo $! >"${cmd[6]}/pid"
          echo "box: exec timed out after 30s" >&2; exit 124
        fi
        if [[ "$(map "${cmd[1]}")" == *box-agent-run.sh ]]; then printf 'runner-executed\n' >>"$T/runner.log"; printf '{"stdout":"simulated agent run","stderr":"","exitCode":0}\n';
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
  for p in "gh-ok" "git-clone-ok testowner/testrepo"; do grep -q "$p" "$T2/calls.log" 2>/dev/null || ok=0; done
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
test_gate_probe_failure_no_launch() {
  gate_setup wrong-write
  out=$(BOX_BIN="$T2/stubbin/box" PATH="$T2/stubbin:$PATH" GATE_T="$T2" BOX_PROBE_BASE="$T2/boxhome" "$DIR/box-agent" pi --repo testowner/testrepo "add a probe note" 2>&1); rc=$?
  ok=1; (( rc == 3 )) || ok=0
  grep -q "wrote.*expected" <<<"$out" || ok=0
  grep -q "box-agent-run.sh" "$T2/scp.log" 2>/dev/null && ok=0
  [[ -e "$T2/runner.log" ]] && ok=0
  [[ -s "$T2/stop.log" ]] || ok=0
  rm -rf "$T2"
  (( ok )) && pass "dispatch gate: failed probe assertion blocks every task launch, Box stopped" || fail "dispatch gate: probe failure blocks launch" "rc=$rc out=$out"
}
test_gate_probe_timeout_no_launch() {
  gate_setup timeout
  out=$(BOX_BIN="$T2/stubbin/box" PATH="$T2/stubbin:$PATH" GATE_T="$T2" BOX_PROBE_BASE="$T2/boxhome" "$DIR/box-agent" pi --repo testowner/testrepo "add a probe note" 2>&1); rc=$?
  ok=1; (( rc == 3 )) || ok=0
  grep -q "confirmed dead" <<<"$out" || ok=0
  grep -q "box-agent-run.sh" "$T2/scp.log" 2>/dev/null && ok=0
  [[ -e "$T2/runner.log" ]] && ok=0
  [[ -s "$T2/stop.log" ]] || ok=0
  all="$(grep -oE 'confirmed dead \(reaped(-after-kill)?:[0-9 ]+\)' <<<"$out" | grep -oE '[0-9]+')"
  [[ -n "$all" ]] || ok=0
  for p in $all; do kill -0 "$p" 2>/dev/null && ok=0; done
  for p in $all; do kill -KILL "$p" 2>/dev/null || true; done
  rm -rf "$T2"
  (( ok )) && pass "dispatch gate: probe timeout reaps the owned tree, blocks every task launch, Box stopped" || fail "dispatch gate: probe timeout blocks launch" "rc=$rc out=$out"
}
for t in test_fresh_success test_resumed_transient_success test_missing_binary \
  test_missing_credential test_invalid_auth test_wrong_write test_timeout \
  test_cursor_json_success test_stale_env test_expired_gh test_missing_gh \
  test_git_repo_fail test_wrong_login test_reply_envelopes_rejected test_github_timeout \
  test_github_only test_github_only_sentinel_failure \
  test_codex_personal \
  test_pi_invocation test_gemini_invocation test_devin_invocation \
  test_kimi_invocation test_scrub_shapes \
  test_timeouts_rejected test_models_rejected \
  test_gate_success test_gate_bootstrap_failure \
  test_gate_clone_ordering test_gate_github_failure_no_clone \
  test_gate_probe_failure_no_launch test_gate_probe_timeout_no_launch; do "$t"; done
echo
echo "pass=$PASS fail=$FAIL"
(( FAIL == 0 ))
