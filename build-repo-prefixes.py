#!/usr/bin/env python3
"""Generate repo-prefixes.json: unique 2-4 char prefix per itsryanarmani repo.

Run:  python3 build-repo-prefixes.py

Writes repo-prefixes.json itself (read-then-atomic-write). Do not redirect
stdout into that file: a shell `>` truncates it before this script starts,
so the read of the existing registry below would already see an empty file.
"""

import json
from pathlib import Path
import re
import string
import subprocess
import sys

# ── helpers ──────────────────────────────────────────────────────────────

GH_LIST_LIMIT = 300


def gh_list():
    """Fetch all itsryanarmani repos via gh CLI."""
    r = subprocess.run(
        ["gh", "repo", "list", "itsryanarmani", "--limit", str(GH_LIST_LIMIT),
         "--json", "name,diskUsage,isArchived,isFork"],
        capture_output=True, text=True, check=True,
    )
    repos = json.loads(r.stdout)
    # `--limit` is also the page size cap gh applies, so a result that fills it
    # exactly is indistinguishable from one `gh` silently truncated. Fail loudly
    # rather than let the registry quietly miss whichever repos sorted last.
    if len(repos) >= GH_LIST_LIMIT:
        print(
            f"ERROR: gh returned {len(repos)} repos, at the --limit {GH_LIST_LIMIT} "
            "ceiling -- raise GH_LIST_LIMIT, the account may have more repos than "
            "this fetched.",
            file=sys.stderr,
        )
        sys.exit(1)
    return repos


# Small dictionary of known English words for word-boundary detection
KNOWN_WORDS = {
    # vibe* suffixes
    "ads", "agent", "brand", "build", "care", "code", "context", "create",
    "core", "daily", "dating", "debug", "donate", "family", "gen", "health",
    "home", "hooks", "host", "kids", "learn", "live", "memory", "money",
    "movie", "music", "network", "news", "notifications", "publish", "qa",
    "radio", "replay", "review", "score", "share", "stream", "study", "teens",
    "translate", "voice",
    # other common words
    "slack", "bot", "gmail", "fox", "cade", "private", "conductor",
    "playground", "default", "branch", "alert", "article", "video",
    "master", "template", "cloudflare", "netlify", "firebase",
    "wordpress", "meta", "description", "generator", "alternative", "text",
    "featured", "image", "notion", "backup", "n8n", "telegram",
    "near", "nomination", "onchain", "nft", "static", "svg",
    "crypto", "foodies", "locowalk", "business", "pagely", "redirect",
    "penguin", "rewards", "users", "richedu", "website", "beehouse",
    "x", "to",
}

def split_camel_lower(s: str) -> list[str]:
    """Split a lowercase concatenated string into known words (greedy)."""
    words = []
    i = 0
    while i < len(s):
        # Greedy: try to match longest known word from this position
        best = None
        for wl in range(min(14, len(s) - i), 0, -1):
            part = s[i : i + wl]
            if part in KNOWN_WORDS:
                best = part
                break
        if best is None:
            # Fallback: treat single char as its own "word"
            best = s[i]
        words.append(best)
        i += len(best)
    return words


def derive_prefix(name: str) -> str:
    """Always return 2-4 lowercase letters.

    The heuristics below have several return paths, and three of them could hand
    back something main() then rejects the whole run over: "---" and "_" for a
    name made only of separators, "3t" for 3d-tools. Validating once here beats
    guarding every branch, and it matches what pr-standards.mjs does for the same
    rule -- two implementations of one rule is already one too many.
    """
    letters = "".join(c for c in _derive_prefix_raw(name).lower() if c.isalpha())[:4]
    if not letters:
        return "zz"
    if len(letters) == 1:
        return letters * 2
    return letters


