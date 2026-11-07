#!/usr/bin/env bash
# Smoke contract: reject unsafe names and bad config; never execute config or leak tokens.
set -euo pipefail
repo_dir=$(cd "$(dirname "$0")" && pwd)
test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT
mkdir -p "$test_dir/bin" "$test_dir/home/Documents/Personal/.secrets/pooriaarab-demo-fleet-app"
cp "$repo_dir/gh-app-per-repo-rollout" "$test_dir/bin/"
folder="$test_dir/home/Documents/Personal/.secrets/pooriaarab-demo-fleet-app"
cat > "$test_dir/bin/gh-app" <<'STUB'
#!/usr/bin/env bash
set -eu
[[ "$*" == 'token pooriaarab-demo-fleet-app' ]]
printf 'called\n' >> "$CALL_LOG"
printf 'fake_secret_token\n'
if [[ ${MINT_FAIL:-0} == 1 ]]; then
  printf 'fake_secret_token\n' >&2
  exit 1
fi
STUB
cat > "$test_dir/bin/gh" <<'STUB'
#!/usr/bin/env bash
set -eu
[[ "$*" == 'api rate_limit' && $GH_TOKEN == fake_secret_token ]]
[[ -z ${GH_DEBUG:-} && -z ${GITHUB_TOKEN:-} && $GH_HOST == github.com ]]
printf 'called\n' >> "$CALL_LOG"
if [[ ${API_FAIL:-0} == 1 ]]; then
  printf 'fake_secret_token\n' >&2
  exit 1
fi
if [[ ${BAD_JSON:-0} == 1 ]]; then
  printf '{"resources":{"core":{"limit":"fake_secret_token"}}}\n'
else
  printf '{"resources":{"core":{"limit":5000,"remaining":4999,"reset":123}}}\n'
fi
STUB
chmod +x "$test_dir/bin/gh-app" "$test_dir/bin/gh"
run() {
  local status=0
  env HOME="$test_dir/home" PATH="$test_dir/bin:$PATH" CALL_LOG="$test_dir/calls" \
    GH_DEBUG=api GITHUB_TOKEN=unused GH_HOST=wrong.example \
    "$test_dir/bin/gh-app-per-repo-rollout" "$@" > "$test_dir/output" 2>&1 || status=$?
  if grep -Fq "fake_secret_token" "$test_dir/output"; then
    echo "FAIL: secret in output" >&2; exit 1
  fi
  return "$status"
}
reject() {
  if run "$@"; then echo 'FAIL: command unexpectedly passes' >&2; exit 1; fi
}
run plan demo
grep -Fq './gh-app create --name pooriaarab-demo-fleet' "$test_dir/output"
for perm in contents=write pull_requests=write issues=write workflows=write actions=read checks=read statuses=read; do
  grep -Fq -- "--perm $perm" "$test_dir/output"
done
grep -Fq './gh-app install pooriaarab-demo-fleet --owner itsryanarmani' "$test_dir/output"
grep -Fq './gh-app token pooriaarab-demo-fleet-app' "$test_dir/output"
[[ ! -e "$test_dir/calls" ]]
reject plan ../demo
reject plan 'demo;echo'
reject plan Demo
reject plan demo extra
reject verify demo --unknown
reject verify demo
printf 'APP_ID=123\nAPP_SLUG=pooriaarab-demo-fleet\n' > "$folder/app.env"
reject verify demo
cat > "$folder/app.env" <<'CONFIG'
APP_ID='123'
APP_SLUG=pooriaarab-demo-fleet
export APP_INSTALLATION_ID=42
CONFIG
printf 'fake-key\n' > "$folder/app.pem"
run verify demo
[[ ! -e "$test_dir/calls" ]]
run verify demo --online
grep -Fq '"limit": 5000' "$test_dir/output"
MINT_FAIL=1 reject verify demo --online
API_FAIL=1 reject verify demo --online
BAD_JSON=1 reject verify demo --online
if grep -Fq 'fake_secret_token' "$test_dir/output"; then exit 1; fi
# The fixture contains literal shell code; verification must not run it.
# shellcheck disable=SC2016
printf 'APP_ID=$(touch "%s")\nAPP_SLUG=pooriaarab-demo-fleet\nAPP_INSTALLATION_ID=42\n' \
  "$test_dir/executed" > "$folder/app.env"
reject verify demo
[[ ! -e "$test_dir/executed" ]]
printf 'canonical_repo\tshort\nitsryanarmani/demo\tdemo\n' > "$test_dir/manifest.tsv"
run batch-status "$test_dir/manifest.tsv"
grep -Fq 'summary	total=1	ready=1	missing=0' "$test_dir/output"
printf 'itsryanarmani/x\tBad\n' > "$test_dir/bad-manifest.tsv"
reject batch-status "$test_dir/bad-manifest.tsv"
printf 'PASS: per-repo rollout smoke (plan, config, online, secret filtering, batch-status)\n'
