# Making ascii.dev Boxes fast for every personal repo

Measured 2026-08-28. Every number here came from a real run, not from the docs.

## The headline: we were optimising the wrong thing

The brief assumed a Box takes ~65s to come up and that a warm image would cut
that to ~1s. The first half is right. The second half is not, and the reason
matters.

A Box is **already** ~1s to ready and ~2s to first usable command:

| run | ready | first usable command |
|---|---|---|
| cold 1 | 1.0s | 2.1s |
| cold 2 | 1.3s | 2.6s |
| cold 3 | 0.8s | 2.0s |

Provisioning was never the bottleneck. Here is where the 65s actually goes,
captured from a real `git worktree add` firing the crabbox hook on
private-repo-4ed5 (693 files, 3.9 MiB):

```
lease (box new + provision) ....... 14.3s
bootstrap ......................... 10.1s
sync .............................. 48.7s   <-- the real cost
    rsync 19.7 | ssh 7.6 | finalize 4.5 | git_seed 4.0
    manifest_write 4.1 | fingerprint_remote 3.7 | prune 3.7
command (apt check + bun install) . 14.9s   (bun install itself 7.2s)
-------------------------------------------
total ............................. 1m16.8s
end to end ........................ 1m38.3s
```

**Two thirds of the wait is rsyncing the worktree to the box.** Dependency
install was 15s of 77s. So a snapshot that only caches `node_modules` fixes the
smaller half of the problem.

### A warm start is slower to first command, not faster

This is the counter-intuitive result and it is worth stating plainly:

| | ready | first usable command |
|---|---|---|
| cold (`base`) | 0.8-1.3s | 2.0-2.6s |
| warm (`--from` a 651MB snapshot) | 0.9-1.0s | **6.6-9.1s** |

Restoring the filesystem costs time. The warm box wins overall because it skips
install entirely, not because it boots faster. Anyone promising "1s warm boxes"
is quoting `ready`, which is not a number you can do work in.

## What was actually broken

### 1. Secrets: a box that comes up misconfigured, not broken

crabbox copies gitignored files to the box before installing. With no
`.crabbox-secrets` manifest it copies the worktree root only. For Content
Rabbit that meant the 5-key root `.env.local` went up and the **221-key**
`apps/website/.env.local` did not. The box installed cleanly and then failed at
runtime, which is the worst shape for an agent to debug.

Manifests now exist for all four repos. They list paths only, hold no values,
and are committed.

| repo | manifest contents | PR |
|---|---|---|
| private-repo-c4e6 | `.env.local`, `apps/website/.env.local` | #921 (merged earlier) |
| private-repo-4ed5 | `.env.local`, `backend/.dev.vars` | #206 |
| private-repo-f304 | `.env.local`, `apps/web/.env.local`, `apps/web/cloudflare/app-worker/.dev.vars` | #98 |
| private-repo-5073 | `.env.local` | #252 |

Two judgement calls worth recording:

- **private-repo-4ed5 `backend/.env.local` is deliberately excluded.** It holds live
  Stripe keys and the production BYOK encryption key. Nothing in `backend/src`
  or `scripts/` reads any of its six names — the runtime reads the unsuffixed
  names from `.dev.vars`. A box does not need them to build, and a box is a
  third-party VM, so they stay on the laptop.
- **private-repo-f304 lists two files with identical contents** (`apps/web/.env.local` and
  `apps/web/cloudflare/app-worker/.dev.vars`). That is not redundancy: Next.js
  reads one and wrangler reads the other. Dropping either misconfigures one
  runtime.

### 2. Turbo remote cache: configured, never used

The credentials already reached the box inside the root `.env.local`, but
nothing exported them and the remote script never ran turbo. Every build was
cold. Proof, on a real box, of the gap and the fix:

| run | state | result |
|---|---|---|
| A | as crabbox leaves it today | `Remote caching disabled` · 0 cached · **6.022s** |
| B | `TURBO_*` exported | `Remote caching enabled` · miss, populates remote · 6.718s |
| C | local `.turbo` **deleted** | **2 cache hits from remote** · **605ms** · `FULL TURBO` |

Run C is the one that counts. The local cache was destroyed first, so the hit
could only have come from the remote. Ten times faster.

The fix is now a named `box env` per repo carrying `TURBO_API`, `TURBO_TOKEN`
and `TURBO_TEAM`, verified injected into the box environment.

### 3. crabbox cannot ask for a warm box — and the shim that fixes it

This is the blocker nobody had hit yet. crabbox shells out to `box`, but it
forwards exactly three ascii-box settings:

