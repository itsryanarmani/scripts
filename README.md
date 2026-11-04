# scripts

Automation scripts that run my agent ops.

## Part of my AI workspace

The [`agents`](https://github.com/pooriaarab/agents) repo is the hub — a portable `.agents` folder symlinked into every agent CLI.

| Repo | What |
|---|---|
| [agents](https://github.com/pooriaarab/agents) | The hub — portable `.agents` workspace |
| [skills](https://github.com/pooriaarab/skills) | Reusable agent skills |
| [clis](https://github.com/pooriaarab/clis) | Working CLIs for ad-platform APIs |
| [commands](https://github.com/pooriaarab/commands) | Slash commands and shortcuts |
| [scripts](https://github.com/pooriaarab/scripts) | Automation scripts |
| [prompts](https://github.com/pooriaarab/prompts) | Refined prompts |

## CI cost controls

[Reduce CI cost without blocking delivery](ci-cost-controls.md) covers local
proof, production checks, runner placement, safe pool drains, and billing evidence.

## fleet-ci-census

Fleet CI wall-time census. `./fleet-ci-census --help`.

## black-october-audit

Read-only host audit for one Mac. It checks system Chrome, Electron app versions
against patched floors, cached Chromium builds, open ports, macOS protections, secret
file modes and outdated tools. It exits 1 when a check fails. Use `--json FILE` for a
report with no secret values. Steps and fixes:
[`black-october-hardening`](https://github.com/pooriaarab/skills/blob/main/black-october-hardening/SKILL.md).

```bash
./black-october-audit --json /tmp/black-october.json
```

## Diagnose CI in this order

The four `ci-*` scripts are one workflow, not four tools. Run them in order. Each step
stops you from optimising a job that does not matter.

| Step | Script | Question it answers |
|---|---|---|
| 1 | `ci-pr-latency` | Which number is bad — the wall clock you wait for, or the machine seconds you pay for? They move independently, so never report one CI number. |
| 2 | `ci-job-timings` | Which jobs take longest? Trace dependencies and waits separately to find the complete critical path. |
| 3 | `ci-cache-health` | Do the caches actually hit? A cache that restores nothing still prints a green success line, and a disabled remote cache prints one grey line. |
| 4 | `ci-runner-audit` | Is each job on a tier that can run it? Flags `services:` and `actions/cache` misuse on self-hosted runners. |
| 0 | `ci-baseline` | Where do the jobs come from? Counts billed jobs, median wait and median run per workflow and event from the API. Run it before and after a CI change over equal windows. |

Use the [CI optimization playbook](ci-optimization-playbook.md) for changes after diagnosis.

Only optimise after step 4. The reasoning behind the order, and the checklist of defects
that hide behind a green check, are in the
[`ci-speed-diagnosis`](https://github.com/pooriaarab/skills/blob/main/ci-speed-diagnosis/SKILL.md)
skill.

```bash
./ci-pr-latency   owner/repo
./ci-job-timings  owner/repo
./ci-cache-health owner/repo --limit 12
./ci-runner-audit owner
```

For releases, use [Measure release CI changes](ci-release-evidence.md) to compare full delivery intervals, shared runner demand, and failure costs.

For web changes, use [Measure web performance changes](web-performance-evidence.md) to check fonts, caching, payloads, and server work.

## Other scripts

Not part of the diagnosis order above.

| Script | What |
|---|---|
| `claude-token-rotate` | Rotate a Claude OAuth token into every repo that runs the review action. Reads the token from a hidden prompt, never an argument, because an argument lands in shell history and the process list. |
| `claude-subs-resync` | Re-sync live Claude Code OAuth sessions from the macOS Keychain (per-`CLAUDE_CONFIG_DIR` entries) into private-repo-4944 secrets, CodexBar and the `.secrets` env file; clears stale usage-poll backoffs that pin accounts to `unknown`. Account map is local (`claude-subs-accounts.example.json` shows the shape). `--check` is read-only. |
| `cliproxy-hub` | Run the CLIProxyAPI hub on the home Mac and wire every other host to it. `check` shows listen, bind, tailnet, sleep and per-seat health (a dead login still lists models, so it reads the management API). `serve` exposes the hub on the tailnet. `client claude\|codex\|pi` writes Claude Code, Codex or pi config on another host, with a backup. `verify` tests reach from a client. Never prints a key. |
| `boat-hub` | Boat boxes that already reach the CLIProxyAPI hub. `base` builds a `hub-ready` snapshot (Tailscale installed, not joined). `warm REPO...` saves a `<repo>-ready` snapshot from each repo's environment. `new REPO` makes a box that joins the tailnet and wires Claude Code, Codex and pi on first boot. Keys go in with `boat new --file`; the Tailscale key is shredded once the box joins, and the hub key stays in the box's client config. A snapshot holds no key. |
| `cc-cloud-env` + `cc-cloud-env-e2e` | Create, check, share and archive claude.ai/code cloud environments from a local spec (network level, variables, setup script). The dialog is the only interface, so it drives it through agent-browser. `cc-cloud-env apply <spec-root>`, `check`, `share`, `archive <name>`, `--session <name>`. The e2e script runs the whole lifecycle on one throwaway environment and prints a PASS or FAIL line per step. Keep the spec outside any repo. |
| `gbp-create` + `gbp-create-e2e` | Open Google Business Profiles for service-area businesses with no public address, from a JSON spec, through agent-browser. `gbp-create plan <spec>` checks the spec and opens no browser. `gbp-create create <spec> [name...]` fills every sign-up screen and picks Verify Later. It never enters an address, keeps a ledger so a rerun makes no duplicate, and `--stop-before-submit` stops one click before Google creates the profile. The e2e script checks the spec guards with no browser, and with `--session <name>` runs the flow up to that click. Keep the spec outside any repo. See the `local-business-profiles` skill. |
| `instinct-vault-fill` | Seed login entries into an Instinct vault via agent-browser: reads a local `entries.json`, drives the Add-login dialog with DOM-eval clicks (a11y-ref clicks drop silently on this app), retries until async-rendered fields exist, verifies each entry lands. Never logs secret values. |
| `install-pr-hooks` | Installs the `pr-standards` pre-push hook into local pooriaarab checkouts that have adopted `.github/pr-standards.json`. Dry-run by default; `--apply` writes, `--uninstall --apply` removes. See [pr-standards.md](pr-standards.md). |
| `fleet-digest` | One message a day that needs a person: owner-only label requests, failing default-branch CI, stale PRs and green PRs that wait for a human. Prints `Nothing needs you.` when empty. |
| `fleet-ci-census` | Per repo and workflow: run count, p50/p95 wall time, total minutes, failure and cancellation rates. JSON by default; `--markdown` ranks by total minutes. A run count at the page cap is a floor, not a total. See [fleet-ci-census.md](fleet-ci-census.md). |
| `append-point-scan` | Flag shared append points from repo contents alone: freshness gates, enumerated scripts, ordinal registries, committed junk. Answers what WILL conflict once a repo gets busy. `./append-point-scan <dir-or-owner/repo>`. |
| `merge-hotspots` | Rank files by share of recent commits and mark derived vs source. Churn is not contention: a busy file only serializes merges when several PRs touch it. `./merge-hotspots <dir-or-owner/repo>`. |
| `reviewer-venues/` | Dataset of 287 fee-free peer-review opportunities (CSV; JSON via the filter) with `filter_venues.py` to filter by region, field, venue type and application route. See [reviewer-venues/README.md](reviewer-venues/README.md). |

## Guides

- [Use Claude API credits safely](docs/claude-api-credits.md)

## Tests

`.github/workflows/tests.yml` runs every test in this repo on each pull request:
the checker's `node --test` suite, the PreToolUse guard, the prefix builder, the
hook installer, and the branch-pattern check. Each group runs even after an
earlier one fails, so one run names every failure rather than only the first.

Run them locally the same way:

```bash
node --test pr-standards.test.mjs
PATH="$PWD:$PATH" ./hooks/pr-standards-guard.test.sh
python3 build-repo-prefixes.test.py
python3 install-pr-hooks.test.py
./adopt-branch-pattern.test.sh
./pr-standards-rollout-labels.test.sh
./append-point-scan.test.sh
./merge-hotspots.test.sh
```

## spec-audit

Scores every open issue on whether a delegate could implement it without
guessing, and prints what each one is missing.

```bash
./spec-audit                      # every repo that adopted the standard
./spec-audit --repo private-repo-c4e6
./spec-audit --ready              # only the dispatchable ones
```

Four things a weak model cannot supply for itself: a file to change, an existing
thing to copy, a testable finish line, a named verification command. Measured
across this fleet's 145 open issues, 10 had three or more. The rule and the two
extra requirements for human-facing decisions are in
[pr-standards.md](pr-standards.md).

## pr-standards

Checks a branch or a pull request against the [PR standard](pr-standards.md): one
issue, one PR, one concern, under 500 counted lines. Run it before you push, and let
CI run it again on the PR.

```bash
./pr-standards branch                    # the current branch name
./pr-standards branch cr-142-fix-onboard # a specific name
./pr-standards precheck --branch X --title Y   # pattern only, no network
./pr-standards pr --repo pooriaarab/private-repo-c4e6 --number 88
./pr-standards pr --repo pooriaarab/private-repo-c4e6 --number 88 --json   # machine-readable
./pr-standards --selfcheck               # run the test suite
```

Exit 0 clean, 1 on a failure, 2 on a configuration problem. Warnings never change
the exit code.

Settings come from `.github/pr-standards.json` in the repo being checked. If that
file does not set a prefix, the checker reads the bundled `repo-prefixes.json`
registry. A repo absent from both sources gets a prefix derived from its name,
which it reads from `GITHUB_REPOSITORY` or the origin remote rather than the
directory name. A worktree is checked out to a directory you named, so the
basename is only the last resort.

Two files, not one. `pr-standards` is a launcher and `pr-standards.mjs` holds the
engine, which is also what the test suite imports. Anything fetching this checker
needs both.


## Other scripts

| Script | What |
|---|---|
| `box-reap` | Report what ascii.dev Boxes are costing and stop the unused ones. Never reaps on Box state, which lies |
| `box-guard` | Give every Box a deadline. `box new --no-auto-stop` leaves `archiveAfter: null` and nothing will ever stop it. Repairs state hourly with `box extend --ttl`; never stops anything |
| `iphone-wda` | Drive a USB iPhone through WebDriverAgent: `up` builds and starts it with the go-ios tunnel, then open, tree, tap, find, drag and shot. Never unlocks the phone |
| `private-repo-32ef` | Run the Phone Farm iOS stack (kevs-ios-agents): `up`, `down`, `status`, `register <udid>`, `run-now` and `stop`. Waits out a busy registration, sends `Origin` equal to `Host`, and removes a stale `ios forward 8100` (`iphone-wda up` leaves one). `--dry-run` prints the commands |
| `iphone-agent` | Send one named action to a local hidagent. Fractions are 0 to 1. The pointer stays visible |
| `box-reap-cron` + `com.pooriaarab.box-reap.plist` | Runs `box-reap` hourly under launchd. Installs to `~/.local/bin` because macOS TCC blocks a launchd agent from reading `~/Documents` |
| `gpu-vm` | Run local LLMs on a rented spot GPU VM on Google Cloud. `up` builds llama.cpp with CUDA, copies GGUF files and serves them on loopback. `tunnel` reaches them through IAP. `stop` and `down` end the billing. `--dry-run` prints every command |
| `turbo-remote-cache/` | Deployable Cloudflare Worker: a Turborepo remote cache backed by R2 |
| `box-setup/` | Provision the personal agent-CLI roster (claude x3, codex, gemini, kimi, pi, muse) inside an ascii.dev Box |
| `box-warm-shim` | Stand in for the `box` CLI so crabbox can start a Box from a named environment and a warm snapshot |
| `box-repo-audit` | Per-repo readiness for a warm Box: package manager, tracked files, gzipped tree size, secrets manifest, turbo creds, existing env and snapshot. `--tsv` for parsing |
| `box-session` | SessionStart/SessionEnd hook: warms a Box for the repo in the background when a session starts, stops it when the session ends. Opt-in per repo via `.crabbox-default-on` |
| `box-perf-check` + `box-perf-cron` + `com.pooriaarab.box-perf.plist` | Time the attach path and flag regressions against a baseline, weekly. Catches the silent 50x slowdowns |
| `box-work` | Start or reuse a Box that is ready to work on a repo, and run the work there instead of on the laptop. `box-work <repo>`, `--agent pi "brief"` (`--issue N` claims the issue first), `--ssh`, `--stop`, `--list`, `--stop-all` |
| `box-env-provision` | Give a repo a warm `box env`: repo auto-clone, the env files its `.crabbox-secrets` declares, `TURBO_*`, credentials capped. `--all --private-only` does the whole account |
| `box-git-sync.sh` | Runs inside a Box that already has the repo: fetches the commit the laptop is on instead of uploading a tree |
| `box-fast-attach` | Attach a worktree to a running Box in ~2s over `box host`, instead of ~84s through crabbox |
| `box-unpack.sh` | Runs inside a Box: unpacks the delta `box-fast-attach` sends and installs only when the lockfile moved |
| `agent-defect-rate` | Defect rate per `Assisted-by` agent: how often merged PRs get reverted or hot-fixed within the window. Shows the denominator next to every rate |
| `mine-confirmed-defects` | Mine independently confirmed PR defects (revert, later fix, linked issue, human in-PR correction). Bots are never evidence. See [mine-confirmed-defects.md](mine-confirmed-defects.md). |

## pr-standards-rollout

Enforce a standard branch name and PR title format across the account.
Every PR branch looks like `<prefix>-<issue>-<slug>`, and every PR title
starts with `[<PREFIX>-<ISSUE>]`. The prefix is 2-4 lowercase letters
mapped from the repo name in `repo-prefixes.json`.

Derivation rules: hyphen/underscore/dot separated names take the first
letter of each part (up to 4). Single-word names take the first 3 letters.
Names that are already an initialism are hand-picked. When two repos
collide on the same prefix, extend the shorter one until they differ.
Collision resolution is the whole point of the registry: every prefix
must be unique across the account.

| Script | What |
|---|---|
| `repo-prefixes.json` | Prefix registry. One entry per eligible repo. All unique. |
| `pr-standards-rollout` | Fan the standard out. Dry-run by default. `--apply` to write. |
| `pr-standards-templates/` | The four artifacts each repo gets: config, PR template, workflow, and the managed `AGENTS.md` block. |

```bash
./pr-standards-rollout                   # dry-run all repos
./pr-standards-rollout --repo <name>      # dry-run one repo
./pr-standards-rollout --repo <name> --apply  # write + PR
```

The rollout creates or reuses a GitHub issue per repo, then a branch and a PR.
Repos that are already configured are skipped.

## gh-app-read

Run read-only `gh` commands on a GitHub App installation token. Each App has its
own hourly budget, often 12,500 requests, so agent reads do not drain the owner
token. The wrapper rotates across the Apps you list and caches each token for 50
minutes in a file with mode 600. It refuses any command that may write.

```bash
export GH_READ_APPS="app-a app-b"
export GH_APP_TOKEN_CMD='<your-token-tool> token {app}'   # prints one token
gh-app-read api rate_limit --jq .rate
gh-app-read pr view 12 -R <owner>/<repo> --json state,headRefOid
```

Run `gh-app-read --help` for every variable. Writes and merges use plain `gh`.
Skill: `agent-factory-throughput` in the skills library.

## stack-merge

Helpers for merging a PR stack bottom-up. The script never merges. It prints the
exact `gh pr merge --match-head-commit <full-sha>` command and you run it.

| Command | What |
|---|---|
| `stack-merge prep <owner/repo> <merged-pr\|-> <pr>` | Point the next PR at `main`, then delete the merged branch. Refuses an unmerged PR |
| `stack-merge gate <owner/repo> <pr>` | Run `STACK_GATE_CMD`. On exit 0, print the merge command with the full head SHA |
| `stack-merge ack <owner/repo> <pr> [issue] [--dry-run]` | File one issue for unanswered Minor inline comments and reply to each. Exit 2 on any Major or Critical |

Run `stack-merge --help` for the variables. Check both tools with
`./stack-merge.test.sh`. It uses a fake `gh` and needs no network.

## Notes

| Doc | What |
|---|---|
| `rules/ci-cd-speed.md` | Measured CI tactics, cache costs, test gates, and safe fleet rollouts |
| `box-cost-discipline.md` | How to keep ascii.dev Boxes cheap, and why `state: idle` is not an idleness signal |
| `cost-audit-and-boat-traps.md` | Cost-audit rules, Boat box traps, and shell traps that hide a real failure |
| `box-warm-start.md` | Where the ~77s Box attach actually goes, and what a warm snapshot does and does not buy |
| `t3-code-on-a-box.md` | Running T3 Code on a Box and reaching it over `box host` |
| `silent-failover-discipline.md` | Why a working primary/backup credential failover can take a whole fleet down silently, and what to alert on instead |
| `rules/delegation-failure-modes.md` | Shared worktree traps, claim handling, review results, and measured savings |
- [cloudflare-auth-discipline.md](cloudflare-auth-discipline.md) — why wrangler, OAuth and the Cloudflare MCP cannot mint an API token, the one permission that can, and how to mint narrow per-purpose tokens that do not break on custom domains.

## Agent routing

The agent-worker roster lives in [agent-routing.json](agent-routing.json): three
tiers (`route:mechanical`, `route:scoped`, `route:judgement`) mapped to workers
with cost and benchmark indexes, plus an `unavailable` list with reasons. Not
every worker has a `command`: the default `route:judgement` worker is the
native Claude Code session doing the reviewing, not a CLI invocation, so it has
none. Tier names are durable; model names and prices are not, so update the
JSON instead of editing CLAUDE.md copies that drift. Retune tier defaults from
`agent-defect-rate` output, not vibes.

## Brightness sync

[`hammerspoon/brightness-sync.lua`](hammerspoon/brightness-sync.lua) makes the
Mac brightness keys drive external monitors too. It polls the built-in panel
four times a second and writes the same level (0-100) to each matching monitor
over DDC/CI. It also follows the Control Center slider and auto-brightness, and
re-scans monitors after a reconnect or wake.

Install:

```sh
brew install m1ddc
cp hammerspoon/brightness-sync.lua ~/.hammerspoon/
echo 'brightnessSync = require("brightness-sync").start()' >> ~/.hammerspoon/init.lua
```

Then reload Hammerspoon. It drives monitors whose name contains `DELL`; change
`MATCH` for others. Run `hs -c 'return brightnessSync.status()'` to see the
monitors it found and the last level it sent.

Do not trust `m1ddc ... get luminance` to confirm a write. Through some docks
it returns a stale value after a write that worked, so look at the screen.

## Social media cleanup tools

| Tool | What it does |
|---|---|
| [`pinterest-privacy/`](pinterest-privacy/) | Make all your Pinterest boards secret, or delete them, with dry run and undo. |
| [`reddit-cleanup/`](reddit-cleanup/) | Delete your own Reddit comments and optionally posts, with dry run, filters and a CSV backup. |

## ble-bridge

Send commands to the ESP32-S3 BLE mouse and keyboard board that controls iPhones.
`./ble-bridge "list" "@1 home" "@1 click"`. Firmware, pairing and protocol are in
[private-repo-32ef](https://github.com/pooriaarab/private-repo-32ef) `docs/ble-bridge.md`.

## ESP32 voice device

Three scripts for taking an ESP32-S3 voice board (XiaoZhi-family firmware) off the
vendor cloud. The `self-hosted-esp32-voice-device` skill in `pooriaarab/skills`
explains the order.

| Script | What it does |
|---|---|
| `esp-flash-backup <port> [dir]` | Reads the whole flash and appends its SHA-256 to `SHA256SUMS`. Read-only. |
| `esp-nvs-wifi-ota <port> [--dry-run]` | Writes the server URL and Wi-Fi login into the NVS partition, found from the device's own partition table. No rebuild. |
| `say-tts-shim.py` | Serves `POST /v1/audio/speech` with the macOS `say` voice. Standard library only. |

`esp-nvs-wifi-ota` reads `OTA_URL`, `ESP_WIFI_SSID` and `ESP_WIFI_PASSWORD` from
the environment, so the password never appears in `ps` output. It replaces the
whole NVS partition. Back up first. ESP32 radios use 2.4 GHz only.
