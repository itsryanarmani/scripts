# Self-hosted runner fleet

Turn spare always-on machines into GitHub Actions runners for private repositories. One
runner service per repository, because a personal GitHub account has no account-wide
runner.

## Why

Measured on one host (i9-10900, 128 GB RAM), fifteen private repositories moved over in a
day:

| | |
|---|---|
| CI on a hosted runner | 1–4 min queue, then the run |
| CI on the fleet host | no queue, and roughly half the wall clock |
| Actions minutes consumed | none |
| Marginal cost | the electricity of a box that was already on |

The install is the easy part. What actually decides whether this works is (a) which jobs
you move and (b) three host details that make jobs fail on your machine and nowhere else.

## Which jobs to move

| Move | Keep hosted |
|---|---|
| build, lint, typecheck, unit tests, E2E | deploy, release, publish, production smoke |
| dry-run / plan / simulation steps | anything needing a macOS or Windows image |
| AI review jobs (secrets are injected normally) | workflows that run a prompt from comment text |
| formatting bots that push to a PR branch | `gitleaks-action` SARIF uploads (see below) |

Two rules that are easy to get wrong:

- **Never copy secret values to the host.** GitHub injects repository secrets into trusted
  self-hosted jobs, so AI review keeps working untouched.
- **A `@mention`-triggered workflow executes attacker-suppliable text.** Keep it hosted
  even though it looks like just another AI job.

## Use

```sh
export RUNNER_SSH_TARGET=user@100.x.y.z    # Tailscale address of the host
export RUNNER_SSH_KEY=~/.ssh/that-host
export RUNNER_NAME=STUDIO-M2               # runner name shown on GitHub
export RUNNER_LABEL=studio-ci              # label your workflows will target
export RUNNER_WSL_DISTRO=Ubuntu            # Windows host only; omit on Linux

./add-repo.sh prepare-host
./add-repo.sh register OWNER/REPO          # first service
./add-repo.sh register OWNER/REPO 2        # second service, so its jobs run in parallel
./add-repo.sh status OWNER/REPO
```

Then point the reviewed jobs at the label:

```yaml
runs-on: [self-hosted, linux, studio-ci]
```

## The three host details nobody documents

`prepare-host` applies all three. Each was found by a job that passed on GitHub and failed
on the host:

1. **Passwordless sudo for the service account.** Hosted images have it, so workflows use
   it freely — `sudo apt-get install` for build dependencies, and `playwright install
   --with-deps`, which elevates by itself. Without it: `sudo: a password is required`.
2. **A separate `HOME` per runner service.** Every service usually runs as the same user,
   so two concurrent jobs share `~/.bun`, `~/.cache`, `~/setup-pnpm`. Symptom:
   `bun install` dies with `/home/runner/.bun/bin/bun: Text file busy`, or a build picks up
   another repository's tool version. Fix: a systemd drop-in with
   `Environment=HOME=<runner-dir>/home`.
3. **A toolchain as new as the hosted image.** A host on Node 20 breaks every `wrangler`
   step, because `wrangler` requires Node 22 while hosted images ship 24.

## Windows hosts: WSL will stop and kill your jobs

Run the runner inside WSL2. A stopped WSL kills the running job, and the symptoms do not
say "WSL":

| Symptom | Cause |
|---|---|
| Steps `null` after `Checkout` succeeded | WSL went down mid-job |
| Run stuck in `queued` while the runner looks idle | no WSL, no listener |
| Runner API says `offline busy=true` | GitHub still holds the dead session |
| `A session for this runner already exists` in the journal | restarted runner cannot reclaim it yet |

Two holders are needed, not one:

- `%USERPROFILE%\.wslconfig` → `[wsl2]` / `vmIdleTimeout=-1` (needs `wsl.exe --shutdown`
  to apply, so do it while the fleet is idle).