```
-ascii-box-base-url   -ascii-box-cli   -ascii-box-workdir
```

There is **no** way to pass `--environment` or `--from`. So every crabbox
warmup starts from the bare `base` image no matter what snapshots exist.

`-ascii-box-cli` is the seam. `scripts/box-warm-shim` stands in for the `box`
binary, injects the two flags on `new`, and passes every other subcommand
through untouched. No crabbox change needed.

Two traps cost real time here, both silent:

- crabbox calls `box --no-update --json --api-url https://ascii.dev new --ttl 900`.
  The subcommand is **not** `$1`, and a naive "first bare word" scan picks up
  `https://ascii.dev` — the *value* of `--api-url`. The shim then passes through
  and you get a cold box that looks completely fine.
- crabbox runs `box` with `HOME` pointed at its own state directory, so
  `$HOME/.ascii/bin/box` does not exist. Resolve the real home from the OS user.

Verified end to end: box pinned to environment `private-repo-4ed5` v5, **732MB of
`node_modules` restored**, `TURBO_*` present, warmup 17.1s.

### 4. The base image already has the toolchain (and crabbox already knows)

The base image ships `node` 24, `bun` 1.3.14, `git`, `gh`, `gcc`, `make`,
`python3`, `pkg-config`, `rg`, `jq`, `docker`, `ffmpeg`, Chrome, plus Go, Rust,
Java, Ruby and PHP.

My first reading of `crabbox-attach.sh` was that its apt-install step was pure
waste on every attach. **That was wrong.** The step is guarded by
`command -v curl / git / gcc`, and all three are present, so it never fires.
Verified on a real box:

```
curl /usr/bin/curl   git /usr/bin/git   gcc /usr/bin/gcc
VERDICT: crabbox apt block SKIPS
```

So there is nothing to cut here. The 14.9s "command" phase is the package
manager install (7.2s of it `bun install`) plus overhead, not apt. Worth
recording because it is the obvious-looking optimisation that is not there.

## Cost and reaping

The docs settle the question the CLI only hinted at. `box new --no-auto-stop`
implies a default auto-stop, and there is one — but it is **purely a TTL**:

> "Box has no idle timer. The auto-stop TTL counts from creation or resume,
> never from last activity." — docs.ascii.dev/box/faq

Default TTL is 1 hour, max 30 days. At expiry a box **stops and snapshots**; it
is not deleted. So the standing rule holds: nothing stops a Box for being
unused, and the caller must `box stop`.

**Webhooks cannot help.** `box webhook` fires on `ready`, `error`, `archived`
and `hydrated` only. There is no idle or activity event, so lifecycle hooks
cannot drive an idle reaper. Do not wire them for that.

`box-reap` in this repo already does the right thing: it never reaps on state,
because a Box pegged at 100% CPU still reports `idle`. It measures CPU and load
and prefers a heartbeat file. That stays the reaping mechanism.

Plan `box_20`: 100 concurrent, **50 starts/hour**, 150/day. The hourly start
ceiling — not the concurrency cap — is what limits an agent fleet.

## Security

- **`box env list` prints stored secret-file contents in plaintext.** Anything
  parked in an environment's secret files is readable by anyone who can run the
  CLI. That is why the repo environments carry `TURBO_*` **only**, and app
  secrets keep going up the per-run crabbox sync path instead.
- Every repo environment sets `--box-credentials false --agents-credentials false`.
  A build box needs neither the Box CLI credentials nor the agent logins, and
  one compromised box otherwise exposes the whole personal AI spend surface.
- **Scrub secrets before snapshotting.** A snapshot is a filesystem image and
  outlives a key rotation. The `private-repo-4ed5-ready` snapshot was scrubbed of
  `.env.local` and `.dev.vars` first; the environment injects config at boot
  instead. Verified: a box deployed from it has no secret files and full
  `node_modules`.
- **Zero data retention and warm snapshots are mutually exclusive.** Enabling
  ZDR deletes existing named snapshots and blocks creating new ones. Pick one.
  We keep snapshots and do not enable ZDR.

## Gotchas that cost time

- **`sizeBytes` on a named snapshot is not the restored size.** Ours reported
  32,830 bytes and restored 651MB. Snapshots are incremental deltas on a chain.
  Do not judge a snapshot by that number — deploy from it and look.
- **ascii's GitHub token is a scoped app token.** It 404s on any repo not
  connected in the ascii dashboard, so `box env add-repo itsryanarmani/private-repo-c4e6`
  fails and an in-box `gh repo clone` of it fails too. Connect the repo in the
  dashboard, or push the source from the laptop.
