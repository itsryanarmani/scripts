# AGENTS.md

Repository identity and interface rules live in
[`.agents/brand.md`](.agents/brand.md) and
[`.agents/design.md`](.agents/design.md).

## CI runners

This repo is public, so every job runs on GitHub-hosted `ubuntu-latest`.
Public repos get those runners for free. Do not use Boat for public repos:
a self-hosted runner can run code from fork PRs.
Private `itsryanarmani/*` repos use `boat`, or `boat-8` for larger jobs.
JIT runners get only the labels passed. Do not add `self-hosted` to `runs-on`.
Declare `boat` and `boat-8` in `.github/actionlint.yaml`:

```yaml
self-hosted-runner: { labels: [boat, boat-8] }
```

<!-- pr-standards:start -->

## Pull requests

One issue. One PR. One concern. Under 500 counted lines.

Open the issue first. No issue, no branch. The issue number ties the branch, the
title, the body and the merged commit to one agreed piece of work.

```text
branch:  scr-<issue>-<slug>          scr-142-fix-onboarding-drop-off
title:   [SCR-<issue>] <Subject>   [SCR-142] Fix onboarding drop-off
body:    Closes #142
         ## What / ## Why / ## How I verified
         Assisted-by: <agent>:<model>
         Assisted-by: <agent>:<model>
```

One `Assisted-by: <agent>:<model>` line per contributor. Repeat the line for
each contributor. A comma-separated list on one line fails the check.

Subject line: imperative mood, 10-50 characters, no trailing period, no emoji.
Write "Fix the drop-off", not "Fixed the drop-off".

Hard caps, failed by the `pr-standards` CI check: 500 counted lines, 40 counted
files, exactly one `Closes #`. Lockfiles, build output, snapshots, generated
code and migrations are not counted. There is no label that clears the cap and
no one to ask for one. Split the change.

Settings for this repo are in `.github/pr-standards.json`. The standard is at
https://github.com/itsryanarmani/scripts/blob/main/pr-standards.md

## Merge gates

Run the repo `ci:local` script before every `git push` when it exists.
Else run the same lint, typecheck, and unit tests CI runs.
Do not push a red local gate. Do not use CI as the test runner.

For a change a user can see, or that talks to a third party, walk the
Cloudflare Worker Preview before merge. Quote the Preview URL and status
codes. A 2xx on the site home is not that walk.

Wait for one LLM review APPROVED. Red CI blocks merge even when GitHub
does not require checks.

## Agent presence

Before you cut a branch:

```
bin/fleet-presence claim itsryanarmani/<repo> <N> --goal "..." --branch <branch>
```

One sticky GitHub comment per agent. Create once, then PATCH. Same-machine
lock is local. Name harness, model, host, start time, and goal. Do not dump
transcripts. Full rule: itsryanarmani/private-repo-b1e6 `rules/fleet-claim.md`.

<!-- pr-standards:end -->

<!-- cursor-cloud:start -->

## Cloud agents (Cursor)

This repo runs on [Cursor Cloud Agents](https://cursor.com/docs/cloud-agent). Local
`.env.local` does **not** sync — mirror keys in **Dashboard → Cloud Agents → Secrets**.

| Secret type | Use for |
|---|---|
| Runtime Secret | API keys, passwords (hidden from chat/commits) |
| Environment Variable | Non-sensitive config (URLs, flags) |
| Build Secret | Private npm/docker registries during install only |

### Install & test

Install command lives in `.cursor/environment.json`. After dashboard setup:

1. **Environments** → link this repo → wait for **Build = Success**
2. **Secrets** → copy every key from your local `.env.local` / `.env.example`
3. Run the project's test/lint command before opening a PR (see below)

### Verify before PR

```bash
export PATH="$PATH:$PWD" && node --test pr-standards.test.mjs assisted-by.test.mjs && ./hooks/pr-standards-guard.test.sh && python3 build-repo-prefixes.test.py && python3 worker-preview-provision.test.py && python3 worker-preview-access.test.py && python3 install-pr-hooks.test.py && ./adopt-branch-pattern.test.sh && ./pr-standards-rollout-labels.test.sh && ./fleet-ci-census.test.sh && ./append-point-scan.test.sh && ./merge-hotspots.test.sh
```

### Pull requests

Follow the fleet PR standard in this repo's `AGENTS.md` (`<!-- pr-standards:start -->` block).
Cloud agents need push access via Git integration and a successful environment Build.

Setup guide: https://github.com/itsryanarmani/scripts/blob/main/cursor-cloud-rollout.md

<!-- cursor-cloud:end -->

## Public naming boundary

This repo is public. Do not name a private repository in any file, issue, PR
or comment. Use a generic phrase such as "the fleet template repository", or an
example name such as `example-repo`. Keep private names and inventories in a
private repository.