- A scheduled task holding `wsl.exe -d <distro> --user <user> -- bash -lc "exec sleep
  infinity"`, with an **at-startup** trigger and principal `LogonType=S4U`. The obvious
  `LogonType=Interactive` never fires on a headless desktop — `quser` returns nothing on a
  machine nobody logs into, and that is the normal state for a CI host.

Native Windows OpenSSH often uses PowerShell as its default shell, so remote commands are
PowerShell. Send bash as base64 and decode on the far side instead of fighting quoting.

## One job that cannot move

`gitleaks-action@v2` scans fine, then fails uploading `results.sarif`: it resolves the
artifact root from the runner's home, which is not a parent of a workspace under
`/opt/actions-runner`. Leave it hosted and comment why in the workflow.

## Toolchains the hosted image has and your host does not

Beyond Node, three more prerequisites each cost a red job before they were found:

| Missing | Symptom |
|---|---|
| Docker | `docker: command not found` for any workflow using `services:` — also put the service account in the `docker` group and restart the runner services |
| Rust | `failed to run 'cargo metadata'` on Tauri builds. Symlink the **toolchain** binaries into `/usr/local/bin`, not the `rustup` shims: a shim needs `RUSTUP_HOME`, which a per-service `HOME` does not have (`rustup could not choose a version of cargo to run`) |
| `xdg-utils`, `desktop-file-utils` | `failed to bundle project xdg-mime binary not found` |

## A fixed-port service container cannot run twice on one host

This is the ceiling on a single-machine fleet. Three test shards that each declare
`ports: ["5432:5432"]` are fine on hosted runners, where every job gets its own VM. On one
machine the second shard dies:

```
Bind for 0.0.0.0:5432 failed: port is already allocated
```

So that repository gets exactly one runner service and its jobs serialize. If that is too
slow, the answer is an ephemeral per-job runner, not more services on the same box.

## Remote-dev tools are a separate fight

