# Repo standards for an agent fleet

`issue-standards.md` governs the request. `pr-standards.md` governs the change.
This document governs the thing they both act on: the repository, and the front
door a stranger meets before they read one line of code.

The three are one system. An agent can open a correct issue, land a correct pull
request, and still leave behind a repo that nobody can identify, install, or
trust. The two existing standards make the work legible to the fleet. This one
makes the result legible to a person.

This document is the standard. `repo-standards` is the program that enforces
what a program can enforce.

## The rule

**One sentence. One command. One screen. Nothing in it that is not true.**

Everything below is that sentence, made checkable.

- **One sentence.** The repo says what it is in one sentence. The same sentence
  appears in the GitHub About panel and as the pitch in the README's front door,
  directly under the title. Two different sentences describe two different
  products, and the reader believes the one you did not mean.
- **One command.** There is one supported way to install or run it, and it sits
  in the first screen. Four alternatives are not generosity. They are a reader
  deciding which of your four paths is the one you actually test.
- **One screen.** A reader decides in the first viewport whether this is for
  them. Everything they need for that decision is above the fold.
- **Nothing in it that is not true.** Every command runs. Every badge reports
  something real. Every screenshot shows the current build. This is the only
  rule a template cannot give you, and the only one that decays on its own.

## The front door

Everything above the first `##`, in this order.

1. **Title.** A banner image, centred, with alt text. Or an `# H1` carrying the
   repo name, when there is no banner. Never both: a logo above the repo's own
   name in text is the name twice.
2. **Pitch**, centred, one sentence, no heading.
3. **Badges**, centred, one row.
4. **Language switcher**, centred. Public repos with translations only.
5. **Proof**, centred, with a caption.

Then the first `##`, which is `Contents` or `Install`.

