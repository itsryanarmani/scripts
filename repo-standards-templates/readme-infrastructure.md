<!--
Fill every __PLACEHOLDER__. Delete this comment first. It is the first thing
you delete before shipping. A leftover placeholder is a claim that is not
true, and the reader will believe it. No banner, no pitch, no badges beyond
CI. This file is for the person who operates it at 2am.
-->

# __REPO__

[![CI](https://github.com/__OWNER__/__REPO__/actions/workflows/__WORKFLOW__.yml/badge.svg)](https://github.com/__OWNER__/__REPO__/actions)

<!-- for example: `repo-standards` is the workflow that checks a README on every pull request that touches one. -->
`__REPO__` is the `__WHAT__` that runs `__WHEN__`.

## Failure modes

<!-- for example: `codeload` 403 means `itsryanarmani/scripts` went private — restore public or add an auth header. -->
<!-- for example: a queued Boat job can mean no pool slot is free. Check the broker and pool. -->
<!-- for example: a grey Shields badge on a private repo is "not found", not a dead project. -->
| What you will see | Cause | What to do |
|---|---|---|
| `__FAILURE_1__` | `__FAILURE_1_CAUSE__` | `__FAILURE_1_FIX__` |
| `__FAILURE_2__` | `__FAILURE_2_CAUSE__` | `__FAILURE_2_FIX__` |
| `__FAILURE_3__` | `__FAILURE_3_CAUSE__` | `__FAILURE_3_FIX__` |

<!-- for example: this workflow costs about `__COST__` / month at the current fleet size. A retry loop that hits the GitHub API on every repo will take the quota down with it. -->
> [!IMPORTANT]
> `__COST_WARNING__`

## Install

```bash
# for example: copy .github/workflows/__WORKFLOW__.yml from this repo and pin repo-standards-v1
__INSTALL_COMMAND__
```

One supported way.

## Quick start

```bash
__QUICK_START__
```

<!-- for example: repo-standards check .  ->  0 findings -->
```
__QUICK_START_OUTPUT__
```

## Why

<!-- for example: not a single-repo toy and not a replacement for reading the README. -->
For __WHO__, who today uses __ALTERNATIVE__. Not for __WHO_NOT__.

## Usage

<!-- for example: on every PR that touches `README.md`, about 12s on `boat` in a private repo, or `ubuntu-latest` in a public repo. -->
<!-- for example: nightly on `main`, about `__NIGHTLY_MINUTES__` across the fleet. -->
| When | What runs | What it costs |
|---|---|---|
| `__WHEN_1__` | `__RUNS_1__` | `__COST_1__` |
| `__WHEN_2__` | `__RUNS_2__` | `__COST_2__` |

## How it works

<!-- for example: CI fetches the engine from `itsryanarmani/scripts` at tag `__PIN__`, then `repo-standards check .` fails the job on a finding. -->
__HOW_IT_WORKS__

## Contributing

See [CONTRIBUTING.md](https://github.com/itsryanarmani/.github/blob/main/CONTRIBUTING.md).

## License

[__LICENSE__](LICENSE)