def _derive_prefix_raw(name: str) -> str:
    """Derive a 2-4 lowercase prefix for a repo name.

    Rules applied in order:
    1. Hyphen / underscore / dot separated → first letter of each part (max 4)
    2. Names that are obviously an initialism → human-picked (rts for private-repo-4ed5)
    3. Single word → first 3 letters, then resolve collisions later
    """
    name_lower = name.lower()

    # ── Known initialisms (hand-picked, human-readable beats mechanical) ──
    overrides = {
        "private-repo-4ed5": "rts",        # reply to social
    }
    if name_lower in overrides:
        return overrides[name_lower]

    # ── Separated names ──
    # Split on every separator in one pass so a mixed name like "foo-bar_baz"
    # yields one part per word (f, b, b), not just per the first separator found.
    if re.search(r"[-_.]", name_lower):
        parts = [p for p in re.split(r"[-_.]+", name_lower) if p]
        if parts:
            prefix = "".join(p[0] for p in parts[:4])
            # Must be at least 2 chars. With one part there is no second part to
            # borrow from, so take more of that part rather than returning a
            # one-character prefix that main() then rejects the whole run over.
            if len(prefix) < 2:
                source = parts[1] if len(parts) > 1 else parts[0][1:]
                prefix = (prefix[:1] + source[:3]) or prefix
            # A one-letter name has nothing left to borrow. Double it rather than
            # return a length main() rejects the whole run over.
            if len(prefix) == 1:
                prefix = prefix * 2
            return prefix[:4]

    # ── Single-word name ──
    # First: try word-boundary detection for obvious compounds like vibecodereview
    # Check if it's a vibe* repo (the most common compound pattern)
    if name_lower.startswith("vibe") and name_lower != "vibe":
        suffix = name_lower[4:]  # strip "vibe"
        suffix_words = split_camel_lower(suffix)
        # v + first letter of each suffix word
        return ("v" + "".join(w[0] for w in suffix_words))[:4]

    # Default: first 3 letters
    prefix = name_lower[:3]
    return prefix[:4]


def candidate_prefixes(repo: str):
    """Prefixes to try for a repo, most meaningful first.

    The old version only sliced the squashed name, so three repos sharing a long
    stem (vibenotebooks, vibenotepad, vibenoteworthy all squash to vibenote...)
    produced the same candidate, ran out, and left a duplicate behind. main()
    then aborted the entire registry build over one unresolvable name.

    This always terminates with a free prefix while any remain, and the order is
    fixed, so the same repo set always produces the same registry.
    """
    seen: set[str] = set()

    def offer(value: str):
        value = "".join(c for c in value.lower() if c.isalpha())[:4]
        if 2 <= len(value) <= 4 and value not in seen:
            seen.add(value)
            return value
        return None

    name = repo.lower()
    squashed = re.sub(r"[^a-z]", "", name)
    parts = [p for p in re.split(r"[-_.\s]+", name) if p]
    initials = "".join(p[0] for p in parts)

    # Longest first: a 4-letter prefix carries more of the name than a 2-letter
    # one, so vibenotebooks should reach for "vibe" before it settles for "vi".
    ordered = []
    for length in (4, 3, 2):
        ordered.append(squashed[:length])
        ordered.append(initials[:length])
    # initials plus a growing tail of the last word keeps a compound name readable
    if len(parts) > 1:
        for length in range(1, 4):
            ordered.append(initials[:1] + parts[-1][:length])
    # deterministic exhaustion, so the resolver never simply gives up
    stem = (squashed[:3] or initials[:3] or "z")
    for length in (3, 2, 1):
        base = stem[:length]
        for letter in string.ascii_lowercase:
            ordered.append(base + letter)
            for second in string.ascii_lowercase:
                ordered.append(base + letter + second)

    for value in ordered:
        candidate = offer(value)
        if candidate:
            yield candidate


def resolve_collisions(prefixes: dict[str, str], fixed: set[str] = frozenset()) -> dict[str, str]:
    """Resolve prefix collisions by extending shorter prefixes.

    `fixed` names are already-registered prefixes and must never be
    reassigned. For each collision group, only the non-fixed (fresh)
    names extend, left-to-right, until unique, up to 4 chars max.
    """
    # Build reverse map: prefix → [repo names]
    by_prefix: dict[str, list[str]] = {}
    for repo, pref in prefixes.items():
        by_prefix.setdefault(pref, []).append(repo)

    result = dict(prefixes)

    for pref, repos in by_prefix.items():
        if len(repos) == 1:
            continue

        has_fixed = any(repo in fixed for repo in repos)
        # Sort the fresh repos alphabetically for deterministic extension.
        # Fixed (registered) repos never move, so they aren't in this list.
        fresh_sorted = sorted(repo for repo in repos if repo not in fixed)

        # A fixed repo already holds `pref`, so every fresh repo in this
        # group must move. Otherwise the first fresh repo (alphabetically)
        # keeps `pref`, matching the old all-fresh behavior.
        taken: set[str] = {pref} if has_fixed else set()

        for repo in fresh_sorted:
            current = result[repo]
            if current in taken or current in {result[r] for r in result if r != repo}:
                others = {result[r] for r in result if r != repo}
                for candidate in candidate_prefixes(repo):
                    if candidate not in taken and candidate not in others:
                        current = candidate
                        break
                else:
                    # candidate_prefixes only runs dry when every 2-to-4 letter
                    # prefix is taken, which needs ~475k repos. Failing loudly
                    # here beats returning a duplicate that aborts the whole
                    # registry build with an error naming the wrong cause.
                    print(f"ERROR: no free prefix for {repo}", file=sys.stderr)
                    sys.exit(1)
            result[repo] = current
            taken.add(current)

    return result


