# CI optimization playbook

Use this procedure before changing runners, test gates, or deployment triggers.
Record measured results separately from estimates. A faster check is not always a cheaper release.

Start with the [diagnosis skill](https://github.com/pooriaarab/skills/blob/main/ci-speed-diagnosis/SKILL.md)
and the four diagnosis commands in [README](README.md#diagnose-ci-in-this-order).
This guide proposes experiments. It does not override repository merge or release rules.

## 1. Establish the baseline

Inventory every trigger: pushes, pull requests, comments, schedules, merge events,
manual runs, reusable workflows, and provider Git integrations.
Include Cloudflare Pages branch controls and Workers deployment integrations.
A workflow edit cannot disable a separate provider build.
Classify repositories without Cloudflare as such. Do not add infrastructure to satisfy an audit.

For each job, record queue time, checkout, install, restore, build, tests,
cache save, deployment, verification, and cleanup.
Find the actual dependency critical path. Summed parallel job durations are not wall time.
Compare equivalent workloads on the same source, tools, runner size, and cache state.

Record these measures separately:

- PR feedback and ready-to-merge latency: median and tail wall time.
- Runner usage: summed execution seconds, idle capacity, and cancelled work.
- Actual charges: invoices or billing exports, rounding, storage, and network transfer.
- Release quality: escaped defects, recovery time, rollbacks, and repair work.
- Cost per successfully released change: all experiment and operational costs divided by successful changes.

Define a successful change and observation window before the experiment.
Include failed attempts, LLM reviews, agent repair, cloud builds, and operator time.
Report labor separately when its monetary value is unknown.
Do not infer billed savings from elapsed time or fewer test cases.

For an estimate, let each of `n` revisions run cheap work `C` and heavy work `H`.
Running heavy work only for `k` candidates gives estimated compute reduction:

```text
baseline / candidate = n(C + H) / (nC + kH)
```

This assumes equal job sizes and excludes queue, retry, transfer, idle, and repair costs.
It predicts compute, not release latency or quality. Label it as an estimate.

## 2. Remove obsolete and duplicate work

Group superseded checks by PR or candidate identity. Cancel computation before external mutations start.
Avoid duplicate push and PR runs for the same intended check.
Consolidate tiny checks when checkout and scheduling cost more than useful work.
Keep independent failures visible in the final verdict.

Coalesce pending deployment requests. Let an active state-changing deployment finish safely.
Do not cancel migrations, publication, or production changes halfway through.
Move preparation outside a shared publication lock only when its output is immutable.
Keep the short mutation section serialized when resources are shared.

Measure checkout depth and sparse paths. Preserve history needed by change selection and release tools.
A reused checkout can retain an old sparse specification. Reset it before the next job.

## 3. Cache only when reuse wins

Compare restore plus save time with a clean frozen-lockfile install.
A green cache action does not prove a hit or a speed gain.
Measure misses, cold runs, archive size, eviction, and transfer geography.
A fast package download store can beat a large remote archive.

Key reusable data on relevant lockfiles, tool versions, platform, architecture,
configuration, and input shape. Avoid broad fallback keys for compiled outputs.
Separate dependency stores, build outputs, and test results: they have different contracts.
Never treat cached passing browser results as current verification without a complete input contract.

On Linux, package stores and workspaces on the same filesystem can support hardlinks.
Verify the pinned package manager's behavior. Cross-device copies can remove the benefit.
Share read-only tool installations where supported. Give concurrent jobs separate writable homes and stores.
Do not cache secrets, auth state, tenant data, or mutable test databases.
See [GitHub dependency caching](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching).

## 4. Select tests with evidence

Build a dependency graph from changed files to tests, including configuration,
shared fixtures, generated inputs, dynamic loading, and cross-package imports.
Unknown dependencies or graph failures must select the full suite.
Keep a periodic full-suite comparison while selection runs in advisory mode.

Write failure controls before implementing the selector.
Inject representative faults into production-shaped code, without changing expected assertions.
Confirm selected and full executions detect the same fault identities.
A successful mock child command does not prove the real execution path works.

Compare actual case names, statuses, skips, retries, suite errors, and process exits.
Reject missing, stale, truncated, malformed, or inconsistent reports.
An empty report or skipped suite is not a passing test run.
Preserve raw results and the exact base, head, tools, and selector version.
Promote selection only after representative controls and repeated full comparisons pass.

## 5. Make browser parallelism real

Give each shard an isolated server, database state, ports, inspector port,
auth identity, writable home, and artifact directory.
Separate browser contexts alone do not isolate server state.
Prove isolation with both controls: separate databases pass; intentionally shared state exposes interference.
The shared control must reach authenticated requests before its expected assertion fails.

Cap workers explicitly. Runtime CPU detection can see more CPUs than the assigned quota.
Measure setup, build, server readiness, tests, and cleanup separately.
Parallel tests can lose when duplicated setup dominates.
Audit retries, unconditional skips, weak assertions, sleeps, and duplicated coverage.
Keep meaningful business flows, including failure paths.

Own every child process group. Witness that it is alive before claiming later absence proves cleanup.
Bound startup, execution, process observation, termination, and drain time.
Treat `ESRCH` as gone. Treat `EPERM` or an unknown probe as unresolved.
Retain cleanup diagnostics when refactoring. Free ports alone do not prove all descendants stopped.
Pin tools and run platform-specific controls; shell exit codes and file limits can differ.

## 6. Build once when inputs match

Record inputs before the real build starts. Bind the output to that successful build receipt.
Do not retroactively declare an existing output equivalent.
Include source bytes, file modes, symlink targets, lockfiles, tool versions,
platform, build command, configuration, compile flags, and relevant environment inputs.
A Git index or commit label does not describe modified working files.
Keep sensitive values out of published receipts. Protect even hashes of low-entropy secrets.

Hash every nested field with deterministic serialization. Test nested tampering explicitly.
Compare actual installed tools and actual consumer inputs before installation or output writes.
Reject unknown fields, missing inputs, dangling links, and paths outside the owned destination.
Check physical paths before writes. Preserve outside targets in link-escape controls.
Version the receipt protocol so old formats cannot silently pass new validation.

Retire the producer path, then boot fresh consumers from relocated output.
Verify assets, generated imports, WASM, and real browser flows.
Use relative output paths only where the runtime supports them.
Give each consumer independent writable state. Test the shared-state negative separately.
Record extraction, verification, and install costs as part of reuse.

## 7. Match runner capacity to demand

Preinstall stable tools in a versioned image or snapshot when setup cost justifies it.
Separate lightweight checks, heavy builds, and Docker workloads into measured pools.
Use ephemeral JIT runners for jobs where supported. Clean and deregister failed runners.
Set capacity bounds, idle shutdown, and a TTL safety net.
Poll queued work as a webhook fallback; deduplicate deliveries.
Retry infrastructure loss only after distinguishing it from a real test failure.

Start with explicit CPU and memory limits. Test oversubscription against pressure, latency, and flake rates.
Do not assume Kubernetes or extra runners reduce total cost.
Measure peak demand and idle billing before adding capacity.
Public hosted jobs can have different economics from private jobs.
Check current plan features before proposing a native GitHub merge queue.
See [self-hosted runner guidance](https://docs.github.com/en/actions/reference/runners/self-hosted-runners).

For Boat operations, read [boat-runners.md](boat-runners.md) and current provider documentation.
The operational checklist also includes hydration before heavy work and optional health fields,
small snapshots, scratch exclusions, per-job homes, stable paths, locale, noninteractive apt,
service PATH, and a consistent `PLAYWRIGHT_BROWSERS_PATH` at install and execution.
Validate readiness against the current API schema. Missing health is not necessarily degraded health.
Keep a TTL safety net and respect account start budgets.
Stage an allowlisted source tree before upload; unignored secrets can otherwise travel with the checkout.
Do not put job workspaces or credentials in toolchain snapshots.
See [Boat documentation](https://docs.boat.dev/quickstart).

## 8. Move previews and testing deliberately

A main-only Cloudflare preview is a staging deployment, not a per-PR environment.
Inventory workflow and provider-side branch controls before changing either.
Disable PR previews only after the replacement verification gate works.
Update repository operator rules in the same approved policy migration.
Until then, existing local CI, review, and Preview requirements still apply.

Use these stages for a bounded experiment:

1. Keep cheap PR checks and local verification. Run expensive checks once when a candidate is ready to merge.
2. For approved low-risk changes, test after merge and before production deployment.
3. Build an immutable candidate from an exact source revision. Test that candidate in isolated staging.
4. Promote the verified artifact or version. Reject promotion when its identity differs from the tested candidate.
5. Keep the previous production version available. Measure health and recover under a documented policy.

Prevent another main update from moving the shared staging target during tests.
A mutable staging URL answering successfully does not identify the tested revision.
Keep tenant data isolated and protect staging access.
Do not skip deployment verification for auth, payments, webhooks, or migrations.
Rollback cannot always undo database changes or external side effects; plan those separately.
See [Cloudflare branch controls](https://developers.cloudflare.com/pages/configuration/branch-build-controls/).

One current LLM approval can satisfy a repository's review rule. Read findings from all reviewers.
LLM-only verification has no assumed quality equivalence with executed tests.
Removing PRs also removes a review and audit surface; replace those functions explicitly before adoption.
Anthropic describes post-merge/pre-deploy testing while retaining review, simulations, telemetry, and recovery systems.
Its [source-control report](https://www.anthropic.com/engineering/redesigning-source-control)
is evidence for an architecture to evaluate, not proof that another repository can remove its checks.

## 9. Accept, roll back, or stop

Run at least three repeated baseline/candidate pairs on equivalent source and tools.
Three phases of one run are not three pairs. Record cache order and host variation.
Alternate order where feasible. Report each pair and the median.
Three pairs cannot establish reliable p95 latency. Label tail observations exploratory until the sample size supports them.
Keep billing exports separate from wall-time measurements. State missing billing data explicitly.
Compare escaped defects and repair work over the same observation window.

Promote one change at a time with a rollback switch and a named owner.
Stop when cleanup, report completeness, identity, or quality controls fail.
Do not promise a 5–10x gain. Publish the measured result and its limits.

For a recurring audit, use this prompt:

> Read the last matched baseline and current workflow inventory. Rank queue time,
> critical-path latency, billed usage, cancelled work, and release defects separately.
> Check cache effectiveness, idle runners, duplicate triggers, test selection fallbacks,
> staging identity, and cleanup failures. Propose one bounded change with a failure control,
> matched measurement plan, and rollback. Do not change infrastructure, spend limits,
> deployment policy, or schedules without authorization. Report uncertainties and stop.

A saved prompt is not an active schedule. Report its cadence and next run only after scheduling it.
