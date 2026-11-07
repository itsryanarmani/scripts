<!--
Fill every __PLACEHOLDER__. Delete this comment first. It is the first thing
you delete before shipping. A leftover placeholder is a claim that is not
true, and the reader will believe it. Drop the language switcher on a private
repo or a repo with no translations. On a private repo, use static badges or
none. The screenshot must show the current build doing its job.
-->

<!-- for example: a board with three cards in Review -->
<p align="center">
  <img src="assets/__REPO__.png" alt="__BANNER_ALT__" width="900"/>
</p>

<!-- for example: A board that shows which agent owns which card, and nothing else. -->
<p align="center">__ONE_SENTENCE_PITCH__</p>

<p align="center">
  <a href="https://github.com/__OWNER__/__REPO__/releases"><img src="https://img.shields.io/github/v/release/__OWNER__/__REPO__" alt="release __VERSION__"/></a>
  <a href="https://github.com/__OWNER__/__REPO__/actions"><img src="https://github.com/__OWNER__/__REPO__/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-__LICENSE__-blue" alt="License __LICENSE__"/></a>
  <!-- for example: 12 providers -->
  <a href="__LIVE_URL__"><img src="https://img.shields.io/badge/__METRIC_LABEL__-__METRIC_VALUE__-informational" alt="__METRIC_CAPTION__"/></a>
</p>

<p align="center">
  <a href="README.md"><b>English</b></a> ·
  <a href="docs/translations/zh.md">中文</a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/__SCREENSHOT_DARK__"/>
    <!-- for example: a card moving from Ready to Review -->
    <img src="assets/__SCREENSHOT_LIGHT__" alt="__SCREENSHOT_ALT__" width="900"/>
  </picture>
</p>
<!-- for example: a card moving from Ready to Review. -->
<p align="center"><em>__PROOF_CAPTION__</em></p>

## Install

<!-- for example: https://board.example -->
```
__LIVE_URL__
```

The live app. Paste the same URL into the About panel homepage.

## Run it locally

Every service this process talks to, including the ones that have been running on your machine since you wrote them.

<!-- for example: `bun run dev` on :3000 -->
<!-- for example: `bun run api` on :8787 -->
<!-- for example: `docker compose up db` -->
<!-- for example: `docker compose up redis` -->
| Service | What it is | How to start it |
|---|---|---|
| `__APP_SERVICE__` | the web process | `__APP_START__` |
| `__API_SERVICE__` | the API | `__API_START__` |
| `__DB_SERVICE__` | Postgres | `__DB_START__` |
| `__QUEUE_SERVICE__` | the queue | `__QUEUE_START__` |

```bash
__LOCAL_UP_COMMAND__
```

## Quick start

<!-- for example: the card in Review with your name on it. -->
Open `__LOCAL_URL__`, sign in as `__DEV_USER__`, and move one card. You should see `__QUICK_START_OUTPUT__`.

## Why

<!-- for example: not a Jira replacement and not a team chat. -->
For __WHO__, who today uses __ALTERNATIVE__. Not for __WHO_NOT__.

## Usage

<!-- for example: drop a card on Review and the owner field fills. -->
<!-- for example: paste a pull request URL and the card links it. -->
| Action | What happens |
|---|---|
| `__ACTION_1__` | `__ACTION_1_RESULT__` |
| `__ACTION_2__` | `__ACTION_2_RESULT__` |

## How it works

<!-- for example: the browser holds the board; the API writes events; Postgres is the source of truth. -->
__HOW_IT_WORKS__

## Contributing

See [CONTRIBUTING.md](https://github.com/itsryanarmani/.github/blob/main/CONTRIBUTING.md).

## License

[__LICENSE__](LICENSE)
