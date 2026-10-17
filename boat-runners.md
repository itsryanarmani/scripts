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
- `./boat-pool heal --dry-run` plans replacements whenever `agent_state`
  is not exactly `active`. Omit dry-run to create replacements and remove old Boxes.
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

## Choose one sandbox per job or a JIT pool

Use one model per workload. Do not mix them in one job.

Model A runs one sandbox per CI job. It needs no pool code. Use it for
sparse jobs on any host. `boat run --from ci-base --type small --push . --
<command>` creates one sandbox, copies the checkout in, runs the command,
prints the cost, and deletes the sandbox. It exits with the command exit
code. A cancelled job also deletes the sandbox. See
[CI with Boat](https://docs.boat.dev/ci.md).

Before `--push .`, exclude secret files or push a staging directory that
contains only approved files. In a Git checkout, Boat also uploads new
files that `.gitignore` does not exclude. Outside Git, it uploads every
file except `.git`. Check for `.env` files and credentials before upload.
See [`boat push`](https://docs.boat.dev/cli-reference#boat-push-id-dir).

Model B keeps a pool of Boxes for each label. It uses `boat-pool`,
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
# Requires Bash, jq, and a client-side timeout command.
# On macOS, install coreutils and replace timeout with gtimeout.
# Set ID to the target sandbox ID before running this snippet.
: "${ID:?Set ID to the target sandbox ID}"
deadline=$((SECONDS + 300))
info='{}'
while (( SECONDS < deadline )); do
  info=$(timeout 15 boat info "$ID" --json) || exit 1
  jq -e '.sandbox.state == "ready" or .sandbox.state == "idle" or
         .sandbox.state == "running"' <<<"$info" >/dev/null || exit 1
  if jq -e '.sandbox.health == "degraded"' <<<"$info" >/dev/null; then
    exit 1
  fi
  if jq -e '.sandbox.health == "ok" and .sandbox.hydrated == true' \
      <<<"$info" >/dev/null; then
    break
  fi
  sleep 2
done
jq -e '.sandbox.health == "ok" and .sandbox.hydrated == true' \
  <<<"$info" >/dev/null || exit 1
```

Do not write job output into a restored tree before `hydrated` is
`true`. Reads wait for their own file, but early writes race the
background download. After hydration, do one targeted pass over the hot
paths to warm the OS page cache. Count this pass in the measured time.
This differs from Boat's startup playbook. The playbook records reads
only during restoration, before hydration completes. To train it, start
from a snapshot and read the intended startup files during restoration.
Wait for hydration before saving that trained snapshot. Keep heavy CI
work behind the hydration gate. See the readiness source for this
optional, separate image-training procedure.

Check degraded health through the [webhook contract](https://docs.boat.dev/webhooks).
The loop above requires healthy status and has a five-minute polling budget.
Each CLI request has a separate timeout. Missing health keeps polling;
only an explicitly healthy, hydrated response opens the gate.
Then run bounded, read-only Docker or service probes when the job needs them.
A failed probe stops setup. Do not retry the workload itself.

For machine calls such as `boat exec`, match the live error body before
retrying. The [API prose](https://docs.boat.dev/api/v1) uses
`sandbox_starting` and `sandbox_restoring`. The
[OpenAPI command description](https://docs.boat.dev/openapi/boat-v1.yaml)
still uses `boat_starting` and `boat_direct_failed`.
Only retry a response that explicitly establishes that the command did not
run. Bound the retry count and elapsed time. An ambiguous 502 can mean the
command already ran; reconcile it instead of repeating a mutation.
`boat info` is a control-plane read, not that command retry path.
Never retry a failed test command as infrastructure. Its exit code is the verdict.

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
outside `~/.cache`. Use the same `PLAYWRIGHT_BROWSERS_PATH` for installation
and the JIT runner service environment. `boat-pool install` does not set
this variable. Setting it only in `~/.bashrc` is insufficient for job shells.
Otherwise, reinstall browsers in each job. Do not tar a cache into the
snapshot to skip hydration.
That tarball downloads in full at every restore. Prefer `.boatignore`
plus reinstall, or deps installed natively in a named snapshot.

Measure cache locality before you add an Actions cache. Include lookup,
restore, extraction, upload, and fresh installation time. A miss can still
incur upload cost. Compare machine-local or nearby object storage with
GitHub storage; region and throughput need measurement. Compare matched
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
containers and new `/tmp` entries using lease metadata. Workspace deletion
is wider: it removes every non-tool `_work` entry, including older jobs.
It retains `_work/_tool`, Bun, Playwright, and Docker images.
Docker image pruning runs once a day.

Set an explicit locale and noninteractive apt in every provisioning
script (`LC_ALL=C.UTF-8`, `DEBIAN_FRONTEND=noninteractive`). Use a
modern git. Pin the unit `PATH`. None of these are installed yet. See
required future work below. Explicitly set each test runner's worker count.
CPU affinity can change `nproc` while Node or Python still sees every CPU.
Start near four vCPUs per job, then measure memory and contention.

Give concurrent jobs separate HOME directories and writable state. Keep
checkout paths stable where compiler caches include absolute paths.
Reset sparse-checkout before reuse. The existing job-start hook only
marks the runner busy; it does not reset sparse-checkout. A new JIT
runner does not clear shared machine state. Quarantine a machine when
cleanup fails instead of dispatching another lease onto uncertain state.

## Bill idle and restore time honestly

Boat bills each second a sandbox runs, from `provisioned` on. A
deleted sandbox costs nothing more. Pool Boxes use `--no-auto-stop`
with `archiveAfter=null`, verified at provision. They bill 24 hours a
day, including idle time. Report idle cost as its own line. Add restore
and download time to each job cost. A 6-minute `small` run costs about
$0.002 at $0.018/h; verify the current rate before budgeting. Check
`boat limits` before a batch. Pace creates, forks, and resumes against
all account minute, hour, and day budgets. A refused start does not count. A
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
  design, so no TTL safeguard is enabled. `heal` replaces any Box whose
  `agent_state` is not exactly `active`. Nothing reaps a wedged Box or
  ticks a deadline.
- Recover lost runners. `heal` relies on `systemctl is-active`; a
  transient systemd restart can produce a false loss. Check the actual
  runner process or cgroup and lease before replacement. Deregister the
  lost runner and reconcile its GitHub job. Retry only confirmed
  infrastructure loss, with a bounded count. Preserve real test failures.
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

- Quarantine failed cleanup. Current cleanup errors are logged without
  blocking the next lease. Add a refusal test before changing that rule.
- Isolate writable job state and reset sparse-checkout. Explicit worker
  budgets belong in each workload, not inferred from host CPU count.

## Qualify the control plane before rollout

Use queue depth and healthy capacity to set pool size. Bound both maximum
capacity and idle time. Keep a reserve in account start quotas.
Test the TTL watchdog by stopping the controller. A TTL starts at creation or resume. Boat extends it for integrated
agent activity, which does not establish activity tracking for an Actions
runner. Refresh it before expiry without allowing busy jobs to expire
during controller delays.
Check the current API schema before implementing deadline updates.

Poll queued GitHub work as well as processing webhooks. Deduplicate by
job identity and reconcile each job before dispatch. Do not treat a
webhook delivery as an exactly-once queue. Reconcile interrupted runs
before retrying; never turn test failures into infrastructure retries.

Record queue, restore, hydration, setup, build, test, export, and cleanup
phases. Compare several matched runs on the same commit and machine size.
Include idle pool time and failed capacity in total cost. The supplied
October 2026 experience report describes other repositories; its timing,
region, and bandwidth observations are not measurements of this pool.

For a vendor defect, retain timestamps, machine IDs, command versions,
raw results, and a minimal reproduction. Remove credentials from reports.
Send the report only when the owner authorizes that external message.

Sources checked on 2026-10-16. These instructions do not establish live
qualification. A new controller or image needs a real restore and failure
drill before the fleet depends on it.
