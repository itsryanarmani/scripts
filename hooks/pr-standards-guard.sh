#!/usr/bin/env bash
# A Claude Code PreToolUse hook. It rejects non-conforming branch names before
# they exist. A hook that cannot understand its input must let the call through.
set -uo pipefail

command -v python3 >/dev/null 2>&1 || exit 0

input=$(cat || true)
[ -n "$input" ] || exit 0

# Emit one base64 JSON record for each branch-creating git command and each
# gh pr create call. Shell parsing errors produce no records, which fails open.
records=$(INPUT="$input" python3 <<'PY' 2>/dev/null || true
import base64, json, os, re, shlex

try:
    data = json.loads(os.environ.get("INPUT", ""))
    if (data.get("tool_name") or data.get("tool") or "Bash") != "Bash":
        raise ValueError
    command = (data.get("tool_input") or {}).get("command") or data.get("command") or ""
except Exception:
    raise SystemExit(0)

operators = {"&&", "||", ";", "|", "&"}

# A heredoc body is data the shell hands to another program, not commands the
# shell runs. Scanning it judged the example inside `cat <<'EOF' ... EOF` as a
# real call, which blocked writing a test or a doc that quotes one.
#
# Both of the rules below have to be quote-aware, or they fail OPEN -- the
# dangerous direction. A `#` inside quotes is not a comment, and a `<<` inside
# quotes does not open a heredoc, so scanning for either blindly let a real
# `git checkout -b bad-name` on the next line go unjudged. A heredoc delimiter
# also cannot start with a digit, which is what keeps the shift in
# `$((1 << 2))` from being read as an opener that swallows the following lines.
def scan(line):
    """Return (code_before_any_comment, heredoc_delimiter_or_None)."""
    out = []
    delim = None
    quote = None
    arith = 0
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            out.append(char)
            if char == "\\" and quote == '"' and index + 1 < len(line):
                out.append(line[index + 1]); index += 2; continue
            if char == quote: quote = None
            index += 1; continue
        if char == "\\" and index + 1 < len(line):
            out.append(char); out.append(line[index + 1]); index += 2; continue
        if char in "'\"":
            quote = char; out.append(char); index += 1; continue
        if char == "#" and (not out or out[-1] in " \t;&|"):
            break
        if char == "(" and line.startswith("((", index):
            # `$(( ))` and `(( ))` are arithmetic. A `<<` inside one is a shift,
            # never a heredoc opener. Excluding only a DIGIT after `<<` was not
            # enough: `$((1 << n))` shifts by a variable, so the delimiter test
            # saw a letter, opened a heredoc, and swallowed every line after it
            # -- including a real `git checkout -b`. That fails OPEN.
            arith += 1
            out.append(char); out.append(line[index + 1]); index += 2; continue
        if char == ")" and line.startswith("))", index) and arith > 0:
            arith -= 1
            out.append(char); out.append(line[index + 1]); index += 2; continue
        if char == "<" and line.startswith("<<", index) and not line.startswith("<<<", index):
            if delim is None and arith == 0:
                rest = index + 2
                if rest < len(line) and line[rest] == "-": rest += 1
                while rest < len(line) and line[rest] in " \t": rest += 1
                # A delimiter starts with a letter, underscore, quote or
                # backslash -- never a digit, so an arithmetic shift is not one.
                if rest < len(line) and (line[rest].isalpha() or line[rest] in "_'\"\\"):
                    word = []
                    at = rest
                    while at < len(line):
                        current = line[at]
                        if current == "\\" and at + 1 < len(line):
                            word.append(line[at + 1]); at += 2; continue
                        if current in "'\"":
                            close = line.find(current, at + 1)
                            if close == -1: break
                            word.append(line[at + 1:close]); at = close + 1; continue
                        if current.isalnum() or current in "_.-":
                            word.append(current); at += 1; continue
                        break
                    if word: delim = "".join(word)
            out.append(char); index += 1; continue
        out.append(char); index += 1
    return "".join(out), delim

lines = []
pending = None
for line in command.split("\n"):
    if pending is not None:
        if line.strip() == pending: pending = None
        continue
    code, delim = scan(line)
    lines.append(code)
    if delim: pending = delim

segments = []
for line in lines:
    # Per LINE, not per command. An unbalanced quote anywhere -- a heredoc body
    # is the common one -- makes shlex raise, and wrapping the whole loop
    # discarded every segment already found on earlier lines. So a multi-line
    # call whose first line creates a bad branch and whose fifth line contains
    # a stray quote sailed through unchecked.
    try:
        # punctuation_chars makes shlex itself yield `&&`, `||`, `;` and `|` as
        # tokens, which is the one tokeniser that gets BOTH cases right:
        #
        #   - an unspaced operator still splits, so `true&&git checkout -b x`
        #     is seen (a regex rewrite of the raw line also managed this);
        #   - a QUOTED payload stays one token, so a command that merely
        #     MENTIONS a branch is not judged as creating one. The regex
        #     rewrite reached inside quotes and tore payloads open, which
        #     blocked writing a test, a diagnostic, or documentation that
        #     quotes an example command.
        #
        # Quoted tokens keep their quote characters, so such a token can never
        # equal `git` or `gh` and can never be a segment head.
        lexer = shlex.shlex(line, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        continue
    current = []
    for token in tokens:
        if token in operators:
            segments.append(current)
            current = []
        else:
            current.append(token)
    segments.append(current)

assignment = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
create_flags = {"-f", "--force", "-t", "--track", "--no-track", "-c", "-C", "--copy"}
copy_flags = {"-c", "-C", "--copy"}

def unquote(value):
    # punctuation_chars tokenising keeps a quoted token's quote characters, so
    # an option value arrives as "'[SCR-1] Subject'" rather than the string the
    # shell would pass. Strip one matched pair; anything else is left alone.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value

def option_value(tokens, names):
    # gh/cobra flags: a repeated flag has the LAST occurrence win, and a
    # single-letter shorthand may glue its value directly (-Rowner/repo)
    # with no "=" or space. Scanning the whole token list and keeping the
    # last match (rather than returning on the first) matches that.
    short_names = [name for name in names if len(name) == 2 and name[0] == "-" and name[1] != "-"]
    result = None
    for index, token in enumerate(tokens):
        if token in names and index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
            result = tokens[index + 1]
            continue
        matched = False
        for name in names:
            if token.startswith(f"{name}="):
                result = token[len(name) + 1:]
                matched = True
                break
        if matched:
            continue
        for name in short_names:
            # A glued shorthand is only an option when the token IS the option.
            # Matching any token that merely STARTS with -H let a value inside
            # an unrelated flag win: `--head real --body 'see -Hbad for why'`
            # validated `bad`, because the scan is last-match-wins and the body
            # is scanned later. A real glued shorthand is the first token of an
            # argument, so require the previous token to be a flag or the start.
            if token == name or not token.startswith(name):
                continue
            previous = tokens[index - 1] if index > 0 else None
            if previous is not None and not previous.startswith("-"):
                continue
            result = token[len(name):]
            break
    return None if result is None else unquote(result)

def created_branch(tokens):
    index = 1
    while index < len(tokens) and tokens[index].startswith("-"):
        index += 2 if tokens[index] in {"-C", "-c", "--git-dir", "--work-tree"} else 1
    rest = tokens[index:]
    if not rest:
        return None
    if rest[0] == "checkout": return option_value(rest, {"-b", "-B", "--orphan"})
    if rest[0] == "switch": return option_value(rest, {"-c", "-C", "--orphan"})
    if rest[0] == "worktree": return option_value(rest, {"-b", "-B"}) if len(rest) > 1 and rest[1] == "add" else None
    if rest[0] != "branch": return None
    args = rest[1:]
    if "--" in args:
        split = args.index("--")
        flag_tokens, names = args[:split], args[split + 1:]
    else:
        flag_tokens = [token for token in args if token.startswith("-")]
        names = [token for token in args if not token.startswith("-")]
    flags = set(flag_tokens)
    if not flags <= create_flags or not names: return None
    return names[-1] if flags & copy_flags else names[0]

for tokens in segments:
    while tokens and assignment.match(tokens[0]): tokens = tokens[1:]
    if not tokens: continue
    # A quoted command word ("git" checkout -b x) still runs as git once the
    # shell strips the quotes, but punctuation_chars tokenising above keeps
    # them, so comparing the raw token let quoting the executable name alone
    # evade detection. Unquote before matching the command word only.
    command_word = os.path.basename(unquote(tokens[0]))
    if command_word == "git":
        branch = created_branch(tokens)
        if branch: print(base64.b64encode(json.dumps({"kind": "git", "branch": branch}).encode()).decode())
    if len(tokens) >= 3 and command_word == "gh" and tokens[1:3] == ["pr", "create"]:
        print(base64.b64encode(json.dumps({
            "kind": "gh", "repo": option_value(tokens[3:], {"--repo", "-R"}),
            "head": option_value(tokens[3:], {"--head", "-H"}),
            "title": option_value(tokens[3:], {"--title", "-t"}),
        }).encode()).decode())
PY
)
[ -n "$records" ] || exit 0

origin_repo() {
  local slug
  slug=$(git remote get-url origin 2>/dev/null | sed -n 's#.*github\.com[:/]\([^/]*\/[^/]*\)$#\1#p')
  # The trailing (\.git)? in a single sed pass never fires: greedy [^/]* already
  # consumes ".git" before the optional group gets a chance to match it, so a
  # remote with a .git suffix used to compare unequal to a --repo without one.
  # GitHub owners are case-insensitive, so lowercase here too: this is compared
  # directly against normalize_repo's output below.
  printf '%s' "${slug%.git}" | tr '[:upper:]' '[:lower:]'
}

# gh accepts [HOST/]OWNER/REPO for --repo. Without stripping the host, a
# host-qualified same-org target never matched the itsryanarmani/* check below
# and silently skipped validation entirely. GitHub owner names are
# case-insensitive, so a mixed-case --repo (itsryanarmani/target) must still
# match the lowercase "itsryanarmani/*" check downstream instead of silently
# skipping validation.
normalize_repo() {
  case "$1" in
    */*/*) printf '%s' "${1#*/}" | tr '[:upper:]' '[:lower:]' ;;
    *) printf '%s' "$1" | tr '[:upper:]' '[:lower:]' ;;
  esac
}

