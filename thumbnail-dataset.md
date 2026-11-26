# thumbnail-dataset

`thumbnail-dataset` collects real YouTube thumbnails with their numbers, so a
thumbnail study starts from data and not from opinion. It uses the official
YouTube Data API, read-only. The skill `youtube-thumbnails` (skills repo) says
what to do with the result.

```sh
python3 thumbnail-dataset --out data --queries-file queries.txt --max 30 \
    --published-after 2025-11-26 --dry-run          # quota cost, calls nothing
python3 thumbnail-dataset --out data --queries-file queries.txt --max 30 --published-after 2025-11-26
```

| Flag | Meaning |
| --- | --- |
| `--query TEXT` | A search. Repeat it. |
| `--queries-file FILE` | One search per line. Lines that start with `#` are ignored. |
| `--max N` | Results per search, 1 to 50. Default 25. |
| `--published-after DATE` | `YYYY-MM-DD`. Recent videos show current styles. |
| `--order` | `viewCount` (default), `relevance` or `date`. |
| `--region` | Region code. Default `US`. |
| `--language` | Preferred result language. Default `en`. |
| `--keep-shorts` | Keep Shorts. They are skipped by default. |
| `--short-max N` | A video of N seconds or less counts as a Short. Default 60. The API cannot tell a 61 to 180 s Short from a video, so raise this if they matter. A video with no usable duration (a live stream) is kept, with `duration_s` null. |
| `--no-images` | Write the numbers only. A later run without it downloads the images. |
| `--refresh-searches` | Search again even if `searches.json` has the answer. |
| `--dry-run` | Print the quota estimate and stop. Needs no token. |

## Auth

From the environment: `YOUTUBE_ACCESS_TOKEN`, or `YOUTUBE_CLIENT_ID`,
`YOUTUBE_CLIENT_SECRET` and `YOUTUBE_REFRESH_TOKEN` (the script refreshes the
token). The token needs the `youtube.readonly` scope. The script sends a
bearer token, so a plain API key is not used.

## Output

- `dataset.jsonl` and `dataset.csv`: one row per video with `id`, `title`,
  `channel`, `published`, `duration_s`, `views`, `likes`, `comments`,
  `subscribers`, `views_per_day`, `outlier`, `thumb` (which size was saved) and
  the `queries` that found it.
- `thumbs/<id>.jpg`: `maxresdefault`, or `hqdefault` for older videos.
- `skipped.txt`: Shorts already seen. `gone.txt`: ids the API no longer returns (deleted or private). `searches.json`: finished searches. A rerun uses all three, so it does not fetch or search for them again.
- Files are written whole and then renamed, so a kill cannot leave a half file.

`views_per_day` is views divided by the age in days (at least 1). `outlier` is
views divided by subscribers, only for channels of 1,000 or more subscribers.
A high outlier means the video beat its own channel, which says more about the
thumbnail and title than raw views do. It is not proof: topic, timing and the
title also count, and a small channel can have one lucky video.

A rerun skips ids it already has and reuses finished searches, so after a quota stop it pays only for the searches that did not finish. It retries a failed thumbnail (3 tries in all, then it gives up and the row keeps `thumb` null), and downloads thumbnails after an earlier `--no-images` run, without calling the API. A video is saved only with its channel's subscriber count, so a failed channel lookup leaves it for the next run. Missing likes or comments are `null`, not 0.

## Quota

A search costs 100 units. A page of 50 videos or channels costs 1. The default
daily quota is 10,000, so 25 searches of 30 results cost about 2,530.

## Rights

The images are other people's work. Keep them for study. Do not republish them,
and do not commit them to a public repository. The numbers are facts and are
fine to share.

## Failure modes

| Symptom | Cause and fix |
| --- | --- |
| `token refresh failed` | Wrong client or an expired refresh token. The client that made the token must be the one you pass. |
| `YouTube API 403 ... quota` (exit 1) | The daily quota is used. It resets at midnight Pacific. The script saves everything gathered before the error, so rerun later and only the searches that did not finish cost quota. Any other API or network error exits 2 and also saves. A crash or Ctrl-C saves too. |
| `download_failed` lists ids | Neither `maxresdefault` nor `hqdefault` answered. Rerun: the script retries them without an API call, up to 3 tries in all. |
| `outlier` is `null` | The channel hides subscribers or has under 1,000. |
| Too many videos from huge channels | Add a narrower query, or sort by `outlier` and ignore raw views. |

## Test

`python3 thumbnail-dataset.test.py` runs the script against a fake API on
`127.0.0.1`. It checks the rows, the outlier rule, a skipped Short, the
`hqdefault` fallback, one video found by two searches, the token refresh and a
failed refresh, a quota error that saves partial work, a failed thumbnail that a
rerun retries, live-stream and week durations, hidden subscribers, missing
likes, a hostile video id, a unicode title with comma and quote, a rerun that
fetches nothing again, the dry run, and the usage errors. It uses no quota.
