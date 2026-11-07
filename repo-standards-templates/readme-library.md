<!--
Fill every __PLACEHOLDER__. Delete this comment first. It is the first thing
you delete before shipping. A leftover placeholder is a claim that is not
true, and the reader will believe it. Drop the language switcher on a private
repo or a repo with no translations. On a private repo, use static badges or
none. No screenshots. The example below must compile and run as written.
-->

<!-- for example: search results ranked by score -->
<p align="center">
  <img src="assets/__REPO__.png" alt="__BANNER_ALT__" width="900"/>
</p>

<!-- for example: Rank a list of pages the way a reader would, not by keyword count. -->
<p align="center">__ONE_SENTENCE_PITCH__</p>

<p align="center">
  <a href="https://github.com/__OWNER__/__REPO__/releases"><img src="https://img.shields.io/github/v/release/__OWNER__/__REPO__" alt="release __VERSION__"/></a>
  <a href="https://github.com/__OWNER__/__REPO__/actions"><img src="https://github.com/__OWNER__/__REPO__/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-__LICENSE__-blue" alt="License __LICENSE__"/></a>
  <!-- for example: 1.2kB min+gz -->
  <a href="assets/bench.md"><img src="https://img.shields.io/badge/__METRIC_LABEL__-__METRIC_VALUE__-informational" alt="__METRIC_CAPTION__"/></a>
</p>

<p align="center">
  <a href="README.md"><b>English</b></a> ·
  <a href="docs/translations/zh.md">中文</a>
</p>

## Install

```bash
__INSTALL_COMMAND__
```

```js
import { __EXPORT_1__ } from '__PACKAGE__'

const hits = __EXPORT_1__('agent README', pages)
console.log(hits[0].title)
// Search results, ranked by score
```

## Quick start

```bash
node example.mjs
```

<!-- for example: Search results, ranked by score -->
```
__QUICK_START_OUTPUT__
```

## Why

<!-- for example: not a crawler and not a search engine. -->
For __WHO__, who today uses __ALTERNATIVE__. Not for __WHO_NOT__.

## Usage

<!-- for example: `rank(query, pages)` → `[{ title, score }]`. -->
<!-- for example: `explain(hit)` → the tokens that produced the score. -->
| Export | What it does |
|---|---|
| `__EXPORT_1__` | Ranks `__INPUT__` and returns `__OUTPUT__` |
| `__EXPORT_2__` | `__EXPORT_2_DOES__` |

## How it works

<!-- for example: a lexical score plus a recency prior; no network call, no model. -->
__HOW_IT_WORKS__

## Contributing

See [CONTRIBUTING.md](https://github.com/itsryanarmani/.github/blob/main/CONTRIBUTING.md).

## License

[__LICENSE__](LICENSE)