- **Max 10 named snapshots per account.** Four repos is fine; a snapshot per
  worktree is not. Refresh by saving the same name again; the old artifact is
  released and boxes already deployed from it are unaffected.
- **A green exit proves nothing here.** Three separate steps in this work exited
  0 while doing nothing: the shim passing through on a mis-parsed subcommand,
  `box new --json` emitting JSONL that a single-object parser dropped (which
  leaked three billing boxes), and the pi+OpenRouter grok worker producing zero
  bytes in 20 minutes. Verify by inspecting the result, always.

## What to adopt, and what to skip

Worth wiring:

- **`box env`** — one named environment per repo. Already done for all four.
- **`box snapshot` / `--from`** — the dependency cache. Real win, via the shim.
- **`box exec --detach`** — runs past the 600s exec cap; poll with
  `--status <pid>`, logs at `~/.ascii/processes/<pid>.log`.
- **`box scp`** — works, and is the simplest way to push a file to a box.
- **`box limits`** — check `starts.hour.remaining` before any fan-out.

Not worth wiring, with reasons:

- **`box webhook`** — no idle event. Cannot drive reaping. That was the only
  reason we wanted it.
- **`box data-retention`** — mutually exclusive with named snapshots. The
  snapshots are worth more than delete-on-stop.
- **`box host` / `box forward`** — useful for a human debugging a dev server,
  irrelevant to an unattended build box. `forward` does not survive a resume.
- **`box org` / `box team`** — single-user personal account, one wallet. Nothing
  to scope.
- **`box desktop`** — no use for a build box.
- **`box api-key`** — one key already exists and works. Rotate, do not automate.
- **`--type large`** — twice the price, and measurably not faster.

## Getting the attach from ~84s to ~2s

The warm snapshot was a wash because it attacks install, which is the small
half. The transport is the big half. Round trips against a running Box:

| transport | round trip | usable as a payload channel? |
|---|---|---|
| `box exec` | 1.13 / 1.17 / 1.31 s | **Yes — as an argv word.** See the correction below. |
| `box ssh`  | 5.17 / 5.17 / 5.72 s | Yes, and it takes stdin. This is the honest floor for anything SSH-based. |
| `box scp`  | 6.05 / 6.14 / 9.83 s | Yes, but it rides SSH too, so it is no better. |

Streaming a tar into `box ssh` gives a working ~6.7s attach. Good, not 2s.

**`box host` is the way through.** It publishes a Box port on a stable HTTPS URL
that never touches SSH. Put a small receiver on that port, POST the tree to it,
and let it extract and decide about installing:

```text
attach 1:  2.23s   attach 4:  1.82s
attach 2:  1.99s   attach 5:  1.86s
attach 3:  1.87s
```

Five consecutive runs, tar build included, `extract_rc=0` each time, and the
change verified by reading a marker back off the box over a different
transport. About **45x faster than crabbox's ~84s**.

`scripts/box-fast-attach` plus `scripts/box-attach-receiver.py` implement this.
Setup costs ~10s once per Box; every attach after that is ~2s. Install is
skipped unless the lockfile hash actually moves.

### Correction: `box exec` DOES carry a payload

I first concluded that `box exec` silently drops a large argument, after a
43k-char base64 blob arrived as one byte. That conclusion was wrong, and the
mistake was mine, not the platform's. The blob was interpolated into a
`bash -lc "...$VAR"` string, and the quoting is what destroyed it.

Passed as its **own argv word**, the payload arrives intact:

```text
sent 100000 chars -> box received 100000
sent 130000 chars -> box received 130000
sent 150000 chars -> E2BIG: argument list too long, posix_spawn 'bash'
```

So the ceiling is the box-side ARG_MAX, ~128 KiB, and a normal edit is nowhere
near it. `box exec` is HTTPS, needs no SSH and no open port, and the round trip
is ~1.2s. That makes it the right transport, better than the hosted port on
both speed and exposure.

The rule that generalises: pass a payload as an argument, never interpolate it
into a `-c` string.

### The final shape, and where the time really went

Detecting *what* changed turned out to cost more than sending it. Hashing 694
files with one `shasum` process each took 8.4s locally, against 0.6s of actual
work on the Box. Asking git instead is free.

```text
seed (full tree, once) .......... 7.43s
attach, nothing changed ......... 0.43 / 0.72s
attach, one changed file ........ 1.41 / 1.49 / 1.51s
```

Verified by reading a marker back off the Box. Against crabbox's ~84s that is
about **56x**. `scripts/box-fast-attach` plus `scripts/box-unpack.sh`.

### The review caught five real bugs

