# mine-confirmed-defects

Walk merged pull requests and emit `confirmed-defects.json` for the council
eval. Every label cites later evidence that is independent of the council.

```bash
./mine-confirmed-defects itsryanarmani/vibecodereview
./mine-confirmed-defects --out confirmed-defects.json
./mine-confirmed-defects --validate confirmed-defects.json
```

A later change is evidence only when it deletes a line the PR added.
`vibecodereview[bot]` and any other bot are dropped. "fix: address review"
is dropped even when a human wrote it.

| kind | meaning |
|---|---|
| `revert` | a later non-bot revert of that PR |
| `later-fix-commit` | a later non-bot fix PR that deletes a line the original added |
| `linked-fix-issue` | a later PR closes an issue that says the original PR caused the bug |
| `in-pr-correction` | the human author pushed a `fix`/`correct`/`undo`/`revert` commit before merge |

Lens: first keyword in the evidence summary, then the path; otherwise
`correctness`. Security: auth, token, secret, oauth, permission, credential,
injection, xss, csrf, privilege, password. Performance: timeout, leak,
latency, slow, memory, cache, n+1, overhead, cpu. Scope: out of scope,
unrelated, extra, drive-by, shouldn't. Maintainability: lint, rename, dead
code, duplicate, complexity, format.

Repos, cases, and defects are sorted. If more than `--max` cases survive,
the pick is round-robin across repos. Re-running writes the same bytes.
The tool does not invent cases to reach 50.
