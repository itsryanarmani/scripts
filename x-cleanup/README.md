# x-cleanup

Delete your own X (Twitter) posts and replies, read from your X archive export
or from a CSV of tweet ids. Deletes run in a logged-in browser driven by
[Playwright](https://playwright.dev/python/), or through the official X API
when you supply your own user token.

- Dry run is the default. It only writes a CSV of what would be deleted.
  Nothing is deleted until you pass `--confirm`.
- Deletes are slow on purpose: 15, then a 2 hour pause. X has locked an
  account that deleted quickly. Change it with `--batch-size` and `--delay`.
- Every handled id goes into a JSONL progress log. A rerun skips ids that are
  already deleted, so you can stop and resume at any time.
- No credentials are stored in the script or printed. You log in yourself.

Requires Python 3.9 or newer, plus `pip install playwright && playwright install chromium`
for browser mode. Dry run and API mode do not need Playwright.

## Get the ids

1. Request your archive: **Settings → Your account → Download an archive of
   your data**. When it is ready, download and unzip it.
2. Pass the folder (or `data/tweets.js`) with `--archive`. Multi-part
   archives (`tweets-part1.js`, ...) are picked up from the folder.

Or pass `--ids-csv` with a CSV of ids or status URLs. A header column named
`tweet_id`, `id`, `id_str`, `url` or `link` is used; otherwise the first column.

## Usage

```bash
# Dry run: list what would go, write x-cleanup-items-<stamp>.csv
./x_cleanup.py --archive ~/Downloads/twitter-archive

# Log in once in the browser window that opens, then it deletes
./x_cleanup.py --archive ~/Downloads/twitter-archive --confirm

# Replies only, before 2022, at most 100 this run
./x_cleanup.py --archive ./archive --kind replies --before 2022-01-01 --limit 100 --confirm

# From a CSV, with exported cookies instead of a browser profile
./x_cleanup.py --ids-csv ids.csv --cookies x-cookies.json --confirm

# Official API (your own developer app; OAuth 2.0 user token with tweet.write)
export X_USER_ACCESS_TOKEN='...'
./x_cleanup.py --archive ./archive --api --confirm
```

| Option | Default | Meaning |
|---|---|---|
| `--confirm` | off | Delete. Without it the run is a dry run. |
| `--kind` | `all` | `all`, `posts` or `replies`. Archive retweets are never touched; CSV ids are used as given. |
| `--before`, `--after` | none | `YYYY-MM-DD`, UTC. CSV ids have no kind or date, so `--kind posts/replies` and dates leave them out. |
| `--limit` | none | Handle at most N items this run. |
| `--batch-size` | `15` | Deletes per batch. |
| `--delay` | `7200` | Seconds to pause between batches. |
| `--item-delay` | `20` | Seconds between single deletes. |
| `--jitter` | `0.3` | Random +/- fraction applied to every pause. |
| `--max-failures` | `3` | Stop after N failures in a row. |
| `--progress` | `x-cleanup-progress.jsonl` | Resumable progress log. |
| `--csv` | `x-cleanup-items-<stamp>.csv` | Dry-run listing. |
| `--profile-dir` | `~/.x-cleanup-profile` | Persistent browser profile you log in to. |
| `--cookies` | none | JSON cookies file (Playwright storage state, or a Cookie-Editor export). |
| `--headless` | off | No browser window. Needs a profile or cookies that are already logged in. |

Deletes from the last `--delay` seconds in the progress log count toward the
current batch, so restarting does not skip the long pause.

The run stops at once, keeping the progress log, when X answers with a rate
limit, an error page, or a redirect to login or account access. Rerun later
with the same command to resume. Exit codes: `0` ok, `1` some deletes failed
or the run stopped, `2` usage error.

## Selectors may break

Browser mode clicks X's normal web UI: the `...` menu on the post, **Delete**,
then the confirm button. X changes its markup often. All selectors are in the
`SELECTORS` dict at the top of `x_cleanup.py`; fix them there if deletes start
failing. Three failures in a row stop the run.

## Safety notes

- **Deletion is permanent.** Read the dry-run CSV first.
- **Keep your cookies file private.** It logs in as you. Delete it after use.
- Pacing does not guarantee X will not limit or lock the account. Slower is safer.
- Follow X's terms of service and API rules.

## Testing

```bash
python3 -m unittest discover -s x-cleanup   # from repo root
```

The tests cover archive and CSV parsing, filters, the progress log, cookies
and pacing. They need no Playwright, account or network.

## Disclaimer

Unofficial tool, not affiliated with or endorsed by X Corp. Use at your own
risk. MIT licensed. See the repository [LICENSE](../LICENSE).