The council review on scripts#47 flagged the prototype receiver, and it was
right. Rather than harden it, I deleted it: the final design seeds over
`box ssh` and sends deltas over `box exec`, so the HTTP receiver and its open
port are no longer part of the path at all. That removes the critical finding
by removing the component.

The other four were real bugs in code that stayed, all fixed and each verified
against a live Box:

| finding | fix | proof |
|---|---|---|
| tar members could escape the destination | reject any member matching `../` or a leading `/` before extracting | crafted `../../pwned.txt` archive -> exit 2 |
| `X-Repo: ..` escaped the work root | destination must live under `/home/user/work` and contain no `..` | `dest=/home/user` -> exit 2 |
| a failed install still wrote the lock marker, hiding a broken `node_modules` until the lockfile changed again | only write the marker when the install returns 0, and surface the output | install of a nonexistent package -> exit 1, marker absent |
| pointing at a different Box sent a delta to a machine with nothing on it | reseed whenever the Box id changes | `--box bx_DIFFERENT` -> "Box changed; reseeding" |
| a locally deleted file stayed on the Box forever | split the change set into changed and deleted, and remove the deleted ones | file removed locally -> "0 changed, 1 deleted" -> gone from the Box |

The deletion fix hid a second bug worth naming. I first passed the delete list
as an environment variable around the `box exec` call. `box exec` runs the
command **on the Box**, so a variable exported around the local `box` process
never arrives, and every deletion was silently skipped while the call still
reported success. Pass it as an argument.

Hardening cost nothing measurable:

```text
attach, nothing changed .... 1.62 / 1.81s
attach, one changed file ... 1.49 / 1.53 / 1.97s
```

### Keep the hosted port token-gated

`box host <id> <port>` defaults to `--private` and returns a URL with a
`?_token=` on it. **Do not pass `--public`.** The receiver extracts a tar into
the Box, so an ungated URL lets anyone who guesses the subdomain write arbitrary
files there. I used `--public` while prototyping, which was wrong. Verified
after the fix: a POST with no token returns `403 Access denied`.

The gated URL needs one extra step. It answers with a 302 that sets a session
cookie, and curl turns a 302 into a GET and drops the body — so POSTing straight
at the token URL uploads nothing and says nothing. Do the handshake once into a
cookie jar, then POST the bare URL with that jar. Token-gated attach measures
1.68 / 1.77 / 1.79s, no worse than the ungated one.

The URL and the cookie jar both carry live credentials, so `box-fast-attach`
keeps them in `~/.local/state/box-fast-attach/<hash>` at mode 700, never in the
worktree where they could be committed.

### There is a first-party file API, and it may be better still

The docs describe `PUT /boxes/{boxId}/files` and `GET /boxes/{boxId}/files` on
`https://ascii.dev/api/box/v1`, alongside the `POST /boxes/{boxId}/commands`
that `box exec` already uses. That is the same HTTPS transport that makes
`box exec` a 1.2s call, and it needs no receiver process and no exposed port —
so it would likely be a bit faster than this and strictly safer. I have not
measured it. It is the first thing to try next.

### Two bugs in this that are worth remembering

Both produced a confident, fast, wrong answer:

- **`set -o pipefail` plus `cat` on absent lockfiles.** `cat bun.lockb ...`
  returns non-zero for the files that do not exist, pipefail fails the whole
  pipeline, and `set -e` kills the script at that line. It exits in 0.4s and
  looks like a very fast success. Feed `cat` only the files that exist.
- **HTTP/1.1 keep-alive on a single-threaded receiver.** One idle connection
  blocks the next request until it times out, which turned the 1.7s attach into
  a consistent 90s. The timing looked stable, so it read as a real measurement
  rather than a bug. Use `ThreadingHTTPServer` and send `Connection: close`.

## It holds on the biggest repo, and what it costs per repo

Content Rabbit is the worst case here: 5,699 tracked files, a 29 MB gzipped
tree, a large bun monorepo.

```text
seed (once per Box) ......... 42.7s
attach, nothing changed ..... 1.99 / 2.06s
attach, one changed file .... 1.80 / 1.92 / 2.00s
```

Same shape as the 1.1 MB repo, because the steady-state cost is one `box exec`
round trip and not the size of the tree. Only the one-time seed scales.

`scripts/box-repo-audit` reports readiness per repo. Across 95 locally-cloned
`itsryanarmani/*` repos, 46 have a lockfile and are candidates. The seed cost is
the number to plan against:

