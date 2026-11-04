# Boat pool cost proposal

Status: proposal only. The pool stays unchanged. No autoscaler is installed.

## Observation and limit

A read-only sample on 2026-10-16 finds 18 standard and four large pool Boxes.
All four large slots run actual GitHub jobs. Large jobs queue while standard
capacity stays idle. Labels separate the tiers; spare standard slots cannot
run `boat-8` jobs.

The broker leases a job, then registers a repository runner with a label.
GitHub can assign another matching job. A lease job ID is not proof of the
runner's actual job. `/status` open and claimed counts are advisory.

The current [pool tool](boat-pool), [agent](boat-runner-agent), and
[broker](workers/boat-runners/src/index.ts) cannot safely activate shrinking:

- `boat-pool down` checks pool membership, but does not check busy jobs.
- `heal` checks the agent service, not the runner's actual job.
- The agent can take another lease after any idle observation.
- No drain handshake prevents that race. A stopped service kills its group.

Do not use `down`, `heal`, or a service restart to implement this proposal.
Keep the existing lease acknowledgement and cleanup guards unchanged.

## Proposed policy, disabled

| Parameter | Proposed value | Meaning |
| --- | ---: | --- |
| Standard warm floor | 2 | Healthy idle `boat` slots |
| Large warm floor | 1 | Healthy idle `boat-8` slots |
| Standard weight | 1 | Default-equivalent online capacity |
| Large weight | 2 | Default-equivalent online capacity |
| Online ceiling | 26 | No growth above the sampled pool's weighted size |
| Snapshot age limit | 60 seconds | Older or incomplete state blocks planning |
| Scale-out batch | 1 Box | Reobserve after each start completes |
| Idle cooldown | 15 minutes | Continuous confirmed idle time before draining |
| Poll interval | 30 seconds | Proposal; no timer is installed |

The floor reserves idle capacity above busy jobs. For each tier, calculate
`desired = busy + max(warm_floor, runnable_queued)`.
Only queued jobs whose dependencies have completed count as runnable demand.
A start needs runnable demand or a warm-floor deficit, with capacity below `desired`.
Reserve its tier weight before starting it. Count starting Boxes against the
ceiling. Release a reservation only after a confirmed failure or deletion.

Prioritize the oldest runnable job when both tiers need capacity. Never borrow
standard headroom by terminating busy work. At the ceiling, keep jobs queued
and report their ages. If busy capacity already exceeds the ceiling, freeze
new starts. Let existing work complete.

The ceiling limits online capacity, not monthly spend. A dollar budget also
needs a time window, accumulated weighted seconds, current credit terms, and
a forecast. Before growth, reserve the proposed Box's weighted seconds for
that window. When the budget is exhausted, deny growth and report the limit.
Do not stop busy jobs to satisfy a changed budget or floor.

## Actual-state requirements

Collect one complete observation with start and finish times. Preserve raw
records outside Git. Reject failed pages, unknown Boxes, missing IDs, clock
skew, duplicate identities, and a collection window above 60 seconds.

Match each pool Box to its local lease's repository and runner ID. Read the
repository's actual runner `busy` flag and jobs assigned to that runner ID.
Accept old and nested lease formats. Never export the encoded JIT config.

Treat a Box as protected if any actual job is in progress, its runner is busy,
its job-start marker exists, or local/GitHub states disagree. A missing record
is unknown, not idle. Exclude non-pool Boxes and public repositories.

Track continuous idle time across observations. Reset it on any work, restart,
missing observation, state conflict, or failed API page. Box state `idle` and
an active agent service do not establish runner idleness.

Shrinking requires a reviewed drain handshake. It must block new leases,
acknowledge that state, wait for actual work and cleanup acknowledgement, and
recheck runner/job state immediately before deletion. Any uncertainty cancels
deletion. Removing the drain restores the agent's existing lease loop.

## Cost worksheet

The sample records 100,000 default-equivalent credit seconds per dollar and
a 2x large multiplier. These are observed credit terms, not an invoice model.
Refresh them before approval. Included credits, subscriptions, other Boxes,
startup time, bursts, and actual utilization change the final bill.

| Idle capacity | Weighted slots | Credit seconds/hour | Credit dollars/hour |
| --- | ---: | ---: | ---: |
| Sampled 18 standard + 4 large | 26 | 93,600 | 0.936 |
| Proposed 2 standard + 1 large | 4 | 14,400 | 0.144 |
| Theoretical idle difference | 22 | 79,200 | 0.792 |

`26 / 4 = 6.5`: this is a theoretical idle-floor reduction, not CI speed or
invoice savings. The floor-only reduction is about 84.6%. At 24 idle hours,
the credit difference is $19.008. Do not multiply that by a month and call it
savings. Demand above the floor consumes extra capacity.

For a measured interval, sum `online_seconds * tier_weight` for every pool Box.
Divide by the refreshed credit-seconds-per-dollar rate for credit consumption.
Report queue wait, job execution, summed job machine-seconds, online pool
seconds, and billing records separately. Retain before/after observations
with comparable workload and burst size.

## Review commands available now

These commands inspect or print a plan. They do not activate this policy:

```sh
./boat-pool --help
./boat-pool up boat 1 --dry-run
./boat-pool up boat-8 1 --dry-run
```

With existing broker credentials in the operator shell, `./boat-pool status`
reads Boxes, agent services, and advisory broker counts. Do not print those
credentials or use status counts as the busy-job source.

For a known private repository, these existing GitHub calls read actual state:

```sh
gh api --paginate 'repos/pooriaarab/REPO/actions/runners?per_page=100'
gh api --paginate 'repos/pooriaarab/REPO/actions/runs/RUN_ID/jobs?per_page=100'
```

Replace the identifiers from the complete inventory. Two example calls do not
establish complete fleet coverage. Never pass a token in command arguments.

## Activation and rollback review

Activation has no command today. Do not schedule `heal` or wrap `down` in a
loop. A separate implementation must provide the collector, read-only planner,
durable reservations, drain handshake, and an explicit disabled default.
Its PR must document its real activation and rollback commands.

First run that planner without mutation through a full burst and idle period.
Compare every protected Box with actual runner/job records. Obtain operator
approval for the exact ceiling, budget window, observation period, and drain
implementation before activating it. Start with growth only. Approve shrinking
separately after drain proofs pass.

Rollback must disable new capacity decisions without restarting agents. Keep
busy Boxes and complete cleanup. Restore the previous 18/4 target only after
checking actual capacity and budget; add only missing slots. Do not treat this
historical target as a permanent requirement. Drain newly added surplus slots
only with the same reviewed handshake. This PR creates nothing to roll back.

## Failure cases required before controller code

Use CLI fixtures before implementation. Save the command output as an artifact.
Require these outcomes:

- Stale, future, partial, or conflicting state produces no capacity actions.
- A lease points to queued job A while its runner executes B: protect the Box.
- Any busy flag, actual running job, or job-start marker prevents deletion.
- Standard and large slots consume one and two capacity units respectively.
- Existing and pending starts cannot exceed the weighted ceiling or budget.
- A budget below current usage blocks starts and preserves busy work.
- A large backlog with idle standard capacity proposes large growth only.
- Unknown runner state never starts an idle cooldown.
- Interrupted idleness resets the full 15-minute cooldown.
- A lease acquired between observation and drain acknowledgement cancels removal.
- API or process failure leaves reservations and protected work recoverable.
- Policy disable stops decisions while runner jobs and cleanup continue.