**A kind's deltas beat this list.** An infrastructure repo carries no banner, no
pitch and no badges past CI, and a private repo carries no language switcher.
Those are not exceptions to be argued; they are stated under
[The kinds](#the-kinds) and [What private repos do differently](#what-private-repos-do-differently),
and they win.

**Proof is the part most READMEs miss.** It is a screenshot of the product
working, a terminal capture of the real command and its real output, or a
benchmark chart with a caption. It sits above the first heading, before the
reader is asked to install anything.

A survey of 26 widely-used repositories on 2026-09-14 found this is what
separates the good READMEs from the merely complete ones: `ruff` and `uv` open
with a captioned benchmark chart, `n8n`, `appwrite` and `excalidraw` with the
product interface, `gum` and `starship` with a recorded terminal. The reader
watches the thing work before deciding whether to trust it.

On a CLI, prefer the terminal capture over the banner. A logo proves nothing
about a command.

Serve a hero image in both themes, or it disappears for half your readers:

    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/hero-dark.png"/>
      <img src="assets/hero-light.png" alt="Search results, ranked by score" width="900"/>
    </picture>

A whole front door, in order:

    <p align="center">
      <img src="assets/banner.png" alt="Two terminals sharing one cursor" width="900"/>
    </p>

    <p align="center">Share a live agent coding session by URL, read-only or hands-on.</p>

    <p align="center">
      <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License MIT"/></a>
    </p>

    <p align="center">
      <a href="README.md"><b>English</b></a> ·
      <a href="docs/translations/zh.md">中文</a>
    </p>

    ## Contents

    [Install](#install) · [Usage](#usage) · [How it works](#how-it-works) · [License](#license)

### The pitch

One sentence. Under 120 characters, which is the limit the `standard-readme`
spec sets and the length GitHub's About panel shows without truncating. It names
what the thing does, and for whom.

It does not use `powerful`, `seamless`, `robust`, `blazing`, `effortless`,
`comprehensive`, or `revolutionary`. Those words survive in a README because no
reader can disagree with them, which is the same reason they carry nothing.

Write the pitch once. Paste it into the About panel unchanged.

### The contents line

One line, not a bullet list. A bullet list of eight links takes a third of the
first screen to say less than one line of the same links does.

**Only once the README passes 200 lines.** The `standard-readme` spec puts the
floor at 100; of the 26 repositories surveyed, the short ones carry none at all
well past that. A table of contents for four headings is furniture, and it
pushes the install command below the fold.

## Badges

A badge is a claim. Four kinds earn a place:

| Badge | The claim |
|---|---|
| License | You may use this, under these terms. |
| Version or release | This ships, and this is the current one. |
| CI status | The tests run, and they pass. |
| One real number | A benchmark, a provider count, a bundle size. |

Five badges is the cap, and status or version comes first, community last. A
star count is not a claim about the software.

**A dynamic badge pointed at a private repo renders a lie.** Verified
2026-09-14:

    $ gh api repos/itsryanarmani/private-repo-4944 --jq .visibility
    private

    $ curl -s "https://img.shields.io/github/v/release/itsryanarmani/private-repo-4944" | grep -o '<title>[^<]*</title>'
    <title>release: no releases or repo not found</title>

Shields cannot authenticate, so it cannot tell a private repo from a deleted
one. It does not fail loudly. It renders a grey badge that reads, to anyone
who opens that README, as a dead project. Private repos carry static badges or
none. See [What private repos do differently](#what-private-repos-do-differently).

## The spine

Required, in this order. A kind may add sections. No kind may reorder these.

    <front door>

    ## Contents
    Optional. Only once the README passes 200 lines. When present it sits here,
    between the front door and Install, and nowhere else.

    ## Install
    The one supported way, as a single code block. No prose between the reader
    and the command.

    ## Quick start
    The smallest real thing that produces visible output, and the output it
    produces. Show the result, not just the invocation.

    ## Why
    Who this is for, what it replaces, and who should not use it.

    ## Usage
    The commands, flags, or API. A table once there are more than three. On a
    CLI, one section per command with one example each reads better than a
    section called Usage.

    ## How it works
    The shape of the thing, for a reader deciding whether to trust it.

    ## Contributing
    One line and a link. The file is inherited, so the link points at
    itsryanarmani/.github, never at a relative CONTRIBUTING.md. That file is not
    in the repo and the relative link 404s.

    ## License
    One line. The SPDX name and a link to the file.

`## Why` is the section agents skip and readers need. It carries the answer to
"why not the obvious alternative". A README that never names an alternative is
written for someone who has already decided.

**`## Why` is the public face of `VISION.md`.** The repo's `VISION.md` holds
who it is for and what it is explicitly not. The README says the same thing to
a stranger, shorter. When the two disagree, `VISION.md` is right and the README
is stale.

Optional, in this order when present: `## Configuration`, `## FAQ`,
`## Troubleshooting`, `## Prior art`, `## Security`.

Wrap `## FAQ` entries in `<details>`. A reader scanning for an install command
should not scroll past nine answers to questions they have not asked yet.

## What to leave out

These appear in every README template and in almost none of the 26 surveyed
repositories. Each one costs a reader scrolling and buys nothing.

| Leave out | Because |
|---|---|
| `## About`, `## Introduction`, `## Overview` | The pitch already did it. Nobody writes these. |
| A table of contents on a short README | It pushes the install command below the fold. |
| `## Prerequisites` | It belongs inside Install, next to the command that needs it. |
| A roadmap section | It is stale within a month. A link in the nav line is enough. |
| A section pointing at `CODE_OF_CONDUCT.md` | Not one of the 26 has one. Contributing covers it. |
| "Built with love" footers | |
| Back-to-top links | Zero of the 26 use them. |
| Emoji in headings | Emoji inside a feature bullet is fine. In a heading it is noise. |
| A `--help` dump | That is the terminal's job, not the README's. |

**A feature bullet links to the page that explains it.** The README is a table
of contents with proof attached, not the manual. Once a bullet needs a
paragraph, the paragraph belongs in the docs and the bullet belongs as a link.

Two GitHub features are worth using and are widely skipped:

- `> [!IMPORTANT]` and `> [!NOTE]` alerts, for the one thing a reader must know
  before they run the install command.
- `<details><summary>` blocks, for install-variant sprawl and for an FAQ. Keep
  the common path inline and the long tail collapsed.

## The kinds

Five. The kind is a property of the repo, not a label on it.

### cli

Install shows one line to install and one line to run. Carries a terminal
capture in the first screen, showing real output, not a mock.

A `--help` dump is not usage. Show the three invocations people actually use.

### library

Install, then the smallest working code example, both in the first screen. The
example compiles and runs as written. An API table replaces prose once there is
more than one entry point. No screenshots.

### app

A screenshot of the real product doing its job sits in the first screen. The
About panel carries the live URL. `## Run it locally` is required, and it lists
every service the app needs before it starts, including the ones you have had
running since you wrote them.

### collection

Skills, prompts, commands, agent configuration. The body is an index table of
what is inside, one row per item, each linking to its own document. Install
means how to wire it into an agent CLI. Keep per-item detail in the item, never
in the README, because a README index of 28 items is the file nobody updates.

### infrastructure

Scripts, workers, GitHub Actions, runners. What it runs, when it runs, and what
it costs. No pitch, no banner, no badges beyond CI. The reader is the person who
must operate it at 2am, and they need the failure modes near the top.

## The files beside the README

### LICENSE, in every repo, always

GitHub cannot inherit a license. The default community health file
documentation is explicit: "You cannot create a default license file. License
files must be added to individual repositories so the file will be included when
a project is cloned, packaged, or downloaded."

Public repos take MIT unless there is a reason. Private repos carry one too. A
private repo that opens later has no record of what its author intended, and
reconstructing intent across years of commits is how a repo stays closed.

### The five that are inherited, from `itsryanarmani/.github`

`CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md` and
`.github/FUNDING.yml` live once, in the account's `.github` repository. GitHub
applies them to every repository the account owns that has no file of that type,
**regardless of that repository's visibility**. One file, 107 repos.

Two conditions, both load-bearing:

- **The `.github` repository must be public.** GitHub's documentation states it
  plainly: "A repository for default files cannot be private." A private one
  inherits to nothing and fails silently, which is the worst way to fail.
- **A repo's own file always wins.** For issue templates the override is total:
  a repo with any `.github/ISSUE_TEMPLATE` content ignores the defaults
  entirely, rather than merging them.

A repo writes its own copy only when the content genuinely differs. A copied
file that repeats the default is a file that drifts alone and silently. On
2026-09-14 one repo's `CONTRIBUTING.md` still told contributors to branch as
`feature/your-feature`, which the branch standard has rejected for months. It
had been copied once and never read again.

**Do not verify the security policy with the community profile API.** It does
not report one, inherited or local. Measured on 2026-09-14, minutes after the
defaults went live:

    $ gh api repos/itsryanarmani/skills/community/profile --jq '.files | keys'
    ["code_of_conduct","code_of_conduct_file","contributing","issue_template",
     "license","pull_request_template","readme"]

No `security` key, while the same repository's `/security/policy` page was
already serving the inherited file. A checker that trusts that endpoint reports
every repo in the fleet as having no security policy, forever.

### The rest

| File | Owner | Rule |
|---|---|---|
| `AGENTS.md` | the fleet | Every repo. The agent's entry point. |
| `VISION.md` | the repo | Every repo a person could contribute to. |
| `.github/pr-standards.json` | `pr-standards` | Carries the prefix. Never hand-edited. |
| `.github/ISSUE_TEMPLATE/` | `issue-standards` | Per repo, because the prefix varies. |
| `.gitattributes` | the repo | Mark generated and vendored paths `linguist-generated` and `linguist-vendored`, or the language bar reports the language of your lockfile. |

## The About panel

Three fields. All three are set by API, so none of them has an excuse.

    gh repo edit itsryanarmani/<repo> \
      --description "<the pitch, unchanged>" \
      --homepage "https://<live url>" \
      --add-topic <topic> --add-topic <topic>

- **Description.** The pitch, character for character. Required.
- **Homepage.** The live URL when one exists. Set it or leave it null. Two
  public repos carried an empty string instead on 2026-09-14, which the UI
  renders identically to never having set one, so there is nothing to notice
  and nothing to fix by hand later.
- **Topics.** Four to twelve. On 2026-09-14, 29 of 33 public repos had none.
  For a repo with no stars, topics are the only discovery surface GitHub gives
  you, and they cost one command.

## The social preview

The 1280×640 image GitHub serves when the repo URL is pasted into Slack, X,
LinkedIn or Discord. Without one, the preview is a generated grey card carrying
the owner's avatar and the description.

Read the current state:

    gh api graphql -f query='{repository(owner:"itsryanarmani",name:"skills"){
      openGraphImageUrl usesCustomOpenGraphImage }}'

`usesCustomOpenGraphImage: false` means the repo is serving the default card.

**There is no API that sets it.** GraphQL exposes the field for reading only,
and the REST API has no endpoint for it. The upload is a browser action, in
Settings → Social preview. So:

1. Generate or export the image.
2. Commit it to `assets/og.png`. The committed copy is the source of truth, it
   survives the browser step being skipped, and the README banner can reuse it.
3. Upload it through a headed browser pass.

Step 3 is the only part of this standard a program cannot finish. Treat a repo
with `assets/og.png` committed and `usesCustomOpenGraphImage: false` as work in
progress, not as a failure.

## Images

### What earns a place

| Image | Earns its place when |
|---|---|
| Banner | Always, on a public repo. It is the repo's identity. |
| Product screenshot | The repo ships a user interface. Required, not optional. |
| Terminal capture | The repo ships a CLI. Show real output. |
| Diagram | The reader cannot hold the flow in their head without it. |
| Benchmark chart | You have measured something and the number is the point. |

### The rules

**Real beats generated.** A generated banner is decoration and a reader knows
it. A screenshot of the product doing its job is evidence. A repo that ships a
UI and shows no UI is telling you it does not work yet.

**Images live in `assets/`, committed, and are linked relatively.** Not
hot-linked from a GitHub user-attachment URL.

An attachment URL does serve anonymous readers on a public repo, so it looks
fine the day you write it. But it is not a git object, there is no asset
manager, and no GitHub documentation promises it will keep resolving. There is
at least one public commit repairing a README after an attachment stopped
loading. A README that depends on an asset the repo does not contain is a
README with an expiry date nobody wrote down.

Attachments are for pull request proof, where the PR standard already requires
them and where a dead link costs nothing a year later. The repo is for the
README.

**Every image carries alt text** that describes the image, not the project.
`alt="Two terminals sharing one cursor"`, never `alt="vibeshare"`.

**Under 500 KB each.** A README is the one file every visitor loads.

## Translations

Public repos. Skip on private ones.

    docs/translations/<iso-639-1>.md

The `standard-readme` spec names the other convention, `README.de.md` at the
repo root with a BCP 47 tag, reserving `README.md` for English. Both work and
neither is detected by GitHub. This fleet puts them in `docs/translations/`
because four languages across a repo root is four files in the way of every
reader who wanted the English one.

The switcher sits under the badges, English first and bold, separated by `·`.

The English README is the source. Every translation carries the commit it was
made from, on its first line:

    <!-- translated-from: 4d8c7a6 -->

That comment is the only thing that makes staleness visible. Without it a
reader has no way to tell a current translation from one that describes a
version you deleted, and neither do you. **A stale translation is worse than no
translation**, because the reader cannot tell which they are holding.

Translations are produced by `private-repo-0218`, not by hand and not by a one-off
script per repo. One pipeline, so one fix reaches every language.

## What private repos do differently

74 of the 107 repos are private. They follow the same spine, with four changes,
each for a stated reason:

| Change | Reason |
|---|---|
| Static badges, or none | A dynamic badge cannot authenticate and renders "repo not found". Shields will not take a token, and a token in a badge URL is a leaked token. |
| No translations | The audience is one person. |
| No social preview | GitHub does not serve a private repo's card to the places a preview is for, so the upload cannot reach the audience it exists for. |
| No banner required | Identity is not the job. Operability is. |

One thing does not relax and surprises people: **topic names on a private repo
are public**. The repo stays hidden, the topics do not. Do not name an unshipped
product in a topic.

Nothing else relaxes. The private repos are where a README matters most,
because they are the ones a future collaborator meets with no context at all,
and the ones you will reopen in a year having forgotten everything.

## What a program cannot check

`repo-standards` checks shape: the sections, their order, the front door, the
files, the About panel, the image paths, the translation markers. Shape is most
of the drift and all of the cheap fixes.

It cannot check the four things that matter most:

1. **Whether the sentence is true.** A precise description of the wrong product
   passes every check.
2. **Whether the quick start works for someone who is not you.** It runs on your
   machine because your machine has the service already running.
3. **Whether the screenshot is current.** An image never fails a build.
4. **Whether the repo does one thing.** Two products in one repo produce a
   README that hedges, and hedging is not a checkable property.

Those four belong to the review lens and to a person. The checker exists so
that a person's attention is spent on them, and not on a missing license file.

## The layers

Four, the same four as `pr-standards`, because no single layer can hold it.

1. **The agent.** `repo-standards check <path>` before an agent edits a README,
   and after. An agent that rewrites a README without running it will produce a
   good README in the wrong shape.
2. **CI.** `.github/workflows/repo-standards.yml` per repo. The authority on
   public repos. On private repos, GitHub Free cannot require a check, so it is
   a signal and not a gate. That gap is stated in `pr-standards.md` and has not
   changed.
3. **The fleet view.** `standards-coverage` reports which repos carry which
   layer. A standard nobody measures is a preference.
4. **The review lens.** `vibecodereview` makes the judgement no regex can:
   whether the README is still true.

## What this replaces

The `open-source-repo-prep` skill, which covered the same ground for one repo at
a time and predates this document. Its verified content about branch protection
mechanics and history rewriting moves into the `repo-standards` skill. Nothing
is kept in both places.