local_prefix() {
  # GitHub owners are case-insensitive, same reasoning as origin_repo/
  # normalize_repo above: a ItSrYaNaRmAnI-cased origin must still match, or
  # every local branch check on that checkout silently fails open.
  case "$(git remote get-url origin 2>/dev/null | tr '[:upper:]' '[:lower:]')" in *github.com[:/]pooriaarab/*|*github.com[:/]itsryanarmani/*) ;; *) return 1;; esac
  [ -f .github/pr-standards.json ] || return 1
  python3 -c 'import json; print(json.load(open(".github/pr-standards.json")).get("prefix", ""))' 2>/dev/null
}

# GNU base64 decodes with -d; BSD/macOS base64 only accepts -D. Retrying from
# the same captured string (rather than a live pipe) means the first attempt
# failing can't leave the second reading an already-drained stdin.
decode_base64() {
  printf '%s' "$1" | base64 -d 2>/dev/null || printf '%s' "$1" | base64 -D 2>/dev/null
}

target_prefix() {
  command -v gh >/dev/null 2>&1 || return 1
  local encoded content
  encoded=$(gh api "repos/$1/contents/.github/pr-standards.json" --jq .content 2>/dev/null) || return 1
  content=$(decode_base64 "$encoded") || return 1
  RECORD="$content" python3 -c 'import json,os; print(json.loads(os.environ["RECORD"]).get("prefix", ""))' 2>/dev/null
}

inline_check() {
  local branch="$1" prefix="$2" title="$3" upper issues=""
  # Mirrors pr-standards.mjs's ALWAYS_EXEMPT_BRANCHES/EXEMPT_BRANCH_PREFIXES.
  # "master" and "HEAD" are deliberately absent: the real engine does not
  # exempt them, so exempting them here would let a cross-repo PR (which
  # only ever runs this inline check, never the engine) through when the
  # same head would be rejected for a same-repo target.
  case "$branch" in *'$'*|*'`'*) return 0;; main|release|refactor|gh-pages|release/*|dependabot/*|renovate/*) return 0;; esac
  if ! [[ "$branch" =~ ^${prefix}-[1-9][0-9]*-[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
    issues="Branch name does not meet the standard: ${prefix}-<issue>-<slug>"
  fi
  upper=$(printf %s "$prefix" | tr '[:lower:]' '[:upper:]')
  if [ -n "$title" ] && ! [[ "$title" =~ ^\[$upper-[1-9][0-9]*\]\ .+ ]]; then
    issues="${issues}${issues:+$'\n'}PR title does not meet the standard: [$upper-<issue>] <Imperative subject>"
  fi
  [ -z "$issues" ] || { printf '[PR Standards Guard] blocked\n%s\n' "$issues" >&2; return 2; }
}

status=0
while IFS= read -r encoded; do
  record=$(decode_base64 "$encoded") || continue
  kind=$(RECORD="$record" python3 -c 'import json,os; print(json.loads(os.environ["RECORD"])["kind"])' 2>/dev/null) || continue
  branch=$(RECORD="$record" python3 -c 'import json,os; value=json.loads(os.environ["RECORD"]); print(value.get("branch") or value.get("head") or "")' 2>/dev/null) || continue
  repo=$(RECORD="$record" python3 -c 'import json,os; print(json.loads(os.environ["RECORD"]).get("repo") or "")' 2>/dev/null) || continue
  title=$(RECORD="$record" python3 -c 'import json,os; print(json.loads(os.environ["RECORD"]).get("title") or "")' 2>/dev/null) || continue
  repo=$(normalize_repo "$repo")
  # `owner:branch` names a fork-qualified head. Git ref names cannot contain
  # ":", so stripping up to the first one is safe for plain branches too.
  given="$branch"
  branch="${branch#*:}"
  # A --head that carries only the fork qualifier (`--head owner:`) names no
  # branch this hook can judge. Falling through here used the CHECKOUT's current
  # branch instead, so a conforming PR was blocked by the name of whatever
  # branch happened to be checked out -- a verdict about the wrong ref. Nothing
  # knowable is being asserted, so fail open.
  if [ "$kind" = gh ] && [ -n "$given" ] && [ -z "$branch" ]; then continue; fi

  if [ "$kind" = gh ] && [ -n "$repo" ]; then
    # A remote PR without --head has no safely knowable branch. Do not guess HEAD.
    [ -n "$branch" ] || continue
    case "$repo" in pooriaarab/*|itsryanarmani/*) ;; *) continue;; esac
    prefix=$(target_prefix "$repo") || continue
    [ -n "$prefix" ] || continue
    # precheck reads the cwd config. Cross-repo calls use this resolved prefix
    # inline, so the engine cannot restore the false positive this hook prevents.
    if [ "$repo" != "$(origin_repo)" ]; then
      inline_check "$branch" "$prefix" "$title" || status=2
      continue
    fi
  else
    [ -n "$branch" ] || branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)
    prefix=$(local_prefix) || continue
    [ -n "$prefix" ] || continue
  fi

  if command -v pr-standards >/dev/null 2>&1; then
    output=$(pr-standards precheck --branch "$branch" ${title:+--title "$title"} 2>&1)
    engine_status=$?
    # 127 and 126 mean the engine never ran -- on PATH but its interpreter is
    # missing, or not executable. Reading that as a verdict blocked every
    # branch on a machine with the checker installed and no `node` in the
    # hook's PATH, and the message named the branch as if the branch were the
    # problem. Only a verdict it actually reached is a verdict.
    if [ "$engine_status" -eq 127 ] || [ "$engine_status" -eq 126 ]; then
      inline_check "$branch" "$prefix" "$title" || status=2
    elif [ "$engine_status" -ne 0 ]; then
      printf 'Branch "%s" does not meet the PR standard:\n%s\n' "$branch" "$output" >&2
      status=2
    fi
  else
    inline_check "$branch" "$prefix" "$title" || status=2
  fi
done <<< "$records"
exit "$status"
