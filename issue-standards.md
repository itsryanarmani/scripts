# Issue standards for an agent fleet

`pr-standards.md` governs the change. This document governs the request that
justified it.

The two are one system. A pull request must close exactly one issue, so the
issue is where scope is actually agreed. An unclear issue does not produce an
unclear PR; it produces a PR that closes cleanly against the wrong thing, and
the checker cannot see the difference.

This document is the standard. `issue-standards` is the program that enforces
what a program can enforce.

## The rule

**One job. One issue. Sized before it is written. Routed to a tier.**

Everything below is that sentence, made checkable.

## The spine

Four sections, required in every issue whatever its kind or size.

    ## Job to be done
    One or two sentences, in the voice of whoever is blocked. What they cannot
    do today.

    ## Today / Wanted
    Today: what the product does now.
    Wanted: what it must do instead.

    ## Acceptance criteria
    - [ ] Each one independently testable.
    - [ ] Each one true or false, never "better" or "cleaner".

    ## How to verify
    Steps, then the expected result. Concrete enough for someone who has not
    read the code.

`Job to be done` is the section agents skip and the one that matters most. Write
what is blocked, not what to build. An issue that opens with a solution has
already thrown away what you need to check the solution against.

`Acceptance criteria` is the contract the PR is measured against. "Improve the
loading state" is not a criterion because no one can be wrong about it. "The
skeleton renders within 100ms of navigation" is.

## The kinds

Four, each a delta on the spine. The kind is a label, not a heading.

### bug

Replaces `Job to be done` with `Impact`, and adds:

    ## Reproduction
    1. Concrete steps.
    2. Expected: what should happen.
    3. Actual: what happens instead.
    Environment: browser, account, plan, workspace.

    ## Last known good
    The commit, release, or date it last worked. "Never worked" is an answer.

A reproduction is required. A failing test is requested and not required,
because most bugs are filed from a screenshot by someone who cannot write one.
The PR that fixes the bug carries that burden instead: it shows the test failing
before and passing after. That is a `pr-standards` obligation, not an issue one.

A bug carries no success metric. A fixed error rate is a regression guard, not a
metric — the bug is closed when the behaviour is correct, and monitoring only
tells you it stayed that way.

### feature

Adds:

    ## Success metric
    Event:     the real analytics event name, or the event to be added
    Question:  what the number answers
    Threshold: the value that means this worked, and the window

Name a real event. If the event does not exist yet, say so in those words and
treat adding it as part of the work. An invented event name is worse than an
absent section, because the next agent will search for it and conclude the code
is broken.

Repos differ in which analytics client is authoritative. That belongs in the
repo's `.agents/issues.md`, not here.

### chore

The spine only. Refactors, dependency bumps, CI, docs, cleanup.

Deliberately thin. A chore with a success metric is a feature wearing a
disguise, and should be relabelled rather than padded.

### epic

    ## Job to be done
    ## Slices
    ## Out of scope

An epic has no acceptance criteria of its own. Its children carry them, and an
epic that needs its own criteria has not been decomposed yet.

Each slice becomes a real sub-issue through the GitHub sub-issues API, and each
slice must be shippable alone. A slice that only makes sense merged with its
siblings is a slice boundary drawn in the wrong place.

## Sizing

Declare the size in one line before writing the body. This is the only defence
against a template that inflates a typo fix into a specification.

| Size | What it is | What the issue carries |
|---|---|---|
| `mini` | One string, one config value, a narrow rename, an obvious fix | `Job to be done` and one or two verify steps. Nothing else. |
| `standard` | A bounded change in one area, one user-visible flow | The full spine, each section tight |
| `deep` | Multiple surfaces, a new system, a data migration | The spine plus the conditional sections that fire |

Guessing wrong is cheap and correcting is cheaper. When unsure, write
`standard` and adjust once you have read the code.

**A section that is not required is not written.** This is the rule that keeps
issues readable, and the one an agent will break first, because filling a
heading feels like progress. An empty heading is worse than a missing one: it
looks answered.

## Conditional sections

Each has a trigger. Absent the trigger, the section does not appear. All of them
go inside a `<details>` collapsible so the issue stays skimmable.

| Section | Written only when |
|---|---|
| Edge cases | More than one non-obvious case exists. A table: `Case \| Expected`. |
| Flow | The path branches, or runs to more than three steps. A mermaid diagram. |
| Out of scope | A reviewer would otherwise widen the change. |
| Grounding | The issue asserts how the code works. Then it cites `file:line`. |
| Rate limits and cost | The feature calls a metered third-party API. |

`<details>` is correct for GitHub, which renders it natively. Linear needs `+++`
fences instead. Do not carry one tracker's syntax into the other.

### Grounding

Any claim about how the product works today must point at a real file and line.
An agent that has codebase access and writes "the system currently retries
three times" without checking has invented a fact that the next agent will
build on.

If a section would say `N/A`, either delete it or show the search that proves
the absence.

## Labels

GitHub issue **types** are an organisation feature. `itsryanarmani` is a user
account, so `/orgs/itsryanarmani/issue-types` returns 404 and types are
unavailable. Labels carry classification instead, in three groups.

| Group | Labels | Rule |
|---|---|---|
| Kind | `bug` `feature` `chore` `epic` | Exactly one |
| Size | `mini` `standard` `deep` | Exactly one |
| Route | `route:mechanical` `route:scoped` `route:judgement` | Exactly one |
| State | `triage` `ready-for-agent` `needs-info` `blocked` | Exactly one |

