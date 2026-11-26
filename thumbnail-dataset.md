# thumbnail-dataset

Collects real YouTube thumbnails with their numbers, so a thumbnail study starts
from data. It uses the official YouTube Data API, read-only. The skill
`youtube-thumbnails` (skills repo) says what to do with the result.

```sh
python3 thumbnail-dataset --out data --queries-file q.txt --max 30 --published-after 2025-11-26 --dry-run
python3 thumbnail-dataset --out data --queries-file q.txt --max 30 --published-after 2025-11-26
```

| Flag | Meaning |
| --- | --- |
| `--query TEXT`, `--queries-file F` | Searches (a file has one per line, `#` lines ignored). Blank and repeated queries are dropped: each costs 100 units. |
| `--max N`, `--published-after DATE` | Results per search (1 to 50, default 25); `YYYY-MM-DD`. |
| `--order`, `--region`, `--language` | `viewCount` (default), `relevance`, `date`; `US`; `en`. |
| `--keep-shorts`, `--short-max N` | A video of N s or less (default 60) is a Short and is skipped. The API cannot tell a 61 to 180 s Short from a video. A live stream has no duration and is kept (`duration_s` null). |
| `--no-images` | Numbers only; a later run without it downloads the images. |
| `--refresh-searches` | Search again even if `searches.json` has the answer. |
| `--dry-run` | Print the quota estimate (it ignores cached searches). Needs no token. |

**Auth.** `YOUTUBE_ACCESS_TOKEN`, or `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`
and `YOUTUBE_REFRESH_TOKEN` (refreshed by the script). Scope `youtube.readonly`.

**Output.** `dataset.jsonl` and `dataset.csv`: `id`, `title`, `channel`, `published`,
`duration_s`, `views`, `likes`, `comments` (null when hidden), `subscribers`,
`views_per_day`, `outlier`, `thumb`, `thumb_tries`, `queries`. `thumbs/<id>.jpg`
is `maxresdefault`, or `hqdefault` for older videos. Also `skipped.txt` (Shorts),
`gone.txt` (deleted or private ids; delete the file to look again) and
`searches.json` (finished searches, keyed by query, `--max`, `--order`, region,
language and date). Files are written whole and renamed.

`outlier` is views over subscribers, only for channels of 1,000+. A high value
means the video beat its own channel, which says more about the thumbnail than raw
views. It is a hint: topic, timing and title count, and one video can be lucky.

**Reruns.** A rerun skips known ids and cached searches, so after a quota stop it
pays only for searches that did not finish. A failed thumbnail is tried 3 times in
all. A video is saved only with its channel's subscriber count; one whose channel
lookup failed is counted in `unresolved` and fetched again next run. An API error,
a crash or Ctrl-C saves what was gathered. A thumbnail-only rerun still needs a token.

**Quota.** A search costs 100 units, a page of 50 videos or channels 1. The default
is 10,000 a day (reset at midnight Pacific): 25 searches of 30 results cost about 2,530.

**Exit codes.** 0 ok; 1 quota used up or a download failed; 2 usage, auth, a failed
token refresh, odd data, or any other API or network error.

**Rights.** The images are other people's work: study them, do not republish or commit them. The numbers are facts.

`python3 thumbnail-dataset.test.py` runs it against a fake API (no quota).
