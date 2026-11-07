#!/usr/bin/env bash
# Check what the guard blocks and, more importantly, what it lets through.
# A guard that misreads a delete as a create traps you on a bad branch name.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
GUARD="${GUARD:-$HERE/pr-standards-guard.sh}"
REPO_ROOT="$(dirname "$HERE")"

# Put the real engine on PATH for the existing local branch-creation cases.
BIN="$(mktemp -d)"
trap 'rm -rf "$BIN"' EXIT
ln -s "$REPO_ROOT/pr-standards" "$BIN/pr-standards"
export PATH="$BIN:$PATH"

# The target uses tar, not this checkout's scr prefix. This makes cross-repo
# tests prove the guard reads the target settings through gh, without a network.
gh() {
  case " $* " in
    *' repos/itsryanarmani/target-standard/contents/.github/pr-standards.json '*)
      printf '{"prefix":"tar"}' | base64
      ;;
    *' repos/itsryanarmani/scripts/contents/.github/pr-standards.json '*)
      printf '{"prefix":"scr"}' | base64
      ;;
    *) return 1 ;;
  esac
}
export -f gh

fails=0
check() {
  local want="$1" name="$2" command="$3" got
  printf '{"tool_name":"Bash","tool_input":{"command":%s}}' "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$command")" \
    | "$GUARD" >/dev/null 2>&1
  got=$?
  if [ "$got" = "$want" ]; then
    printf 'ok    %s\n' "$name"
  else
    printf 'FAIL  %s (want exit %s, got %s)\n' "$name" "$want" "$got"
    fails=$((fails + 1))
  fi
}

check 2 'blocks a branch created with no issue number' 'git checkout -b my-cool-feature'
check 2 'blocks the -c form of git switch'             'git switch -c my-cool-feature'
check 0 'allows a conforming branch'                   'git checkout -b scr-12-do-one-thing'
check 0 'allows a checkout that creates nothing'       'git checkout main'
check 0 'allows deleting a badly named branch'         'git branch -D my-cool-feature'
check 0 'allows renaming a badly named branch'         'git branch -m my-cool-feature scr-12-do-one-thing'
check 0 'ignores a command that is not git'            'echo git checkout -b nope'
check 0 'lets unparseable input through'               'git checkout -b "unterminated'
check 2 'blocks an orphan branch'                      'git checkout --orphan my-cool-feature'
check 2 'blocks the orphan form of git switch'         'git switch --orphan my-cool-feature'
check 2 'checks the copy target, not the source'       'git branch -c scr-12-do-one-thing my-cool-feature'
check 2 'sees a git call after an unspaced operator'   'true&&git checkout -b my-cool-feature'
check 2 'checks every branch a chain creates'          'git checkout -b scr-12-do-one-thing && git checkout -b my-cool-feature'
check 0 'allows listing branches by pattern'           'git branch --list my-cool-*'
check 0 'allows showing the current branch'            'git branch --show-current'
check 0 'ignores a git call hidden in a comment'       'echo ok # note; git checkout -b my-cool-feature'
check 2 'sees a git call on the next line'             $'echo ready\ngit checkout -b my-cool-feature'
check 2 'sees a git call after an env var assignment'  'FOO=bar git checkout -b my-cool-feature'
check 2 'treats -- as end of options for git branch'   'git branch -- my-cool-feature'
check 2 'sees a branch created via git worktree add'   'git worktree add -b my-cool-feature /tmp/tree'
# Fail-open holes the heredoc and comment scanner opened on its first pass. Each
# swallowed the REST of the command, so a real bad branch on a later line went
# unjudged and the hook exited 0 -- the dangerous direction for a guard.
check 2 'an arithmetic shift does not open a heredoc'  $'n=$((1 << 2))\ngit checkout -b my-cool-feature'
# A `<<` inside `$(( ))` or `(( ))` is a shift, not a heredoc opener. Filtering
# only a DIGIT after `<<` left every variable shift opening a heredoc that
# swallowed the real command on the next line, so the hook exited 0.
check 2 'a variable arithmetic shift is not a heredoc'  $'n=$((1 << n))\ngit checkout -b my-cool-feature'
check 2 'an all-variable arithmetic shift is not a heredoc' $'n=$((x << y))\ngit checkout -b my-cool-feature'
check 2 'an unspaced arithmetic shift is not a heredoc'  $'n=$((x<<y))\ngit checkout -b my-cool-feature'
check 2 'a bare (( )) shift is not a heredoc'            $'((x << y))\ngit checkout -b my-cool-feature'
check 2 'a quoted <<EOF does not open a heredoc'       $'echo \'use cat <<EOF\'\ngit checkout -b my-cool-feature'
check 2 'a # inside quotes is not a comment'           'echo "see #118"; git checkout -b my-cool-feature'
check 0 'allows a conforming cross-repo PR head'       'gh pr create --repo itsryanarmani/target-standard --head tar-12-do-one-thing'
check 2 'blocks a bad cross-repo PR head'              'gh pr create --repo itsryanarmani/target-standard --head my-cool-feature'
check 0 'allows a heredoc containing gh pr create'      $'cat <<\'EOF\'\ngh pr create --title "Added the thing"\nEOF'
check 0 'ignores a non-itsryanarmani PR target'           'gh pr create --repo acme/work --head my-cool-feature'
check 2 'blocks a host-qualified cross-repo PR head'   'gh pr create --repo github.com/itsryanarmani/target-standard --head my-cool-feature'
check 0 'strips the owner: fork qualifier from a head' 'gh pr create --repo itsryanarmani/target-standard --head alice:tar-12-do-one-thing'
check 2 'routes an explicit same-repo target through the real engine, not the master exemption' \
                                                        'gh pr create --repo itsryanarmani/scripts --head master'