Every issue carries exactly four labels, one from each group. More than one from
a group is a contradiction, not extra information.

## Fields

| Field | Rule |
|---|---|
| Labels | Exactly one from each of four groups. Specified above. |
| Project | At most one, from the set named in the repo .agents/issues.md. Never create one. |
| Milestone | At most one, from the milestones that already exist. Never create one. |
| Relationships | A parent is a sub-issue. A blocker is an issue dependency. Never prose. |
| Assignee | An agent never sets this. |

The enumerated sets live in the repo `.agents/issues.md` beside the labels. A project name is repo-specific and cannot be derived from outside the repo.

A field is checked only where the repo defines a set for it. Zero milestones exist across the fleet today, so a rule that always required one would fail every issue on day one and get the standard switched off. `requireProof` in `pr-standards` already works this way.

A parent is a sub-issue and a blocker is an issue dependency, never prose. This covers `Depends on` as well as `Parent:` and `Blocked by:`. Ten phase epics in `private-repo-c4e6` say `Depends on Phase 10` in prose while carrying zero real dependencies, which is the failure this rule exists to stop.

An agent never sets an assignee, because assignment is a person deciding who does the work.

## Sub-issues and dependencies

Both are native GitHub features and both work on private repos on this account,
verified against the API.

- A parent link is a **sub-issue**, created through the sub-issues API.
- A blocker is an **issue dependency**, not a sentence in the body.

The `Parent: #NNNN` and `Blocked by: #NNNN` body conventions are deleted. Body
text is invisible to every query, filter and board that would otherwise show you
the shape of the work. A parent written in prose is a parent that no tool knows
about.

## Routing

An issue declares which tier of agent should implement it, as a `route:` label.

The tier is **derived from the issue, not guessed about it**:

| Tier | When |
|---|---|
| `route:mechanical` | `chore` or `mini`, every acceptance criterion mechanically checkable, and no high-stakes path touched |
| `route:scoped` | `standard`, one area, needs judgement about the codebase |
| `route:judgement` | `deep`, cross-cutting, a migration, **or any high-stakes path at any size** |

The last clause overrides the other two. A one-line change to authentication,
billing, credit accounting, or a data migration routes to `route:judgement`
however small it looks. Size measures the diff, not the cost of getting it
wrong.

Each repo lists its own high-stakes paths in `.agents/issues.md`. The list is
repo-specific and cannot live here.

### Where the model names live

**Not in this document, and not in any issue.** Tier names are durable; model
names are not. The roster lives in `agent-routing.json`, one file, so retuning
after a model ships is one edit rather than 88.

An issue that names a model is out of date the week after it is filed.

### Routing is a default, not a verdict

A worker that stalls escalates one tier and records that it did. That record is
the point: it is evidence the tier was wrong.

The loop closes on measurement. The issue declares a tier, the worker implements
it, the PR carries its `Assisted-by: <agent>:<model>` trailer, and
`agent-defect-rate` reports the defect rate per agent from merged PRs. Retune
`agent-routing.json` from those rates.

Route by measured defect rate, never by how hard the work felt.

## What a program can check

`issue-standards` checks shape. It cannot check whether the issue is worth doing.

    issue-standards check --repo owner/name --number N
    issue-standards precheck --body-file F --kind feature   # offline, for a hook
    issue-standards lint                                    # templates have not drifted

Checked:

- The required headings for the declared kind are present and non-empty.
- Acceptance criteria are a checkbox list with at least one item.
- Exactly one label from each of the four groups.
- No `Parent:` or `Blocked by:` body line, which means a native link was missed.
- A `feature` names an event in `Success metric`.
- A conditional section that appears is not empty.

Not checked, and left to a reviewer:

- Whether the job to be done is real.
- Whether the acceptance criteria actually cover the job.
- Whether the size and route are honest.

A checker that claimed to judge these would be believed, and it would be wrong.

## Enforcement

Two layers. Be precise about what each buys.

1. **A PreToolUse hook** refuses `gh issue create` when the body fails
   `precheck`. Fastest feedback, and it stops a thin issue before it exists.
2. **A CI workflow** on `issues: [opened, edited]` comments what is missing.

There is no third layer, because there cannot be one. Required status checks on
private repos need GitHub Pro, and this account is on Free. Issues have no
merge gate to attach to even with Pro.

So on issues the check is **advice, not a gate**. The hook is skipped by any
agent whose harness never loaded it. Bypassing these is a decision, not a
shortcut, and nothing but this sentence stops you.

## Filing from a review

A `vibecodereview` finding that is not fixed in the PR becomes an issue, carrying
the review's evidence and the `triage` label.

Filed, not scheduled. Triage decides whether it is worth doing. Auto-filing
without auto-ranking preserves the finding at the moment it was cheap to
capture, and defers the cost of acting on it, which is the only part that was
ever expensive.

## Common mistakes

- Opening with a solution, so `Job to be done` records a decision instead of a problem.
- Acceptance criteria no one can fail: "improve", "clean up", "make it better".
- An invented event name in `Success metric`.
- An architectural claim with no `file:line` behind it.
- Filling every heading because the template offered it.
- `Parent: #NNNN` in the body when the sub-issues API exists.
- A model name in the issue instead of a `route:` label.
- An epic with its own acceptance criteria, which means it was never decomposed.