A synced remote-dev tool (Crabbox and similar) verifies the workspace it just synced by
fetching the target commit from the forge **on the host**, with Git's config neutralized
(`GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, `GIT_CONFIG_NOSYSTEM`). Its failure messages are
generic — "remote git seed failed", "align remote Git metadata".

**Do not assume that failure is authentication.** It looks like it must be: no config, no
credential helper, private repository. Tested directly on a Windows host, Git for Windows
cloned a *private* repository with `GIT_CONFIG_GLOBAL=NUL GIT_CONFIG_SYSTEM=NUL` and no
credential config, silently and successfully. Acting on the guess instead of the test cost
hours and produced SSH keys that were not needed.

What did reproduce, and generalizes: **PowerShell with `$ErrorActionPreference = "Stop"`
turns anything a native command writes to stderr into a terminating error.** Recent OpenSSH
clients print

```
** WARNING: connection is not using a post-quantum key exchange algorithm.
```

to stderr on every connection, so a successful `git clone` over SSH kills the script that
ran it. Fix it per host:

```
Host github.com
  LogLevel ERROR
```

Verify with `@(& git clone ... 2>&1).Count` — it should be 0.

Also: these tools check that the commit being synced is on the branch they advertise, so an
unpushed local branch fails with an unhelpful message and is not a host problem. And when
every step of the tool passes by hand but the tool still fails, the bug is upstream — file
it with that evidence rather than rebuilding the machine around it.

## Make a busy fleet fast

Run `ci-cache-dropin.sh` once per host. It creates `/opt/ci-cache` and points every
runner service at it with a systemd drop-in. The caches have to live outside the job
workspace, because `actions/checkout` cleans the workspace on every run. Each service
keeps its own `HOME`; only the content-addressed caches are shared.

Then fix the workflows:

- **Delete `actions/cache` steps from self-hosted jobs.** They round-trip the cache to
  the forge and back, which is slower than reading the local directory, and they consume
  the repository's 10 GB cache quota.
- **Collapse a repo's check jobs into one.** Each job pays checkout and dependency
  install again. One repo paid install eight times per pull request; on a shared host
  that cost more than the checks. Job names are the required status checks, so update
  branch protection in the same change.
- **Cap in-job parallelism.** A 20-thread host running five concurrent jobs with
  uncapped workers reached load average 30. Pull requests queued for about 30 minutes,
  unrelated SSH sessions stopped answering, and file-sync subprocesses were killed. Set
  the task runner's `--concurrency` and the test runner's worker count.
- **One runner service per repo serializes that repo.** Check `uptime` before adding
  services: on a CPU-bound host, more concurrency is not more throughput.
- **Retire a service in the right order.** Delete the runner registration through the
  API first, then stop and remove the systemd unit. The other order leaves a
  registration the API refuses to delete while it still looks busy.
- **Send fixed-port `services:` jobs to ephemeral per-job cloud runners.** Three test
  shards that each bind the same database port cannot share one host.

Two host faults worth recognising, because both look like a per-repo problem:

- `wsl --shutdown` does not bring the runner services back. After a restart, start them
  explicitly.
- If every runner reads "offline, busy=false" at once while the services are active and
  the forge API is reachable, check IPv6. A host that resolves the Actions broker to an
  AAAA record but has no IPv6 default route leaves every listener in backoff throwing
  `ObjectDisposedException` on the TLS stream. Prefer IPv4 by appending
  `precedence ::ffff:0:0/96  100` to `/etc/gai.conf`, then restart the services.

## Keep the disk from filling: periodic cleanup

A fleet of per-repository runners fills a disk in months. Nothing cleans it. On one host,
44 runner folders held 221 GB, and a third of that was old job checkouts, package caches
and folders of runners that no longer existed.

Run `runner-host-maint.sh` on the host, as root:

```sh
./runner-host-maint.sh status                 # disk, busy jobs, runner folders with no service
./runner-host-maint.sh clean --dry-run        # list the work, delete nothing
./runner-host-maint.sh clean                  # do it
./runner-host-maint.sh install-timer          # run "clean" every day at 04:15
```

`clean` touches a runner only when its service is active and it has no job. It stops that
runner's service, clears its `_work` folder (keeping `_tool` and `_actions`), and starts the
service again. A busy runner is skipped and cleaned on the next run. A service you stopped
on purpose stays stopped. When no job runs anywhere, it also clears the service account's
package caches. It then trims the journal and the apt cache and runs `fstrim`. `--docker`
also removes unused Docker images and stopped containers older than 24 hours. That is off by
default, because Docker is shared by the whole host.

A runner folder is a folder with a `.runner` or `config.sh` file. One with no service is
listed as an orphan. `--prune-orphans` deletes it. `clean` refuses to run when it finds
runner folders and no runner services at all, so a broken `systemctl` cannot make every
runner look dead.

`install-timer` installs a copy of the script and writes `RUNNER_ROOT` and
`RUNNER_SERVICE_USER` into the unit. Run it again after you update the script. If a runner
does not start again after its cleanup, the script logs `RESTART FAILED`, counts it in
`restart_failed`, and exits with code 4, so the timer unit shows as failed.

Check what an orphan is before you prune. The usual causes are a repository that was
deleted or archived, a runner that was registered twice by mistake, and a **renamed GitHub
account**: the registration under the old name is gone for good, and its service keeps
failing. Re-register under the new name and remove the old service.

### Windows: shrink the virtual disk too

Deleting files inside WSL2 does not shrink `ext4.vhdx`, so the OS drive stays full. Compact
it with `wsl-compact.ps1`. It needs administrator rights.

```powershell
.\wsl-compact.ps1 -Distro Ubuntu -KeepaliveTask "CI WSL Keepalive" -WaitMinutes 150 -DryRun
```

It waits for an idle fleet, runs `wsl --shutdown`, compacts the file with `diskpart`, and
starts WSL again through the keepalive task. After the shutdown it always detaches the disk
and restarts WSL, even when compaction fails. A failed compaction exits with code 1. With
jobs still running after `-WaitMinutes`, or when it cannot read the job count, it exits with
code 2 and changes nothing.

Register it as a weekly scheduled task with highest privileges, run as the account that owns
the WSL distribution. It reads that account's registry, so SYSTEM does not work. Always pass
`-KeepaliveTask` with the name of the task that holds WSL open (see the Windows section
above). Without it the script starts a hidden `sleep infinity` that ends at logoff, and WSL
can stop later. After the restart the script checks that the distro answers, and it exits
with code 1 when it does not.

Two cautions. `wsl --shutdown` stops **every** distribution and every process in them, such
as agent sessions and other services. The job check counts only runner jobs in one distro.
And a job that starts between the idle check and the shutdown dies. Re-run that job.

Do **not** turn on `sparseVhd` or run `wsl --manage <distro> --set-sparse true` on a disk
you care about. Recent WSL builds call it unsafe and ask for `--allow-unsafe`, because it can
corrupt the disk.

### Other things that free or save space on a Windows host

- `powercfg /h off` deletes `hiberfil.sys`. On a 128 GB host it was 51 GB. A CI host does
  not need hibernate.
- Scan with care. A recursive size scan of a large OS drive takes more than ten minutes
  over SSH. Measure only the folders you suspect.
- A `Local Settings` or `Application Data` folder in a user profile is a junction. Its size
  is counted twice by a naive scan.

## Memory and CPU on a spare machine

Most of the capacity of a CI host sits idle. These settings cost nothing:

- In `%USERPROFILE%\.wslconfig`, set `[experimental]` / `autoMemoryReclaim=gradual`. WSL then
  gives idle cache back to Windows instead of holding it. Cap `memory=` below total RAM so
  Windows keeps some. The file needs `wsl.exe --shutdown` to apply.
- Mount `/tmp` as a tmpfs (`tmpfs /tmp tmpfs defaults,size=24G,mode=1777 0 0` in
  `/etc/fstab`). Temp-heavy installs and builds get faster. It uses RAM only while files
  exist.
- Stop `SysMain` and Windows Search on a machine nobody uses interactively.
- Cap in-job parallelism, as in the section above. More threads than cores slows every job.

## Put an idle GPU to work: a local model server

A GPU that CI cannot use can still serve a small local model for cheap, bulk agent work.

1. **Pick a model that fits.** `llmfit` (github.com/AlexsJones/llmfit) reads the hardware and
   ranks models by fit and speed. Install the pinned release binary and check its checksum.
   Do not pipe an install script to a shell. Use the `musl` build on an older Ubuntu, because
   the `gnu` build needs a newer glibc.
2. **Do not take the top score on trust.** The top of the list is often an unvetted community
   fine-tune. Pick a model from a maker you know, then measure.
3. **Mind the VRAM.** 8 GB holds a 9B model at 4-bit with a small context. A bigger model
   spills into system RAM and gets slow.
4. **Serve it with Ollama** from a release tarball, checked against the digest GitHub
   publishes for the asset. Run it as a systemd service.
5. **Bind it to a private address only.** Ollama has no login. Set `OLLAMA_HOST` to the
   machine's private network address, never `0.0.0.0`.
6. **Measure honestly.** The first call after a start loads the model and can run ten times
   slower than steady state. One short call measured 3 tokens per second. A 300-token run
   measured 27. Time a longer request after a warm-up.
7. **Route to it.** An OpenAI-compatible proxy can list the model under an alias. When the
   host is off, only that one model fails.

## Before you restart anything

`wsl --shutdown` and a service restart kill running jobs. Look first:

```sh
pgrep -fc 'Runner\.Worker'      # 0 means no job is running
```

On a busy fleet this is rarely 0. Plan restarts for a quiet hour, or wait in a loop that
re-checks. Do not assume the fleet is idle because it was idle a minute ago.

The full job-placement and cost playbook, including per-minute prices across runner
options, is the `high-volume-ci-optimization` skill in the skills repository.
