# Boat runner pool

For cost audits, safe drains, and development versus production scheduling,
read [Reduce CI cost without blocking delivery](ci-cost-controls.md).
GitHub Actions can schedule this pool without the native Boat CI integration.

Run `boat-pool` on the owner's Mac with `gh` authenticated and the Box CLI at
`~/.ascii/bin/box`. Install the broker from #508 first. Set `BROKER_URL`,
`POOL_TOKEN` and (for hooks) `WEBHOOK_SECRET` in the operator shell; never commit
those values. The service needs only the pool token, not the GitHub token.

- `./boat-pool up boat 1 --dry-run` shows provisioning without creating a Box.
- `./boat-pool up boat 1` creates a default 4-vCPU Box; `boat-8` uses large.
  Creation is serial. The named environment injects no account credentials,
  and each Box uses `--no-env --no-auto-stop`. Non-null or missing
  `archiveAfter` stops provisioning. A failed install reports the Box ID for
  inspection or deletion; it never silently creates another Box.
- `./boat-pool status` reads pool Boxes, agent state and broker counts.
- `./boat-pool heal --dry-run` inspects existing Boxes and plans replacements
  for inactive agents. Omit dry-run to replace them, then remove the old Boxes.
- `./boat-pool down bx_<id>` stops and deletes only a named pool Box.
- `./boat-pool hooks --dry-run` lists private, non-archived owner repos.
  Omit dry-run to create/update matching webhook URLs; this affects all listed
  repositories. Repo privacy is checked again immediately before mutation.

Provisioning downloads runner v2.338.0 onto the standard Boat image and installs
`boat-runner-agent` at `/usr/local/bin`. `/etc/boat-runner.env` has mode 0600,
transferred through SSH stdin. The service runs as `user` with `Restart=always`.
Inspect it with `systemctl status boat-runner-agent` and
`journalctl -u boat-runner-agent`. Runner output is in
`/home/user/actions-runner/boat-runner.log`.

The agent persists each lease before launch. After a runner exits or a service
restart it reports done before taking another lease. Failed reports retry every
five seconds. An idle runner stops after 180 seconds; a job-start hook disables
that idle timer. Cleanup removes `_work/<repo>`, force-removes containers created
after the lease start, and uses noninteractive sudo to remove new `/tmp` entries
with modification times after that start, owned by `user` or root. A persisted
snapshot preserves pre-existing `/tmp` entries even when a job modifies them;
symlinks are removed without following their targets. On these dedicated pool
Boxes, new temporary entries and containers from the same users during a lease
are treated as job resources. Cleanup errors are logged without blocking the
next lease. Older lease files without cleanup metadata skip temporary/container
cleanup. Cleanup retains `_work/_tool`, Bun, Playwright and Docker images.
Docker image pruning runs once a day.
Broker/GitHub outages delay work until lease cleanup is acknowledged.

The [pool cost proposal](boat-pool-cost-plan.md) describes a disabled demand
policy, its cost worksheet, and the drain safety requirements before activation.

## Two models: one sandbox per job, or one pool Box per label

Use one model per workload. Do not mix them in one job.