| repo | pkg | files | tree gz |
|---|---|---|---|
| private-repo-c4e6 | bun | 5,776 | 29 MB |
| private-repo-5073 | bun | 11,744 | 21 MB |
| nova | bun | 11,041 | 20 MB |
| private-repo-4a88 | npm | 792 | 16 MB |
| example | npm | 752 | 16 MB |
| private-repo-4ed5 | bun | 693 | 1.1 MB |
| private-repo-f304 | bun | 892 | 1.9 MB |

The audit takes `--tsv` for parsing. It has to: one repo path contains a space,
so parsing the aligned table with `awk $NF` silently truncates it.

### The GitHub app is scoped to public repos only

`box env add-repo` fails for every private repo, and so does an in-box
`gh repo clone`. Measured from inside a Box: the token sees **44 public repos
and 0 private ones**, so private-repo-c4e6, private-repo-f304, private-repo-4ed5, private-repo-5073
and private-repo-b1e6 all 404. Granting the ascii GitHub App access to private
repos would fix it.

It does not block anything here. `box-fast-attach` pushes the tree from the
laptop and never asks GitHub, so a private repo warms exactly like a public one.

## The second review pass, and seven more bugs

The follow-up council review found four Major and three Minor issues. All seven
were real. Fixed and each verified against a live Box:

| finding | fix | proof |
|---|---|---|
| `box-reap-cron` discarded the reaper's exit status, so launchd showed a healthy job while nothing was being stopped | run the reaper outside the redirect block, capture `$?`, `exit "$rc"` | stub reaper exiting 3 -> wrapper exits 3; real reaper -> 0 |
| the full seed wrote the lock marker even when the install failed | same guard the delta path already had | seed with a broken lockfile -> exit 1, no marker |
| files listed in `.crabbox-secrets` were never re-checked after the first seed, so an edited `.env.local` left stale credentials on the Box | hash the declared secret files and diff that fingerprint each run | edited `.env.local` -> synced, probe line read back off the Box |
| the Box id was recorded before the seed succeeded, so a failed seed left the next run taking the delta branch against an empty Box | write every state file only after the transfer returns 0 | failed seed -> no state files written |
| `box-unpack.sh` was never actually copied to the Box | the seed ships it | fresh Box with no unpack script -> present after seed |
| `git status | awk '{print $NF}'` truncated any path containing a space and then misclassified it as deleted | `git status -z` with NUL-aware parsing | `docs/space test/a file.md` -> synced, then deleted correctly |
| the full seed never removed files deleted locally | clear the destination first, keeping `node_modules` and the lock marker | deleted file -> gone after reseed |

Two of my own bugs surfaced while fixing those, both worth naming because both
looked like success:

- **macOS `bsdtar` exits 1 on warnings.** With `set -o pipefail` that failed the
  seed *after* it had already completed on the Box. Treat 0 and 1 as success,
  and confirm the archive lists.
- **`box exec` joins argv into a shell command string.** A newline inside an
  argument ends the line, so the next path ran as a command
  (`bash: docs/space: No such file or directory`). The delete list is base64 now.
  This is the same lesson as the payload: give `box exec` one shell-safe word.

Final numbers after all of it:

```text
seed .......................... 12.0s
attach, nothing changed ....... 1.53 / 1.55s
attach, one changed file ...... 1.35 / 1.50 / 1.53s
```

### One more: a security check that fails open

The third review pass found a subtle one. The path-escape guard was:

```sh
if tar -tzf "$tmp" | grep -qE '(^|/)\.\.(/|$)|^/'; then reject; fi
```

Under `set -o pipefail`, `grep -q` exits the moment it matches, `tar` then dies
of SIGPIPE (141), and pipefail reports **141** for the pipeline instead of
grep's 0. The `if` evaluates false and the archive extracts. The check fails
**open**, and the bigger the archive the likelier the race — backwards for a
security control.

Fixed by writing the listing to a file and grepping the file. Verified on a Box:
a crafted archive with `../../pwned.txt` returns exit 2 and nothing lands
outside the destination.

Honest caveat: I could not reproduce the bypass locally — my 20,001-member
archive still rejected correctly, because the listing fit the pipe buffer. The
mechanism is real and the fix costs nothing, so it stands, but I am reporting a
closed race rather than a demonstrated exploit.

## The GitHub connection changes the whole design

Once the ascii GitHub App got access to private repos, the box stopped needing
anything from the laptop. Measured from inside a Box:

```
git clone --depth 1 private-repo-c4e6 (5,863 files) .... 3.23s
git clone --depth 1 private-repo-4ed5  (  722 files) .... 1.06s
bun install, private-repo-c4e6 ......................... 9.80s  -> 1.9 GB node_modules
```