# ── Main ────────────────────────────────────────────────────────────────

def main():
    repos = gh_list()

    # Size is a poor proxy for whether a repo is real. A vibe* scaffold at
    # 8-9KB already has AGENTS.md, .agents/brand.md, .agents/design.md and
    # .github/workflows: it is a live repo with no product code yet. The old
    # floor (diskUsage >= 10, about 10KB) had no recorded reason. It left
    # those 41 scaffolds out of the registry, so rollout could not see them,
    # so the issue rollout that needs a prefix skipped them too. Each layer
    # is defensible alone; together the exclusion is permanent.
    #
    # gh_list() already fetches diskUsage, isArchived, isFork. It does not
    # fetch a commit count or isEmpty, and a new API field is not needed:
    # GitHub reports diskUsage 0 for a repo with no git objects (never
    # pushed). Anything above 0 has at least one commit and must register.
    # Do not put the 10KB number back.
    eligible = [
        r for r in repos
        if not r["isArchived"] and not r["isFork"] and r["diskUsage"] > 0
    ]

    # A prefix is permanent. Once a repo has one, branch names, PR titles and
    # merged commits carry it, so regenerating must never reassign it. Load what
    # is already registered and derive only for repos that have none.
    registry_path = Path(__file__).with_name("repo-prefixes.json")
    existing: dict[str, str] = {}
    if registry_path.exists():
        existing = json.loads(registry_path.read_text())

    # Keep every already-registered entry, even for a repo that fell out of
    # `eligible` (archived, renamed, deleted). Dropping it here would free its
    # prefix for reassignment, breaking the permanence guarantee above.
    prefixes: dict[str, str] = dict(existing)
    fresh: dict[str, str] = {}
    for repo in sorted(eligible, key=lambda r: r["name"]):
        name = repo["name"]
        if name not in existing:
            fresh[name] = derive_prefix(name)

    # Resolve collisions among the new names only, against everything already held.
    if fresh:
        merged = dict(prefixes)
        fixed = set(prefixes.keys())
        merged.update(fresh)
        resolved = resolve_collisions(merged, fixed=fixed)
        for name in fresh:
            prefixes[name] = resolved[name]

    # Validate
    values = list(prefixes.values())
    if len(values) != len(set(values)):
        dupes = {v for v in values if values.count(v) > 1}
        print(f"ERROR: duplicate prefixes detected: {dupes}", file=sys.stderr)
        sys.exit(1)

    for name, pref in prefixes.items():
        if not re.fullmatch(r"[a-z]{2,4}", pref):
            print(f"ERROR: invalid prefix '{pref}' for repo '{name}'", file=sys.stderr)
            sys.exit(1)

    # Self-test: edge-case names that the derivation must handle.
    # These test the one-character-prefix fix and non-alpha names. Run before
    # writing anything, so a broken derivation never overwrites the registry.
    edge_cases = {".github": "gith", "foo-": "foo", "123": "zz", "x": "xx",
                  "---": "zz", "a.b": "ab"}
    for ec_name, ec_expected in edge_cases.items():
        ec_result = derive_prefix(ec_name)
        if ec_result != ec_expected:
            print(f"ERROR: edge-case '{ec_name}' -> '{ec_result}', expected '{ec_expected}'", file=sys.stderr)
            sys.exit(1)

    # Write the registry ourselves, atomically. The old `> repo-prefixes.json`
    # usage truncated the file before this process even started, so the read
    # of `existing` above always saw an empty file. Writing to a temp file in
    # the same directory and renaming it into place means a crash mid-write
    # never leaves a half-written or empty registry behind.
    sorted_map = dict(sorted(prefixes.items()))
    tmp_path = registry_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(sorted_map, indent=2, ensure_ascii=False) + "\n")
    tmp_path.replace(registry_path)


if __name__ == "__main__":
    main()