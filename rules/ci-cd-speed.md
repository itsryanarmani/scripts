# CI/CD speed

Rules from a one-day CI/CD campaign. Measure the whole path before changing it.
The numbers below describe those runs, not expected savings on another runner.

## Measure first

1. As a starting point, audit the last 100–150 runs. Split time into queue wait, setup, and execution.
   Deduplicate rerun copies by job name, runner, start time, and end time.
   Calculate percentiles from successful runs only. Report failures separately.
2. Measure cache restore cost on the real runner before adding a cache.
   A per-site compiler cache took a median 24 s to restore, against about 8 s
   of build time saved.
   A browser cache saved about 0 s. A cache hit is not a saving.
3. Never key a cache with many writers on the commit SHA. Each commit adds
   another copy against the 10 GB quota and pushes useful entries out.
4. One projected saving was revised downward twice and then measured as a loss.
   Quote measured numbers only.

## Shorten the path

1. Gate the expensive matrix on the cheap check with `needs`. Do not add
   `always()` to that dependency: it lets expensive work run after the gate fails.
2. Set step timeouts on network steps. A hung install burned 75 min.
   The longest healthy install took 46 s, so the install timeout became 5 min.
   Keep the job timeout as a second limit.
3. A Rust port of the TypeScript compiler cut typecheck from 34.5 s to 2.5 s.
   Use a parity script before switching. Check both results on the same inputs.
   Record a version stamp so a later run identifies the compiler it used.
4. Give small required gate jobs a hosted runner or a separate runner lane.
   A short check still blocks the PR when it queues behind a long matrix.

## Keep checks useful

1. Classify red scheduled runs before optimising them. Separate setup failures,
   test failures, cancelled runs, and queue delays.
2. Skip an unchanged scheduled suite only after its last gate reports SUCCESS
   and is under 24 h old. Missing, stale, or failed evidence must run the suite.
3. Test selection based on changed files must widen on anything unknown.
   Run the full suite when a path, dependency, or change cannot be classified.
   Mutation-test the selection check itself. Prove it catches a deliberately
   broken case rather than trusting its green result.

## Roll out once

Use one rollout tool for the fleet and reusable workflows for shared steps.
Open one reviewed PR per repository. Make dry run the default and cap each batch.
Never run target repository code from the rollout tool.
Allow only named environments and approved runner pins through explicit allowlists.
