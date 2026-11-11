#!/usr/bin/env bash
# Offline tests for the signup-sweep launcher. Stubs python3 and a fake
# toolkit; never touches the network. The sweep's own tests live with the
# tool in the domain-email-warming skill.
set -uo pipefail

fail=0
pass=0
ok() { echo "ok - $1"; pass=$((pass+1)); }
bad() { echo "FAIL - $1"; fail=$((fail+1)); }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SCRIPT_DIR/signup-sweep"

ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
mkdir -p "$ROOT/bin" "$ROOT/toolkit/scripts"
echo "# fake" > "$ROOT/toolkit/scripts/signup-sweep.py"

cat > "$ROOT/bin/python3" <<'STUB'
#!/usr/bin/env bash
echo "PY3:$*"
STUB
chmod +x "$ROOT/bin/python3"

run() { PATH="$ROOT/bin:$PATH" WARM_DOMAIN_HOME="$ROOT/toolkit" "$SCRIPT" "$@" 2>&1; }

out=$(run --where)
[ "$out" = "$ROOT/toolkit" ] && ok "--where prints the resolved toolkit" || bad "--where printed: $out"

out=$(run --daemon)
case "$out" in
  PY3:*signup-sweep.py*--daemon*) ok "arguments are forwarded to the sweep" ;;
  *) bad "arguments not forwarded: $out" ;;
esac

out=$(PATH="$ROOT/bin:$PATH" WARM_DOMAIN_HOME="$ROOT/nonexistent" HOME="$ROOT/emptyhome" "$SCRIPT" --once 2>&1)
st=$?
[ $st -ne 0 ] && ok "missing toolkit exits non-zero" || bad "missing toolkit exited 0"
case "$out" in *"cannot find signup-sweep.py"*) ok "missing toolkit explains itself" ;; *) bad "unclear error: $out" ;; esac

echo
echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
