# PR standards for an agent fleet

Agents generate pull requests faster than anyone reviews them. Generation costs
almost nothing now; review costs exactly what it always did. That gap is why a
fleet drifts, an agent opens a 20,000-line PR against no agreed scope, and the
only thing standing between it and `main` is your attention.

This document is the standard. `pr-standards` is the program that enforces it.
One engine, four layers: an agent hook, a git hook, a CI check, and a review lens.

## The rule

**One issue. One PR. One concern. Under 500 lines.**

Everything below is that sentence, made checkable.

### Branch name

    <prefix>-<issue>-<slug>

    cr-142-fix-onboarding-drop-off
    pt-7-add-safari-extension-build
    rts-91-retry-stripe-webhooks

| Part | Rule |
|---|---|
| `prefix` | 2–4 lowercase letters. One per repo, fixed. Read from repo config, then the bundled fleet registry, then derived from the repo name. |
| `issue` | A GitHub issue number that **exists and is open**. No issue, no branch. No `0`, and no leading zeros, so one issue has exactly one branch name. |
| `slug` | `[a-z0-9]+(-[a-z0-9]+)*`, 3–48 characters. Describes the change, not the file. |

Full pattern: `^[a-z]{2,4}-[1-9][0-9]*-[a-z0-9]+(-[a-z0-9]+)*$`

Exempt, never checked: `main`, `release`, `refactor`, `release/*`, `gh-pages`,
`dependabot/*`, `renovate/*`.

The issue number is the join key. It ties the branch, the title, the body, and
the merged commit to one agreed piece of work. When this fleet moves to Linear,
only the source of the number changes.

### PR title

    [CR-142] Fix onboarding drop-off on step three

- Tag is the uppercase prefix and the same issue number as the branch.
- Subject after the tag: imperative mood, 10–50 characters, no trailing period,
  starts with a capital letter.
- Rejected openers, because they are not imperative: `Added`, `Fixed`, `Updated`,
  `Removed`, `Changed`, `Refactored`, `Implemented`, and any `-ing` first word.
- No emoji. No conventional-commit prefix, the tag already carries the scope.

### PR description

Four things, all required:

    Closes #142

    ## What
    One to three sentences. What changed, in plain words.

    ## Why
    The problem from issue #142, and why this is the fix.

    ## How I verified
    bun test        -> 214 passed
    bun run build   -> clean
    Manually walked steps 1-4 of onboarding in staging.

    ## Review
    Reviewed-by: codex:gpt-6-astra
    Verdict: 0 major

    Assisted-by: claude-personal:claude-opus-5
    Assisted-by: pi:glm-5

- **Exactly one** closing reference, matching the branch issue. Two closing
  references means two concerns, which means two PRs.

  Count all nine keywords GitHub honours, not just the one in the example:
  `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves`,
  `resolved`. Each of them also works with a colon (`Closes: #10`) and in the
  cross-repo `owner/name#100` form. A checker that knows only `Closes #N` lets
  `Closes #1` plus `Fixes: #2` through, which is two concerns wearing one coat.
  A cross-repo reference counts toward the one-reference rule, because it is
  still a second thing the PR closes, but it can never satisfy the branch issue.
  A reference inside an HTML comment does not count, so an unedited template
  cannot trip it.
- `## How I verified` must name a command and its result. `N/A`, `TODO`, `tested
  locally`, and an unedited template comment all fail. A change with no visible
  surface to click through or screenshot still needs a command and its result;
  add `Proof: n/a — <reason>` alongside it to say why there is nothing further
  to show. The reason is not optional, and the hatch never waives the command
  and its result — only the extra, visible proof. A before/after `git ls-files`
  count, or a `(none tracked)` guard, is a result for a change whose whole
  effect is on the git index.
- Body under 120 characters fails. A description that only restates the diff is
  not a description.