check 2 'does not exempt master on a cross-repo target' \
                                                        'gh pr create --repo itsryanarmani/target-standard --head master'
check 2 'parses a glued short -R/-H option value'      'gh pr create -Ritsryanarmani/target-standard -Hmy-cool-feature'
check 2 'uses the last of a repeated --head, not the first' \
                                                        'gh pr create --repo itsryanarmani/target-standard --head tar-12-good --head my-cool-feature'
check 2 'blocks a mixed-case cross-repo owner, not skips it' \
                                                        'gh pr create --repo ItSrYaNaRmAnI/target-standard --head my-cool-feature'

# `--head owner:` names no branch. The guard used to fall through to the
# CHECKOUT's current branch and judge THAT, so a conforming PR was refused
# because of the name of whatever branch happened to be checked out. This runs
# from a throwaway repo deliberately sitting on a non-conforming branch, so the
# case cannot pass by accident the way it does from a conforming checkout.
undetermined_head() {
  local tmp got payload
  payload=$(python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' \
    'gh pr create --head owner: --title "[SCR-118] Fix the guard"')
  tmp="$(mktemp -d)"
  (
    cd "$tmp" || exit 1
    git init -q . 2>/dev/null
    git remote add origin https://github.com/itsryanarmani/scripts.git 2>/dev/null
    mkdir -p .github && printf '{"prefix":"scr"}' > .github/pr-standards.json
    git -c user.email=t@t -c user.name=t commit -q --allow-empty -m init 2>/dev/null
    git checkout -q -b definitely-not-conforming 2>/dev/null
    printf '%s' "$payload" | "$GUARD" >/dev/null 2>&1
  )
  got=$?
  rm -rf "$tmp"
  if [ "$got" = 0 ]; then
    printf 'ok    allows an undetermined PR head from a non-conforming checkout\n'
  else
    printf 'FAIL  allows an undetermined PR head from a non-conforming checkout (want exit 0, got %s)\n' "$got"
    fails=$((fails + 1))
  fi
}
undetermined_head

# The three environment shapes this hook actually runs in. Every case below was
# a real defect: the engine's verdict was trusted when it had not run, a quoted
# payload was torn open and judged, and an unspaced operator hid a real call.
for shape in with-engine no-node no-engine; do
  SHAPE_BIN="$(mktemp -d)"
  for tool in gh python3 git bash sh env sed grep tr cat base64 awk dirname; do
    src="$(command -v "$tool" 2>/dev/null)" || continue
    [ -n "$src" ] && ln -sf "$src" "$SHAPE_BIN/$tool"
  done
  case "$shape" in
    with-engine) ln -sf "$REPO_ROOT/pr-standards" "$SHAPE_BIN/pr-standards"
                 ln -sf "$(command -v node)" "$SHAPE_BIN/node" ;;
    # Engine on PATH, interpreter missing: it exits 127 without ever running.
    # Reading that as a verdict blocked every branch on such a machine.
    no-node)     ln -sf "$REPO_ROOT/pr-standards" "$SHAPE_BIN/pr-standards" ;;
    no-engine)   ln -sf "$(command -v node)" "$SHAPE_BIN/node" ;;
  esac

  shape_check() {
    local want="$1" name="$2" command="$3" got payload
    payload=$(python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' "$command")
    printf '%s' "$payload" | PATH="$SHAPE_BIN" "$GUARD" >/dev/null 2>&1
    got=$?
    if [ "$got" = "$want" ]; then
      printf 'ok    [%s] %s\n' "$shape" "$name"
    else
      printf 'FAIL  [%s] %s (want exit %s, got %s)\n' "$shape" "$name" "$want" "$got"
      fails=$((fails + 1))
    fi
  }

  shape_check 0 "a quoted payload naming a bad head is not a call" "$(printf %s cnVuICdnaCBwciBjcmVhdGUgLS1oZWFkIGJhZC94JyBub3Rl | base64 --decode)"
  shape_check 0 "an operator inside quotes does not fabricate a git call" "$(printf %s cHJpbnRmICVzICdub3RlOiB4ICYmIGdpdCBjaGVja291dCAtYiBiYWQtbmFtZSc= | base64 --decode)"
  shape_check 0 "a double-quoted conforming branch is not blocked" "$(printf %s Z2l0IGNoZWNrb3V0IC1iICJzY3ItMTU1LXF1b3RlZC1vayI= | base64 --decode)"
  shape_check 0 "a single-quoted conforming branch is not blocked" "$(printf %s Z2l0IGNoZWNrb3V0IC1iICdzY3ItMTU1LXNpbmdsZS1vayc= | base64 --decode)"
  shape_check 2 "a quoted non-conforming branch is still blocked" "$(printf %s Z2l0IGNoZWNrb3V0IC1iICJub3BlL2JhZCI= | base64 --decode)"
  shape_check 2 "an unbalanced quote on a later line does not discard an earlier one" "$(printf %s Z2l0IGNoZWNrb3V0IC1iIG15LWNvb2wtZmVhdHVyZQplY2hvICJ1bmNsb3NlZA== | base64 --decode)"
  shape_check 2 "an unspaced operator does not hide a real git call" "$(printf %s dHJ1ZSYmZ2l0IGNoZWNrb3V0IC1iIG5vcGU= | base64 --decode)"
  shape_check 2 "a cross-repo bad head is refused" "$(printf %s Z2ggcHIgY3JlYXRlIC0tcmVwbyBpdHNyeWFuYXJtYW5pL3NjcmlwdHMgLS1oZWFkIGJhZC94IC0tdGl0bGUgJ1tTQ1ItMV0gRml4IHRoZSB0aGluZyc= | base64 --decode)"
  shape_check 0 "a cross-repo conforming head is allowed" "$(printf %s Z2ggcHIgY3JlYXRlIC0tcmVwbyBpdHNyeWFuYXJtYW5pL3NjcmlwdHMgLS1oZWFkIHNjci0xNTUtanVkZ2UtdGhlLXRhcmdldC1yZXBvIC0tdGl0bGUgJ1tTQ1ItMTU1XSBKdWRnZSBhIGNyb3NzLXJlcG8gUFIn | base64 --decode)"
  shape_check 0 "a conforming local branch is allowed" "$(printf %s Z2l0IGNoZWNrb3V0IC1iIHNjci0xMi1kby1vbmUtdGhpbmc= | base64 --decode)"
  shape_check 2 "a non-conforming local branch is refused" "$(printf %s Z2l0IGNoZWNrb3V0IC1iIG15LWNvb2wtZmVhdHVyZQ== | base64 --decode)"

  rm -rf "$SHAPE_BIN"
done

[ "$fails" = 0 ] || { printf '\n%s failing\n' "$fails" >&2; exit 1; }
printf '\nall passing\n'