3.2s for the Box to fetch the tree against 42.7s to push the same tree up from
the laptop. Uploading was always the wrong direction.

### A `box env` per repo is the whole answer

`box env add-repo` clones the repo into every new box, and `box env set-file`
writes the gitignored env files in. One `box new --environment private-repo-c4e6`
now gives, with **nothing uploaded**:

```text
box ready and usable ................ 8.4 - 10.7s
  repo cloned, 5,870 files, on main
  private-repo-c4e6/.env.local ......... 7 keys
  apps/website/.env.local ........... 221 keys
  TURBO_API / TURBO_TOKEN / TURBO_TEAM
```

Key counts read off the Box, not inferred from the file existing.

So the two tools now split cleanly. The **environment** supplies the committed
state and every secret. **`box-fast-attach`** supplies only what GitHub cannot
know: your uncommitted work. It detects that the Box already has the repo, has
the Box fetch your HEAD commit itself, and then overlays the dirty files.

```
1. box new --environment <repo> ................. 10.7s
2. first attach (fetch HEAD + install + dirty) .. 27.6s
3. every attach after that ...................... 1.69 / 1.78s
```

### Environments are free

`box limits` exposes no storage quota, no snapshot quota and no byte counter —
every billing field it returns is time-based (`creditBalanceSeconds`,
`last24hUsageSeconds`, `subscriptionQuotaSeconds`). I hold 7.0 GB of automatic
snapshots and 689 MB of named ones, and the balance has only ever moved with
running seconds. So there is no reason not to give every repo an environment.
**61 private repos now have one.**

### The default TTL is 60 minutes

Measured: `box new` with no `--ttl` reports `ttlSeconds: 3600`, and
`archiveAfter` lands exactly 60.0 minutes after `createdAt`. So a forgotten Box
costs at most about $0.036, not an unbounded amount. That does not retire the
reaper — `--no-auto-stop` removes the limit, `box resume` restarts the clock,
and crabbox passes `--ttl 90m` — but the exposure is bounded by default.

### `box exec` joins argv into a shell string, again

This trap has now cost three separate bugs. The probe

```sh
box exec "$ID" -- bash -c "test -d '$DIR/.git' && echo yes || echo no"
```

always answered `no`, even with the directory plainly present, because the
quotes are lost when argv is joined: it degenerates to `bash -c test` plus
stray words. Use the exit code of a plain `test` with no shell metacharacters:

```sh
box exec "$ID" -- test -d "$DIR/.git"
```

The general rule for `box exec`: one shell-safe word per argument, no
metacharacters, no newlines, and never a `-c` string you interpolated into.

## Setup scripts do not work, and both routes fail quietly

Neither documented way to run per-repo setup on a Box works. Verified 2026-08-28:

- **`setupScript` on an environment's repo entry.** The field is in the API
  response. `PUT /api/box/v1/environments/{id}` with it populated returns
  **200 `environment.updated`** — and the field reads back empty. A clean
  success that changed nothing. `box env add-repo` has no `--setup-script` flag.
- **`box new --setup-file <path>`.** `setupStatus` stayed `pending`
  indefinitely, `setupError` stayed null, the script never ran and
  `node_modules` was never installed. It also made the Box **6x slower to first
  usable command: 52.7s against 8.5s without the flag.**

Do the install yourself after boot. `box exec` is ~1.2s and verified, and
`box exec --detach` runs past the 600s cap. That is what `box-git-sync.sh` does.

## Agent credentials: I had this backwards

I first set `--agents-credentials false` on every repo environment, reasoning
that a build Box needs no agent logins and one compromised Box should not expose
the whole personal AI spend surface.

That made every repo Box useless for delegated work. The agent CLI logins live
in a separate `agent-roster` environment, so a Box started from a repo
environment had **no muse, pi, gemini or codex at all** — only whatever the base
image ships. A second agent hit exactly this and reported the Box as unusable.

The two credential switches deserve opposite answers:

- `--box-credentials false` — always. These let a Box create and control other
  Boxes, which is the escalation that actually matters.
- `--agents-credentials true` — plus a copy of `agent-roster`'s five secret
  files, via `box-env-provision --with-agents`. This does widen the blast
  radius. It is a deliberate trade: the keys already sit on ascii under
  `agent-roster`, so copying them hands them to nobody new — it only means more
  Boxes carry them.

## T3 Code threads get no Box, and that is correct

The attach is a `git()` shell function in `~/.zshrc` that intercepts
`git worktree add`. A shell function exists only in an interactive zsh:

