# Measure release CI changes

Use this runbook with the existing CI inspection tools before changing release scheduling or test selection.
It defines evidence requirements; it does not automate a critical-path calculation.

For scheduler placement, repeated builds, safe pool drains, and PR proof, use
[the CI cost controls](ci-cost-controls.md). Keep this procedure for measuring
the complete release interval.

## Record the baseline

Keep raw evidence in private storage. Job names, logs, and URLs can identify private projects.
Replace the placeholders below with an authorized repository and workflow name.
These commands read GitHub data. They require an existing authenticated `gh` session and spend API requests.

```bash
./ci-pr-latency owner/repo --event push --workflow 'Release' --limit 20 --json > latency.json
./ci-job-timings owner/repo --limit 25 --json > jobs.json
./ci-cache-health owner/repo --limit 12 --json > cache.json
./ci-runner-audit owner --json > runners.json
```

The job and cache tools sample recent runs across workflows. Filter the evidence before comparing releases.
The runner audit covers the owner's repositories. Keep its output private until reviewed.
Use each command's `--help` to confirm the installed interface.

Record these fields for each compared run:

| Field | Purpose |
| --- | --- |
| Tested source and external dependency revisions | Identify the inputs, including other repositories fetched during the run |
| Workflow revision and event | Identify gates, conditions, and selection rules |
| Run attempt and conclusion | Keep retries, cancellations, and failures visible |
| Affected target count and test identities | Detect a smaller workload masquerading as faster execution |
| Runner type, available capacity, and overlapping runs | Identify scheduling pressure |
| Cache state and artifact size | Distinguish cache effects from code changes |
| Release start and final required deployment finish | Measure the complete delivery interval |
| Per-job start and finish | Measure execution and reconstruct waits |

Use the same start and finish definitions before and after the change.
For separate test and deployment workflows, join the exact release input identity and attempts.
Do not substitute a later manual deployment's duration for the original release interval.

## Find the critical path

Read the workflow dependency graph at the tested revision, including reusable workflows and rendered matrix jobs.
A list of job durations does not contain that graph.

For a job, execution time is its finish minus its start.
Its earliest eligible time is no earlier than the latest successful required dependency finish and the applicable workflow trigger.
Approval gates, environment rules, and concurrency controls can delay eligibility further.
Label unexplained pre-start time as unresolved wait. Do not automatically call it runner queue time.

Trace dependencies and waits through the final required deployment.
The longest individual job is not necessarily the complete critical path.
Summed job execution measures machine time; it does not measure release latency or billed cost.
Use billing records for cost claims.

Check other workflows using the same runner labels during that interval.
A deployment matrix can wait behind a merge queue even when each deployment command is fast.
A lower queue cap can help releases while delaying merges, including when the pool is idle.
Report both effects. Do not claim a capacity increase from a matrix limit change alone.

## Test a proposed change

Write failure cases before implementation. Preserve the required checks and test identities.

- Independent build and planning jobs can overlap only when neither consumes the other's result or required side effect.
- Parallel deployment children must use independent state and have no ordering dependency.
- An early failing child must not prevent joining slower siblings. The parent must return failure and identify the failed child.
- A workflow parser cannot verify tests that inspect shell text. Run those tests after quoting or command changes.
- Multiple local emulators must not compete for one SQLite file without supported shared ownership.
- Prove cross-host writes when tests require a shared logical database. Separate file copies change that behavior.
- Faster helpers can expose rate limits previously hidden by process startup. Preserve production limits and isolate independent test clients.
- Selective tests need valid coverage evidence for all immutable release inputs. Unknown inputs must expand testing or stop the release.
- Pre-uploaded versions must remain inactive until their own release gate passes. Keep required migrations before promotion.

Consult the [CI skills](https://github.com/itsryanarmani/skills/tree/main/ci-speed-diagnosis)
for diagnosis and the sibling guidance for E2E state and selective execution.

## Publish a result

Compare repeated successful runs with comparable workload and capacity.
Report the sample count, measurement window, median, and range.
Report failed attempts and retry time separately; do not silently remove them from delivery results.
State changes in target count, runner capacity, or test coverage beside the timing claim.

Use a table with baseline and changed values for release latency, queue latency, and summed job execution.
Mark values that cannot be established as unknown.
Keep estimates, isolated benchmarks, and complete CI observations in separate rows.
A helper benchmark alone cannot establish a release improvement.

Before publishing, remove private repository names, domains, run URLs, commit hashes, runner names, and raw logs.
Use synthetic identifiers in examples and label synthetic data explicitly.
Do not publish exact private measurements unless the owner authorizes them.
Retain the original evidence privately so authorized reviewers can verify the claim.