- The body must contain an `Assisted-by: <agent>:<model>` line. It discloses which
  fleet member wrote the change. The Linux kernel uses this convention for the same
  reason: so you can tell, later, which agent produced which class of defect.
  Convention puts it last. The check accepts it anywhere in the body rather than
  pretending to enforce a position it does not.

  One trailer per line. Repeat the line for each contributor. Most work here has
  two or more contributors, so two lines is the normal shape:

      Assisted-by: muse:meta-code
      Assisted-by: claude-personal-1:claude-opus-5

  A comma-separated list on one line fails the check. The checker names the line
  it finds, so the failure is not a false "missing".

  Both fields must be non-empty tokens with no internal whitespace, no backticks,
  and no comma. The agent field must not contain a slash — `owner/repo:thing` is
  a repository path, not a fleet member.
- `## Review` is the proof that a second model read the diff. The council no
  longer runs on pull requests. The author runs that review on the same boat
  box, in a fresh process, with a model that did not write the change, and
  pastes two lines:

      ## Review
      Reviewed-by: codex:gpt-6-astra
      Verdict: 0 major

  `Reviewed-by` uses the same `<agent>:<model>` shape as `Assisted-by`. The
  model, the part after the colon, has to be a different model from every
  `Assisted-by` line. A new agent name in front of the same model still fails.
  A verdict of `N/A`, `TODO`, or `TBD` fails.
  `Verdict: 1 major` is fine when the findings are written under it: the check
  proves the review ran, it does not demand a clean one.

  The same two lines in a pull request comment count, so the review can live
  on the conversation instead of the description. An HTML comment does not
  count. An unedited template fails.

#### Proof of work

`## How I verified` must also carry proof that the change worked, not just the
name of a command. An agent can write "tested locally" for free; a screenshot
or a real command output costs work, so it is the part worth checking.

| Work class | Proof |
|---|---|
| UI (a user can see it) | before and after screenshots, or a short video of the flow |
| Backend, API, CLI | the command and its real output |
| Bug fix | the test failing before, passing after |
| Performance | the numbers before and after |
| Infrastructure, CI | a link to the green run |
| Copy, docs, marketing | a screenshot of the rendered page, or the preview URL |

Media goes to GitHub user-attachments. Media never goes into a commit. A commit
carries the change; the pull request carries the evidence.

The checker enforces only what it can cheaply and mechanically:

