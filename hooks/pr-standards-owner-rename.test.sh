#!/usr/bin/env bash
# Exercise the real hook in isolated old-owner and renamed-owner checkouts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
export PATH="$ROOT:$PATH"
gh() {
  case "$*" in
    *repos/pooriaarab/target/contents/.github/pr-standards.json*|*repos/itsryanarmani/target/contents/.github/pr-standards.json*)
      printf '{"prefix":"tar"}' | base64 ;;
    *) return 1 ;;
  esac
}
export -f gh
check() {
  local want="$1" command="$2" code=0
  python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.argv[1]}}))' "$command" |
    "$ROOT/hooks/pr-standards-guard.sh" >"$TEMP/output" 2>&1 || code=$?
  if [ "$code" != "$want" ]; then
    printf 'Expected %s, got %s: %s\n' "$want" "$code" "$command" >&2
    exit 1
  fi
}
for owner in pooriaarab itsryanarmani; do
  mkdir "$TEMP/$owner"
  cd "$TEMP/$owner"
  git init -q
  git remote add origin "https://github.com/$owner/scripts.git"
  mkdir .github
  printf '{"prefix":"scr"}' > .github/pr-standards.json
  check 2 'git switch -c invalid-branch'
  check 0 'git switch -c scr-12-valid-branch'
  check 2 "gh pr create --repo $owner/target --head invalid-branch"
  check 0 "gh pr create --repo $owner/target --head tar-12-valid-branch"
  check 2 "gh pr create --repo github.com/$owner/target --head invalid-branch"
done
check 2 'gh pr create --repo ItSrYaNaRmAnI/target --head invalid-branch'
check 0 'gh pr create --repo unrelated/target --head invalid-branch'
printf '12 owner-rename scenarios passed\n'