```text
zsh -ic 'whence -w git'   ->  git: function
zsh  -c 'whence -w git'   ->  git: command
```

T3 Code creates its worktrees from a Node child process, so `git` is the plain
binary and the wrapper never fires. Independently, T3 runs git, diffs and
terminals on its own disk, so an attached Box would sit idle and bill while the
agent worked on the laptop.

So do not auto-attach on T3 worktree creation. Run `box-fast-attach` when you
actually want a remote build. T3's own hook would be a `t3.json` at the repo
root with a `scripts[]` entry marked `runOnWorktreeCreate: true` — documented,
untested here.

## The launch command

Snapshot and environment compose, and together they give the whole thing:

```sh
box new --from agent-roster-ready --environment <repo>
```

Measured on private-repo-c4e6, usable in **15.34s**:

| what | where it comes from |
|---|---|
| repo cloned, 5,876 files | the **environment** (`box env add-repo`) |
| `.env.local` 7 keys, `apps/website/.env.local` 221 keys | the **environment** (`box env set-file`) |
| `TURBO_API` / `TURBO_TOKEN` / `TURBO_TEAM` | the **environment** (`box env set-var`) |
| claude, codex, gemini, kimi, pi, muse | the **snapshot** |

Agents verified with arithmetic on the Box, not "reply OK": pi on `zai-api`
answered 4087 and muse answered 667. `kimi` fails with a 429 — the Moonshot
account is suspended for insufficient balance, which is an account problem, not
a Box one.

**Credentials alone are not enough.** Copying `agent-roster`'s five secret files
into a repo environment puts the logins on the Box, but the base image ships
only claude, codex and kimi — `gemini`, `pi` and `muse` are missing. The
snapshot is what supplies the binaries. Use both flags or you get keys with
nothing to run them.

One shared `agent-roster-ready` snapshot serves every repo, so the **10 named
snapshots per account** cap never binds. There is no need for a snapshot per
repo.

## Running the work on a Box instead of the laptop

This is the point of the whole exercise, and it is a different thing from
attaching. Attaching keeps a Box in sync with your checkout. **`box-work`**
starts a Box that is ready to work and runs the job there.

```sh
box-work <repo>                      # start or reuse; syncs your uncommitted edits
box-work <repo> --agent pi "brief"   # run one agent on the Box, headless
box-work <repo> --agent pi "brief" --issue N  # claim itsryanarmani/<repo>#N first
box-work <repo> --ssh                # a shell on the Box
box-work <repo> --stop               # stop it
box-work --list / --stop-all
```

`--issue` is optional. With it, `box-work` claims the issue with
`bin/fleet-presence` (from `private-repo-b1e6`, on the laptop) before the agent
starts, refuses when another agent holds a live claim, and releases on exit
through a trap, on success, on failure and on interrupt. Without it the run
dispatches unguarded and says so. A missing `fleet-presence` binary stops a
guarded run instead of running it unguarded.

Measured:

```text
first start for a repo ........ ~100s  (snapshot restore + git fetch + install)
reuse an existing Box ......... 4.1s
one agent doing real work ..... 24.0s
```

Verified end to end, not inferred: `box-work adscapi --agent pi "...89 times 97..."`
created `BOX_PROOF.md` containing `8633` **on the Box**, and the laptop copy of
the repo was untouched.

Three repos in parallel — three Boxes, three agents, one command each —
finished in **129.6s wall clock**, each agent returning its own repo's correct
`git ls-files` count (private-repo-5e18 80, private-repo-3d96 1497, usegeoaeo 293).

The economics: a Box is 4 vCPU / 8 GB against a 12-core / 36 GB laptop, so a
single Box is not faster. Ten of them are, and the laptop stays free. The cap is
100 concurrent Boxes; the binding limit is **50 starts per hour**, so keep Boxes
warm and reuse them rather than starting one per task. At $0.036/h, ten Boxes
running for an hour is 36 cents.

### The brief has to be base64

`box-work --agent pi "Create a file named ..."` first delivered only the word
`Create`. `box exec` joins argv into a shell command string, so a multi-word
brief is split across argv and the agent sees just the first word. It then asks
a clarifying question and does nothing, while the call reports success. The
brief is base64-encoded now. Same lesson as the payload and the delete list:
give `box exec` one shell-safe word.

### T3 Code, concretely

A T3 thread runs the agent on the laptop, always. T3 shells out to provider CLIs
on its own disk, so there is no per-thread Box to arrange, and pointing a
provider `binaryPath` at a Box wrapper gives a green thread that changed
nothing. Two real options:

- **Run the work with `box-work` instead of in a T3 thread** when the job is
  heavy or you want several at once. This is the tested path.