- **UI diff needs an attachment.** If any changed file matches `uiGlobs` and is not
  excluded by `uiExcludeGlobs`, the body must contain at least one
  `https://github.com/user-attachments/assets/<id>` URL. Zero attachments and no
  `Proof: n/a` line fails; exactly one attachment warns ("a visual change wants
  before and after"); two or more passes. For a diff with no UI files, the
  existing command-and-result rule already stands and no attachments are required.
- **The `Proof: n/a` hatch does not clear a UI diff.** The hatch says nothing
  visible changed, and whether anything visible changed is the half of that
  claim the checker settles on its own. When a changed file matches `uiGlobs`,
  the hatch is refused and the refusal names the files that contradict it. The
  hatch keeps working for a diff with no visual surface, which is the case it
  was written for. It is only refused when it is doing the waiving: a body that
  carries before and after media as well as a hatch line has done the work and
  passes.
- **Committed proof media fails.** A file added by the diff whose extension is
  `png`, `jpg`, `jpeg`, `gif`, `webp`, `mp4`, `mov`, or `webm` and whose path
  matches `screenshot*/**`, `**/screenshots/**`, `proof*/**`, `**/*before*`,
  `**/*after*`, `**/*demo-recording*`, or sits in the repo root is rejected: it
  belongs in user-attachments. A screenshot committed to a repo stays in its
  history forever, for a picture nobody opens twice. Media anywhere else (`public/**`, `**/assets/**`, and every other path) is a real
  asset and is not flagged.
- **No label clears it.** There is no `proof-not-applicable`. The size cap's
  override label was removed for the reason that an agent can apply its own
  label, and a proof requirement an agent can waive is not a requirement.
- `requireProof: false` turns off both proof checks for a repo with no
  user-facing surface. That is a config decision: it lives in the repo, it shows
  up in a diff, and it is reviewed like any other change.
- **Proof has to be attributable, not merely present.** `bun test -> 214
  passed` reads the same whether or not it ran, and nothing mechanical can tell
  the two apart from text alone. What the checker can tell is whether the claim
  points to something it did not write itself: a linked Actions run, a
  user-attachments URL, or a `Proof: n/a` reason. None of those present is a
  warning, not a failure — most repos in the fleet do not yet run their own
  tests in CI, and failing every PR whose proof lives only in prose would turn
  the whole fleet red on day one. Set `requireAttributableProof: true` once a
  repo's own tests run in CI, so this becomes a failure instead of a warning.
  Silent when the UI attachment check above already failed on the same diff —
  that failure already names the missing capture. `requireProof: false` turns
  this off too.

Escape hatch, when proof truly does not apply:

    Proof: n/a — <reason, at least 20 characters>

The checker accepts it on a diff with no UI files and refuses it on a diff with
them; the review council judges the reasons the checker cannot read. An agent
cannot clear its own proof requirement with "not applicable", and it cannot
clear a visible change by asserting the change is not visible.

How an agent captures and uploads proof:

```bash
curl -sS -X POST \
  "https://uploads.github.com/user-attachments/assets?name=<file>&content_type=<mime>&repository_id=$(gh api repos/<owner>/<repo> --jq .id)" \
  -H "Authorization: Bearer $GITHUB_ATTACHMENTS_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: <mime>" \
  --data-binary @<file>
```

- If `GITHUB_ATTACHMENTS_TOKEN` is unset, skip the upload and say so in the body.
  Do not commit the file as a fallback.
- Images embed as `![alt](url)`. A video goes on its own line as a bare URL.
- Supported types: `image/png`, `image/jpeg`, `image/gif`, `image/webp`, `video/mp4`.
  Convert first when needed: `ffmpeg -i in.webm -c:v libx264 -pix_fmt yuv420p out.mp4`
- Capture during reproduction and again during verification, so before and after
  come from the same run.
- When a later push changes the UI on screen, recapture and replace the embed.
  Keep every embed that is still accurate; never drop one while rewriting a body.
### Commits

No commit carries an AI attribution trailer. Not `Co-Authored-By: Claude`, not
`Co-authored-by: Codex`, not `Generated with [Claude Code]`, and the same for
Gemini, Kimi, Muse, pi, Copilot, Cursor and the rest. The commits should read as
the author's own work, because that is what they are: a person decided what to
build, reviewed it, and is answerable for it.

Two deliberate exceptions:

- `Co-authored-by: vibecodereview` stays. That is the review bot recording a fix
  it actually made, which is a real author rather than a model taking credit.
- `Assisted-by: <agent>:<model>` in the pull request **body** is required, not
  banned. Disclosure of which fleet member produced a change is the thing that
  lets you tell later which one keeps producing defects. Credit in every commit
  message is not: an `Assisted-by` trailer in a commit fails the check no
  matter which agent it names, because the commit is the wrong place for it
  regardless.

The banned list is `bannedCommitTrailers` in the config, so a repo can add an
agent without editing the checker.

This applies to new pull requests. Existing history is left alone: rewriting it
would change every commit id in eight active repos to remove a cosmetic line.

### Size and atomicity

| Cap | Limit | On breach |
|---|---|---|
| Net counted lines (`+` and `-`) | more than **500** | fail |
| Counted files changed | more than **40** | fail |
| Empty diff (0 counted files and 0 counted lines) | exactly zero | fail |
| Closing issue references | not exactly **1** | fail |
| Top-level directories touched | more than 3 | warn |

The boundaries are inclusive: 500 counted lines passes, 501 fails. "Under 500" in
prose and a bare `500` in a table are not the same rule, so the table is the rule.

Not counted, an agent should never be penalised for a lockfile it did not write:

    **/*.lock  package-lock.json  bun.lockb  pnpm-lock.yaml  yarn.lock  Cargo.lock
    dist/**  build/**  .next/**  out/**  vendor/**  **/generated/**
    **/__snapshots__/**  **/*.snap  **/*.generated.*  **/migrations/**
    **/*.min.js  **/*.map
    **/*.{svg,png,jpg,jpeg,gif,webp,ico,woff,woff2,ttf,otf,mp4,pdf,zip}

**500 is a design constraint, not a nuisance.** It is roughly one reviewable
sitting. An agent that must stay under it decomposes the work before it writes,
which is the behaviour we actually want.

**The cap has no escape.** There was one — an owner-applied `oversized-approved`
label — and it is gone. Every escape from a design constraint becomes the path:
an agent told it may ask for a label asks for the label instead of decomposing
the work, which is the one thing the cap exists to force. A change that seems
unsplittable almost always splits once you accept that it has to.

One escape remains, and it is deliberately awkward: a person merges past a red
check. That takes an act by a human on a named pull request. It cannot be
requested in a body, and it leaves a record.

**A release promotion does not pay the line cap or the file cap twice.** A pull
request whose head is the repository's own default branch, in the same
repository, aimed at any other branch, skips the line cap and the file cap. Its
diff is every pull request merged since the last promotion, added together, and
each of those already passed both caps. The empty-diff check, the directory
warning and the commit rule still apply. So does the branch rule, on the same
terms as any other pull request: the common case, a default branch already on
the exempt list above (`main`), was never checked for title, body or proof
either, promotion or not; a repository whose default branch is not on that list
still owes a real title and body. This is not a request an author can make: the
checker reads the head and base refs from GitHub, and the run prints a `WARN
release promotion: size cap not applied` line and a `WARN release promotion:
file cap not applied` line, each with the number it would have failed on.

**So open a promotion from the default branch itself:** `gh pr create --base
release --head main`. Cutting a named branch off `release`, merging `main` into
it and aiming that at `release` promotes the same commits, but it is not a
promotion by this test and does not get the exemption. The test cannot use the
commits, because a branch-shaped promotion is a shape an author can build, and
a merge commit can carry hand-written conflict resolutions that nobody reviewed.
Where the head ref points is not a shape anyone can build: reaching the default
branch already costs a pull request each time.

**Atomic means one concern.** The mechanical proxies above catch the obvious
cases. Whether a PR really does one thing is a judgement, and that judgement
belongs to the review council, see the scope lens in `vibecodereview`.

## What makes an issue dispatchable

The standard says: no issue, no branch. That makes the issue the unit of work,
which makes its text the thing that decides whether anyone else can do it.

Measured across this fleet's 145 open issues, **10 were implementable by a
delegate without guessing.** Not because the issues are bad — they are good
notes to someone who already knows the codebase. `private-repo-c4e6#1238` reads
"Add `reactToComment` + declare like capability": clear to its author,
underdetermined for anyone else. Which file? What signature? Which sibling
already does this correctly?

A delegate that has to guess will guess. Reviewing a guess costs more than
writing the spec would have, so **the spec is the bottleneck, not the
implementation.**

### Four things a delegate needs

| | Missing on |
|---|---|
| **A file or directory.** Not a concept: `apps/website/src/services/bluesky.ts`, not "the Bluesky service". | 40% |
| **A thing to copy.** Name the sibling that already does this right. This is the strongest instruction available to a weak model, and the one most often absent. | 92% |
| **A testable finish line.** "Under 15 seconds", "exit 1 on a malformed body". Never "faster", never "handles errors". | 84% |
| **A verification command**, by name, that a reader can run. | 77% |

### Two more when a human has to choose

The four above let someone *check* the work. They do not let someone *decide*
it. When the issue asks for a judgement rather than a correction, it needs
something to judge.

- **A flowchart**, when the change is a decision tree: a routing rule, a
  failover chain, a gate with more than two outcomes. Prose describing a branch
  is where a reviewer stops reading and starts assuming, and the assumption is
  what ships.
- **Something to look at**, when the change is visible: a screenshot, an HTML
  prototype, or a Worker Preview URL. Nobody can judge a layout from a
  paragraph. Asking them to is how a design decision gets made by whoever wrote
  the paragraph.

A rough prototype from a cheap model beats a careful description, because it can
be rejected in five seconds. That is the point of a prototype: it is cheap to
throw away, and prose is not — prose gets argued with.

### Score before dispatching

    ./spec-audit                      # every open issue in the fleet
    ./spec-audit --repo private-repo-c4e6
    ./spec-audit --ready              # only the dispatchable ones

It prints what each issue is missing. Run it before a dispatch round, so the
gap shows up as a missing line in a spec rather than as a bad diff.

## Configuration

Each repo may carry `.github/pr-standards.json`. The rollout writes it, and the
checker uses its prefix first. Without that prefix, the checker reads the
bundled `repo-prefixes.json` registry, then derives a prefix for a new repo.

**The file states what the repo decides, and nothing else.** A fresh rollout
decides one thing:

```json
{
  "prefix": "cr"
}
```

Everything else stays at the default, in the checker, where fixing it once fixes
it for every repo. A copied default is not a no-op: the file is merged over the
defaults, so a repo that restates all of them is pinned to the values of the day
it was rolled out and a later fix never reaches it. That is the opposite of what
one central checker is for, and it is what the moving `pr-standards-v1` tag exists
to avoid.

Add a key only to record a decision that differs, and the diff then says what the
repo chose:

```json
{
  "prefix": "cr",
  "maxLines": 900,
  "maxBaseCommitsBehind": 20,
  "allowChoreEscape": true
}
```

`maxBaseCommitsBehind` defaults to 10. Above that limit, the checker names the
base commits that arrived after the branch point. It warns for independent
files and fails when the base and pull request change the same file.

The full set of keys and their defaults is `DEFAULT_CONFIG` in `pr-standards.mjs`.

`allowChoreEscape` is off. Turn it on and a `chore/<slug>` branch skips the issue
requirement, which helps if dependency bumps and CI fixes start costing more in
issue bookkeeping than they save. It is a knob so the decision stays visible.

**It skips the issue requirement and nothing else.** A chore branch still has to
satisfy every title and body rule: imperative subject, the four sections, the
minimum length, the `Assisted-by` line, and the review proof. It must also carry no closing reference,
because a change that closes an issue is not a chore and belongs on a numbered
branch. The obvious implementation gets this wrong. Written as "there is no issue
number, so skip the checks that need one", the knob quietly disables the title and
body rules too, and becomes a way to opt out of the whole standard.

## Generated file drift

A hand-edit to a generated file is a defect, not a shortcut. The edit reads
correctly in review, and from then on the file disagrees with its generator: the
next regeneration either reverts the change or keeps it and drifts further.
Reading the diff cannot catch this. Running the generator can.

The `generated-drift` workflow runs each command in `generators` on every pull
request, then fails when `git status --porcelain` reports anything. The log
carries the offending paths and `git diff --stat`, and the job leaves one comment
naming the drifted files. It updates that comment on re-runs rather than posting
a second one.

Two keys in `.github/pr-standards.json` configure it:

- `generators` — shell commands, in order, for example
  `["bun run db:generate", "bun run build:types"]`. Absent or empty means the job
  skips and passes, so a repo with no generators stays green.
- `generatorSetup` — one optional command that runs first, for example
  `bun install --frozen-lockfile`.

`pr-standards-templates/generated-drift.test.sh` runs the embedded check against a
throwaway git repo. It exists because the first version read its config through an
unexported shell variable: every lookup raised, every raise was swallowed, and the
job passed on every repo without running a generator. A check that silently never
runs is worse than no check, because its green tick is a lie.

Install it with `pr-standards-rollout --with-generated-drift`.

## The four layers

Local layers exist for speed. CI is the authority. Neither replaces the other.

| Layer | Runs | Catches | Bypassable |
|---|---|---|---|
| Claude Code `PreToolUse` hook | at tool-call time | a bad branch before it exists | by another agent |
| `pre-push` git hook | before the push | a bad branch before GitHub sees it | `--no-verify` |
| `pr-standards.yml` in CI | on every PR | everything, including size and body | only by ignoring red |
| `vibecodereview` scope lens | on every PR | non-atomic and off-scope work | by ignoring the review |

The table describes what each layer catches once installed. A layer not rolled
out to a repo catches nothing there, so read it as the design rather than as the
state of any particular repo.

There is a fifth layer, and whether you can have it depends on plan AND
visibility, not plan alone:

| Repo | Rulesets and required checks on GitHub Free |
|---|---|
| Public | Available |
| Private, personal account | Needs GitHub Pro |
| Private, organization | Needs GitHub Team or Enterprise |

So on this account the public repos can be gated and the private ones cannot.
Where nothing can be required, red CI is a signal rather than a gate, and the
local layers carry more weight, though `--no-verify` still skips the git hook.
They are early feedback, not a boundary.

Caution: do not add `pr-standards` as a required status check on a repo before
the workflow is installed there. Requiring a check the repo never runs blocks
every pull request in that repo, permanently.

## The two local layers

CI is the authority, but it is also the slowest feedback. Two local layers catch a
bad branch before GitHub ever sees it. Neither is a boundary — `--no-verify` skips
the git hook, and another agent's harness never loaded the Claude Code hook — so
treat them as early feedback, not enforcement.

- `install-pr-hooks --apply` puts the `pre-push` hook in every eligible checkout.
- `hooks/pr-standards-guard.sh` is the Claude Code `PreToolUse` hook, and the
  earliest feedback available: it rejects a branch name before the branch exists.
  Register it in `.claude/settings.json` under `hooks.PreToolUse` with matcher
  `Bash`:

  ```json
  { "type": "command", "command": "<path>/hooks/pr-standards-guard.sh" }
  ```

  It checks only branch *creation*. Deleting or renaming a branch is how you
  recover from a bad name, so guarding those would trap you in one. It lets a call
  through whenever it cannot parse its own input, because blocking on its own bug
  is worse than the branch name it guards against.

To install the standard itself in a repo — the config, the PR template and the
workflow — use `pr-standards-rollout`.

## VISION.md

The checker asks whether a pull request is one thing. The review council asks
whether it is well built. Neither can ask whether the change belongs in this repo
at all, because nothing in the repo says what the repo is for. A change can pass
every check, do exactly one thing, carry real proof, and still be the wrong change.

`VISION.md` at the repo root closes that gap. The council reads it when the repo
has one. `pr-standards-templates/VISION.md` is the template.

Six sections, and only one of them does the work:

| Section | What it answers |
|---|---|
| What this is | The repo in a user's words |
| Who it is for | One named reader, never "everyone" |
| What good looks like | Three to five observable outcomes |
| **Explicitly not this** | **Three to five changes that would be well built and still wrong here** |
| How it pays for itself | The business model, or whose time it saves |
| The current bet | One sentence with a date |

Write "Explicitly not this" last, and write it from requests you have already
turned down. Every other section tells a reviewer what to accept. Only that one
tells it what to reject, and a vision that rejects nothing changes no review.

The council must actually read it. Every code repo's `vibecodereview.yml` skips
markdown, for a good reason — a README typo does not need a five-model council —
and that skip covered `VISION.md` too. So the one file the council consults to
judge every other pull request was the one file it never reviewed, and a docs-only
vision could never be approved. Re-include it with an ordered `paths` filter — `!` exclusions work with `paths`
and not with `paths-ignore`, so the negated `paths-ignore` form looks right and
still skips the file:

```yaml
paths:
  - "**"
  - "!**.md"
  - "!docs/**"
  - "VISION.md"
```

Two failures to avoid:

- **A template left as prompts.** The council judges against whatever text is
  there. Placeholder prose reads as a vision that permits everything, which is
  worse than no file, because the absent file at least makes the council fall
  back on the diff and the issue.
- **A stale bet.** "The current bet" carries a date so drift is visible. A repo
  whose bet has not moved in a year is either finished or abandoned, and the
  vision should say which.

## Post-merge verify

Merged is not live. CI proves the change is good on a runner. This job proves
the change reached production. It runs on every `push` and on
`workflow_dispatch`, but the job itself skips unless the push landed on the
repo's actual default branch — not every repo in the fleet defaults to `main`.
It uses `boat` for private repos and `ubuntu-latest` for public repos.
The concurrency group includes the repo and ref.

Add `postMergeVerify` to `.github/pr-standards.json` to enable it:

```json
{
  "postMergeVerify": {
    "url": "https://example.com",
    "shaPath": "/api/version",
    "shaJsonKey": "sha",
    "timeoutSeconds": 900
  }
}
```

- `url` — the live URL. The job requests it and requires a 2xx.
- `shaPath` — path appended to `url` to poll for the live SHA. When absent,
  the job skips the poll step.
- `shaJsonKey` — JSON key that holds the SHA in the version response. Default
  is `sha`.
- `timeoutSeconds` — how long to poll before the job fails. Default is `900`,
  capped at `1000` regardless of the configured value so the check always
  fails through its own logic before the job's 20-minute timeout cancels it
  out from under the reporting step.

When `postMergeVerify` is absent, every step is skipped and the job passes. A
repo that does not deploy stays green. Malformed JSON in `pr-standards.json`
is not treated as absent — the job fails so a broken config is never silently
green.

When the job fails, it opens an issue titled `Deploy did not go live: <short sha>`
with the failing step, the expected SHA, what the endpoint returned, and a link
to the run. When an open issue with that title prefix already exists, the job
comments on that issue instead of opening a new one.

Install the workflow with `pr-standards-rollout --with-post-merge-verify`. The
flag is opt-in because most repos in the fleet do not deploy.

`pr-standards-templates/post-merge-verify.test.sh` runs the check the workflow
embeds against a local server. It pins the two cases that decide whether the job
is worth having: a repo with no config stays green, and a SHA that never appears
goes red.

## Usage

```bash
pr-standards branch                      # validate the current branch name
pr-standards branch cr-142-fix-onboard   # validate a specific name
pr-standards precheck --branch X --title Y   # for the agent hook; no network
pr-standards pr --repo itsryanarmani/private-repo-c4e6 --number 88
pr-standards pr --repo itsryanarmani/private-repo-c4e6 --number 88 --json   # machine-readable
pr-standards drift                       # check the managed AGENTS.md block and PR template for drift
```

Exit 0 clean, exit 1 on any failure, exit 2 on a configuration problem.
Warnings never change the exit code.

## Boat runners

Private repos use `boat`. Use `boat-8` for jobs that need 8 vCPU and 16 GB.
Public repos use free GitHub-hosted runners. A self-hosted runner in a public
repo can run code from fork PRs. The templates select the runner from the
repository visibility.

Boat JIT runners get only the labels passed. Use `runs-on: boat` or
`runs-on: boat-8`; do not require `self-hosted`. Copy this config to
`.github/actionlint.yaml` when you install a workflow template:

```yaml
self-hosted-runner: { labels: [boat, boat-8] }
```

The pool keeps Boxes on, with one JIT runner per Box at a time. It keeps
`~/.bun`, Playwright browsers, and Docker images warm between jobs. A
Cloudflare Worker broker takes `workflow_job` webhooks and hands out JIT
configs. The GitHub token stays off the Box. Pool code is in
`workers/boat-runners/`, `boat-runner-agent`, and `boat-pool` in scripts
(#508 and #509, in progress).

Boxes run Ubuntu 24.04 with passwordless sudo, Docker 29, Node 24, and Bun.
The default Box has 4 vCPU and 8 GB at $0.036/h. A small Box has 2 vCPU and
4 GB at half that rate. A large Box has 8 vCPU and 16 GB at $0.072/h.
$1 buys 100,000 Box-seconds at the default rate. Always-on Boxes bill while
idle too. For comparison, Ubicloud standard-2 costs $0.075/h, standard-4
costs $0.15/h, and standard-8 costs $0.30/h (2026-10-11).

`ci-runner-audit itsryanarmani` reports the `boat` tier and flags legacy
Ubicloud labels. `ci-pr-latency` groups Boat job time under `boat` and keeps
the `cloud` tier for comparison with old Ubicloud runs.
