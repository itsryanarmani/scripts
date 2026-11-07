<!-- issue-standards:start -->

## Issues

One job. One issue. Sized before it is written. Routed to a tier.

Open the issue before the branch. It is where scope is agreed, and its number is
what ties the branch, the pull request and the merged commit together.

Every issue carries the same spine: job to be done, today and wanted, acceptance
criteria, how to verify. Acceptance criteria are testable and each is true or
false. "Improve the loading state" is not a criterion.

Four forms in `.github/ISSUE_TEMPLATE/`: bug, feature, chore, epic. A bug needs a
reproduction, and a failing test is welcome but not required. A feature needs a
success metric naming a real event through the analytics helper named in
`.agents/issues.md`, or saying plainly that the event has to be added.

Declare a size first: `mini`, `standard` or `deep`. A section that is not
required is not written, because an empty heading looks answered.

Every issue carries exactly one label from each of four groups: kind, size,
route, state. GitHub issue types are an organisation feature and this account is
a user, so labels carry classification.

The `route:` label says which agent tier implements it. Anything touching a
high-stakes path is `route:judgement` whatever its size.

Parents are sub-issues and blockers are issue dependencies, both native. Do not
write `Parent: #NNNN` in the body.

Repo context for issue writers, including the high-stakes paths and the
analytics helper to cite, is in `.agents/issues.md`. The standard is at
https://github.com/itsryanarmani/scripts/blob/main/issue-standards.md

<!-- issue-standards:end -->