- **Run the whole T3 server on a Box** and reach it over `box host`. Then T3's
  "own disk" is the Box. That is one Box for all threads, not one per repo. The
  shape is written up in `t3-code-on-a-box.md`.

## When a Box starts, and when it stops

`box-work` was a command you had to remember. `box-session` makes it automatic
by hanging off the agent harness's own session hooks:

```
SessionStart -> box-session start   # warms a Box for this repo in the background
SessionEnd   -> box-session end     # stops it
```

Wired into `~/.claude-personal{,-1,-2}/settings.json` (personal only; the work
config is untouched). Two gates keep it honest:

- **Opt-in per repo.** No `.crabbox-default-on` marker at the repo root, no Box,
  no cost. Today that is 4 repos, not 61.
- **Non-blocking.** A cold start is ~100s and a session must never wait on it.
  The hook forks and returns in **0.38s measured**. By the time you have read
  the diff, the Box is up; `box-work <repo>` then reuses it in ~4s.

Verified end to end: the hook returned in 0.38s, the Box came up in the
background, and it had the repo (123,159 files with deps), the 221-key
`apps/website/.env.local`, 3 `TURBO_*` vars, **1.9 GB of installed
node_modules**, and all six agent CLIs. `SessionEnd` stopped it.

Three independent things stop a Box, which is the right number for something
that bills by the second: the session hook, the 60-minute default TTL, and the
hourly `box-reap`.

## Watch the timings, not the exit codes

The expensive failures here are silent. `box-fast-attach` fell back to a full
tree upload when a helper was missing on the Box: exit 0, no warning, **50x
slower**. Nothing but a stopwatch catches that.

`box-perf-check <repo>` measures a no-op attach, a real one-file delta and a
bare `box exec` round trip, and compares them against a recorded baseline.
`com.pooriaarab.box-perf` runs it weekly.

Proof it works — helpers deleted from the Box:

```text
now:  noop=0.51s delta=13.15s exec=0.91s
base: noop=0.52s delta=1.43s  exec=0.93s
REGRESSION:
  delta 13.15s vs 1.43s baseline (9.2x)
```

**The probe has to be a git-tracked file.** My first version wrote an untracked
one, and `box-fast-attach` reads `git status --untracked-files=no`, so the probe
was invisible and the "delta" silently became a second no-op. The check reported
a healthy 0.41s while measuring nothing — the same class of bug it exists to
catch.

## The reaper's exit code immediately earned its keep

Making `box-reap-cron` propagate the reaper's status (it used to always exit 0)
turned up a real problem within minutes: `launchctl list` started showing
`exit=3`, and the log said

```text
WARNING: auto-stop is OFF on 2 Box(es) (...); nothing will ever stop them.
```

Two Boxes had been started with `--no-auto-stop`, so `archiveAfter` was null and
no TTL would ever fire. Both were idle at load 0.00. Before the fix this exited
0 and nobody would have known.

## Environments drift, so check them

Three of the 61 environments were cloning a branch that was wrong or gone:

```text
private-repo-4ed5   clones 'production'                                   default is 'main'
private-repo-3d96    clones 'feature/migration-to-private-repo-3d96'            default is 'main'
private-repo-5e18       clones 'pooriaarab/pooria-arab/help-us-identify-...'  default is 'main'
```

`production` no longer exists at all, so that Box cloned nothing and looked
fine until a build failed.

**Root cause was mine.** The provisioner read the default branch from
`git symbolic-ref refs/remotes/origin/HEAD`, which is whatever the local clone
recorded when it was made. It goes stale when a default branch changes, and on
private-repo-5e18 it produced that mangled multi-segment value. It asks GitHub now
(`gh repo view --json defaultBranchRef`) and rejects anything containing a
slash.

Drift will happen again — default branches change. So:

```sh
box-env-provision --verify   # report environments cloning the wrong branch
```

runs weekly from `box-perf-cron`, alongside the timing check. Same principle as
`box-guard`: assume the config rots and check it, rather than assuming
provisioning stays correct.

## Still open

- **Content Rabbit has no warm snapshot yet.** Its repo is not connected to the
  ascii GitHub app, so the box cannot clone it. Either connect it in the
  dashboard or seed the snapshot by pushing the tree from the laptop once.
- **The 49s rsync is untouched.** It is now the dominant cost by a wide margin.
  A snapshot that already contains the repo checkout would turn the full sync
  into a delta; that is the next real win, and it is bigger than the install
  saving we just banked.
- **The shim is not yet wired into `crabbox-attach.sh`** for every repo.
