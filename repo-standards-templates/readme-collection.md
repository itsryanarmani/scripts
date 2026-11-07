<!--
Fill every __PLACEHOLDER__. Delete this comment first. It is the first thing
you delete before shipping. A leftover placeholder is a claim that is not
true, and the reader will believe it. Drop the language switcher on a private
repo or a repo with no translations. On a private repo, use static badges or
none. Keep per-item detail in the item, never here.
-->

<!-- for example: a list of skills an agent can load -->
<p align="center">
  <img src="assets/__REPO__.png" alt="__BANNER_ALT__" width="900"/>
</p>

<!-- for example: Skills, prompts and commands for an agent that writes pull requests in this fleet. -->
<p align="center">__ONE_SENTENCE_PITCH__</p>

<p align="center">
  <a href="https://github.com/__OWNER__/__REPO__/releases"><img src="https://img.shields.io/github/v/release/__OWNER__/__REPO__" alt="release __VERSION__"/></a>
  <a href="https://github.com/__OWNER__/__REPO__/actions"><img src="https://github.com/__OWNER__/__REPO__/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-__LICENSE__-blue" alt="License __LICENSE__"/></a>
  <!-- for example: 28 skills -->
  <a href="https://github.com/__OWNER__/__REPO__"><img src="https://img.shields.io/badge/__METRIC_LABEL__-__METRIC_VALUE__-informational" alt="__METRIC_CAPTION__"/></a>
</p>

<p align="center">
  <a href="README.md"><b>English</b></a> ·
  <a href="docs/translations/zh.md">中文</a>
</p>

<!-- for example: writes the pull request body an agent would otherwise invent. -->
<!-- for example: the prompt that turns a failing check into a one-line diagnosis. -->
<!-- for example: the slash command that claims a fleet issue. -->
| Item | Kind | What it does |
|---|---|---|
| [`__ITEM_1__`](__ITEM_1_PATH__) | __ITEM_1_KIND__ | __ITEM_1_DOES__ |
| [`__ITEM_2__`](__ITEM_2_PATH__) | __ITEM_2_KIND__ | __ITEM_2_DOES__ |
| [`__ITEM_3__`](__ITEM_3_PATH__) | __ITEM_3_KIND__ | __ITEM_3_DOES__ |

## Install

```bash
# for example: npx skills add __OWNER__/__REPO__ or copy skills/ into ~/.agents/skills/
__INSTALL_COMMAND__
```

How to wire this into an agent CLI.

## Quick start

```bash
__QUICK_START__
```

<!-- for example: loaded __ITEM_1__ — writes a pull request body from the issue -->
```
__QUICK_START_OUTPUT__
```

## Why

<!-- for example: not a prompt dump and not a second copy of the standards. -->
For __WHO__, who today uses __ALTERNATIVE__. Not for __WHO_NOT__.

## How it works

<!-- for example: each item is a directory with its own `SKILL.md`; this file is only the index. -->
__HOW_IT_WORKS__

## Contributing

See [CONTRIBUTING.md](https://github.com/itsryanarmani/.github/blob/main/CONTRIBUTING.md).

## License

[__LICENSE__](LICENSE)
