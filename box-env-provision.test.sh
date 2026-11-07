#!/usr/bin/env bash
# Tests for box-env-provision agent credentials. Offline: stub `box`/`gh`,
# throwaway repo, --dry-run. Contract: --with-agents with a missing manifest
# fails loudly instead of silently provisioning zero agent files.
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${BOX_ENV_PROVISION_UNDER_TEST:-$DIR/box-env-provision}"
PASS=0
FAIL=0

pass() { echo "ok - $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL - $1"; echo "  $2"; FAIL=$((FAIL+1)); }

T="$(mktemp -d "${TMPDIR:-/tmp}/box-env-provision-test.XXXXXX")"
trap 'rm -rf "$T"' EXIT

mkdir -p "$T/stubbin"
cat > "$T/stubbin/box" <<'STUB'
#!/usr/bin/env bash
echo "box $*" >>"${BOX_ENV_TEST_T:?}/box.log"
STUB
cat > "$T/stubbin/gh" <<'STUB'
#!/usr/bin/env bash
[[ "$*" == *"defaultBranchRef"* ]] && echo "main"
exit 0
STUB
chmod +x "$T/stubbin/box" "$T/stubbin/gh"
export BOX_ENV_TEST_T="$T"
export PATH="$T/stubbin:$PATH"

REPO="$T/repo"
git init -q "$REPO" 2>/dev/null
git -C "$REPO" remote add origin https://github.com/itsryanarmani/fakerepo.git
AGENT_CRED_DIR="$T/empty" \
  bash "$SCRIPT" --with-agents "$REPO" >"$T/out1" 2>"$T/err1"
rc=$?
[ "$rc" = "1" ] \
  && pass "missing agent manifest exits 1" \
  || fail "missing agent manifest exits 1" "rc=$rc out: $(cat "$T/out1") err: $(cat "$T/err1")"
grep -q "manifest" "$T/err1" \
  && pass "missing agent manifest names the manifest" \
  || fail "missing agent manifest names the manifest" "$(cat "$T/err1")"
[ ! -e "$T/box.log" ] \
  && pass "missing agent manifest provisions nothing" \
  || fail "missing agent manifest provisions nothing" "$(cat "$T/box.log")"
mkdir -p "$T/creds"
printf 'x' > "$T/creds/credfile"
printf '[[".config/test/cred","credfile","note"]]\n' > "$T/creds/manifest.json"
AGENT_CRED_DIR="$T/creds" \
  bash "$SCRIPT" --dry-run --with-agents "$REPO" >"$T/out2" 2>"$T/err2"
rc=$?
[ "$rc" = "0" ] \
  && pass "present manifest provisions cleanly" \
  || fail "present manifest provisions cleanly" "rc=$rc err: $(cat "$T/err2")"
grep -q "agent CLI credentials: 1 file(s)" "$T/out2" \
  && pass "present manifest provisions one agent file" \
  || fail "present manifest provisions one agent file" "$(cat "$T/out2")"
AGENT_CRED_DIR="$T/empty" \
  bash "$SCRIPT" --dry-run "$REPO" >"$T/out3" 2>"$T/err3"
rc=$?
[ "$rc" = "0" ] \
  && pass "plain provisioning ignores the manifest" \
  || fail "plain provisioning ignores the manifest" "rc=$rc err: $(cat "$T/err3")"
echo "pass=$PASS fail=$FAIL"
[ "$FAIL" = "0" ]