Model A runs one sandbox per CI job. It needs no pool code. Use it for
sparse jobs on any host. `boat run --from ci-base --type small --push . --
<command>` creates one sandbox, copies the checkout in, runs the command,
prints the cost, and deletes the sandbox. It exits with the command exit
code. A cancelled job also deletes the sandbox. See
[CI with Boat](https://docs.boat.dev/ci.md).

Model B keeps one pool Box per label. It uses `boat-pool`,
`boat-runner-agent`, and the broker in
[workers/boat-runners](workers/boat-runners/README.md). Use it for steady
CI load on private `pooriaarab` repos. Each Box serves one lease at a time.
The pool exists because Model A pays a fresh start per job, while Model B
pays idle time between jobs. Report both costs before you pick.

`boat run` has no `--ttl` flag. Bound the command with `--timeout`
instead. For an explicit TTL, use `boat new --from ci-base --type small
--ttl 1800` plus `boat exec` plus `boat delete --yes` in a step that
always runs. Flag syntax verified with `boat 1.0.53 --no-update help`.

## Gate heavy work on hydration after a restore

`ready` means commands work. It does not mean the disk is complete. On a
resume, a fork, or a start from a named snapshot, system paths (`/usr`,
`/etc`, `/opt`, `/var`, `/srv`, `/root`), Docker, and enabled systemd
services arrive seconds later. See
[Readiness](https://docs.boat.dev/readiness).

Wait for each dependency with a bounded wait. Then run the heavy work.

```bash
boat exec "$ID" --timeout 120 "until docker info >/dev/null 2>&1; do sleep 1; done"
boat exec "$ID" --timeout 120 "until systemctl is-active --quiet my-app; do sleep 1; done"
until [ "$(boat info "$ID" --json | jq -r .sandbox.hydrated)" = "true" ]; do sleep 2; done
```

Do not write job output into a restored tree before `hydrated` is
`true`. Reads wait for their own file, but early writes race the
background download. After hydration, do one targeted pass over the hot
paths. Boat records the first files the app opens in
`~/.ascii/playbook.json` (first 5,000 paths) and fetches them first at
the next start. Then save the named snapshot. A save before hydration
ends misses the run.

A `409 sandbox_starting` answer means the sandbox still starts after 60
seconds. Retry every few seconds. A `502` with message
`sandbox_restoring` means the files still mount. Retry after 1 to 3
seconds. Retry only these infrastructure answers, with a bound. Never
retry a failed test command as infrastructure. The test exit code is
the verdict.

## Keep snapshots minimal

A snapshot saves the disk changes. It does not save the OS, `/tmp`,
journal logs, `~/.cache`, the Docker build cache, or images that no
container and no Compose project uses. Named volumes and containers
come back. Registry images pull again by digest at each resume. See
[What a snapshot saves](https://docs.boat.dev/snapshots/whats-saved).

Leave out what you can rebuild. Write a `.boatignore` file. Boat does
not read `.gitignore`. `.git` is always saved.

```bash
cd ~/myapp
printf 'node_modules/\n.next/\n' > .boatignore
```

Keep one container per needed image, even if it never runs:
`docker create --name keep-node node:22`. Install Playwright browsers
outside `~/.cache` with `PLAYWRIGHT_BROWSERS_PATH` on the first line
of `~/.bashrc`. Do not tar a cache into the snapshot to skip hydration.
That tarball downloads in full at every restore. Prefer `.boatignore`
plus reinstall, or deps installed natively in a named snapshot.

Measure cache locality before you add an Actions cache. A blanket cache
that always misses costs a download and saves nothing. Compare matched
medians across runs on the same label, not single runs and not mixed
labels. Host speed varies.

## Keep the job environment deterministic

Pin the runner version. `boat-pool` installs runner v2.338.0 and
`boat-runner-agent` at `/usr/local/bin`. The unit file lives at
`/etc/systemd/system/boat-runner-agent.service` with `Restart=always`,
`RestartSec=5`, `KillMode=control-group`, and `TimeoutStopSec=30`.
Each Box runs one lease at a time.

The service runs as `user` with a fixed `RUNNER_DIR` at
`/home/user/actions-runner`. Cleanup is sparse by design: it removes
only containers, `/tmp` entries, and workspaces created during the
lease. It retains `_work/_tool`, Bun, Playwright, and Docker images.
Docker image pruning runs once a day.

Set an explicit locale and noninteractive apt in every provisioning
script (`LC_ALL=C.UTF-8`, `DEBIAN_FRONTEND=noninteractive`). Use a
modern git. Pin the unit `PATH`. None of these are installed yet. See
required future work below.

## Bill idle and restore time honestly

Boat bills each second a sandbox runs, from `provisioned` on. A
deleted sandbox costs nothing more. Pool Boxes use `--no-auto-stop`
with `archiveAfter=null`, verified at provision. They bill 24 hours a
day, including idle time. Report idle cost as its own line. Add restore
and download time to each job cost. A 6-minute `small` run costs about
$0.002 at $0.018/h. Check `boat limits` before a batch and pace starts
to the plan minute limit. A refused start does not count. A
`boat run --from <snapshot>` job that the runner host kills still stops
by itself within 15 minutes.

## Required future work (audited gaps, not installed behavior)

Read against `boat-pool` and `boat-runner-agent` on this branch. Each
item needs an issue before implementation.

- Gate the runner on hydration. The agent starts `run.sh` at once. It
  never waits for `docker info`, the service, or `hydrated=true`.
- Bound infrastructure retries. The agent retries broker operations
  every 5 seconds with no cap. Cap retries and surface repeated
  failure. Never retry test failures.
- Add a TTL tick and watchdog. Pool Boxes run with auto-stop off by
  design, so no TTL safeguard is enabled. `heal` replaces only inactive
  agents. Nothing reaps a wedged Box or ticks a deadline.
- Deregister dead agents. `heal` provisions a replacement, then deletes
  the old Box. It never deregisters the dead runner first. Replace
  means deregister, then delete.
- Pin locale, apt mode, git floor, and unit `PATH`. The provision
  script sets none of these. Add `LC_ALL=C.UTF-8`,
  `DEBIAN_FRONTEND=noninteractive`, a minimum git version, and an
  explicit `PATH` in the unit.
- Cap start quota and budget client-side. `up` loops serially with a
  count of 1 to 20 and no quota or budget check. Read `boat limits`
  before a batch.
- Document broker dedupe separately. The agent recovers by re-reporting
  its persisted lease after a restart. Webhook dedupe and poll recovery
  live in [workers/boat-runners](workers/boat-runners/README.md) and
  are not audited here.
