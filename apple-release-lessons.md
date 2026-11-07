# Recover and monitor an Apple release

Use these lessons with [the browser field map](apple-app-store-connect.md).
They describe observed failure modes and evidence boundaries.
They do not install a scheduler or an automatic upload pipeline.
Keep app identifiers, contacts, credentials, and raw evidence in private storage.

## Record authority for each action

Record internal testing, public submission, and public release authorization separately.
Read the latest owner instruction before each change.
A later explicit release approval can supersede an earlier release hold.
A scheduled prompt must reflect that change before its next run.
Keep manual release selected while waiting when that is the agreed workflow.
Do not mistake manual release for missing authority to release an approved version.

A release record should contain:

- App, bundle, marketing version, build number, and source commit.
- Tested archive identity and Apple's existing build identifier.
- Submission receipt, current Apple status, and last observation time.
- Authorized storefronts and separate submission and release permissions.
- Any pending release attempt and the result observed from Apple.

Keep historical receipts unchanged when repository names or owner instructions change.
Record the new current value separately.
A GitHub username change does not rename signing keys or GitHub App identities.

## Handle uncertain browser actions

A browser timeout can occur after Apple accepts a click.
Take a new snapshot and read the current server state before retrying.
Do not repeat an upload, submission, or release because a tool returns a timeout.
For a release, save the intended identity and pending attempt before the click.
Afterward, verify Apple's version state and retain the receipt.
An unresolved attempt requires a state check, not a second click.

Distinguish these effects:

| Observation | What it proves |
| --- | --- |
| Build upload completes | Apple receives the upload; processing can remain pending. |
| Build becomes VALID | Processing succeeds; tester access is a separate check. |
| Internal group contains the build | Group access exists; installation is still unverified. |
| Ready for Review | A prepared review item exists; it is not submitted. |
| Waiting for Review | Apple receives the submission; review has not started. |
| Pending Developer Release | Apple approves the version; public release remains pending. |
| Release action succeeds | Apple accepts the release; storefront visibility needs verification. |

Use [Apple's status reference](https://developer.apple.com/help/app-store-connect/reference/app-information/app-and-submission-statuses/).
Do not treat a website HTTP200 as proof of an App Store release.

## Monitor without duplicate work

Use an existing authorized read-only status observer when available.
Match its response to the intended app, version, and build.
Record each observation time and whether the state changes.
Append status history only on a real change.
Do not rebuild, rerun tests, inspect old CI, or restart stopped probes on an unchanged status.
Reuse one schedule. Do not create another schedule for the same release.

If the owner chooses email updates, pause the schedule and record that decision.
Apple offers [App Status Reports email alerts](https://developer.apple.com/help/app-store-connect/reference/account-management/user-notifications/).
Do not claim the owner's notification preference is enabled without checking it.
Stop only the workflow's own wake process after verifying PID, UID, arguments, and start time.
Never terminate unrelated wake processes.

When Apple requests information, inspect the actual message before changing the app.
[Apple explains when a reply is sufficient](https://developer.apple.com/help/app-review/after-submitting-for-review/review-status/).
Do not resubmit merely to answer a question or repair metadata when a reply suffices.
Keep fixes within the authorized scope and the repository's test and review gates.

## Preserve the audit's limits

Use PASS, FAIL, UNKNOWN, and NOT_APPLICABLE with evidence for the exact candidate.
Separate mandatory requirements from recommendations and review judgment.
Summarize the counts without converting UNKNOWN into PASS.
Update stale evidence descriptions after a corrected build or published privacy label.
Do not describe a submitted version using an earlier selected build's evidence.

A successful simulator test does not prove physical-device installation.
A SwiftUI accessibility label does not prove VoiceOver behavior.
A requested dark launch argument does not prove the app displays dark appearance.
An external-browser foreground check does not prove the entire handoff and return flow.
A later passing run does not establish the cause of an earlier failure.
Retain stopped or unavailable checks as UNKNOWN until new evidence supports a result.

Verify the complete public privacy text without an account or newsletter unlock.
Check the deployed page for injected analytics separately from the native binary.
Keep license attribution and database export obligations tied to the bundled data source.
A seed update must preserve source and license provenance.

## Diagnose local scheduler access

An interactive command can work while launchd cannot read the same file.
A protected Documents path can block the wrapper before the command starts.
Moving only the wrapper may leave credential helpers blocked by the same access boundary.
Inspect the complete runtime and credential path before proposing a repair.
Do not repeatedly start a known failing job.
Do not grant broad disk access or copy secrets merely to make a scheduler work.

Stop the failed owned job and record that automation is not installed or working.
Keep the working interactive command available.
Resolve unattended runtime and credential access through a separately reviewed design.
The [push evidence command](apple-push-evidence.md) records unsigned evidence.
Its presence does not prove that a scheduler, upload pipeline, or release pipeline runs.

## Preserve useful diagnostics and metrics

Keep build caches and diagnostic backups outside the checkout when tools scan the repository.
A moved cache can still be scanned if it remains inside that checkout.
Check ignored dependency links when a worktree resolves another checkout's packages.
A cache cleanup can expose a separate missing-package error.
Retain both failures instead of describing all failures as one cause.
Do not change tracked source to conceal a local environment problem.

Record setup, tests, archive, signed export, upload, processing, and browser work separately.
Name the command, source identity, result, duration, and artifact path.
Separate a cache hit from a full build.
Use null for unavailable token counts or provider-reported charges.
Do not estimate subscription costs as per-job spending without billing evidence.
A status check duration is not an app build duration.
Do not claim measured savings without comparable runs.
