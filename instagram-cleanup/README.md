# instagram-cleanup

Delete your own Instagram comments in batches. The tool opens **Your Activity →
Comments** (`instagram.com/your_activity/interactions/comments`) in a browser
you are logged in to, driven by [Playwright](https://playwright.dev/python/),
ticks a batch of comments in Select mode and deletes them with Instagram's own
**Delete** button.

- Dry run is the default. It lists what would be deleted in a CSV and changes
  nothing. Nothing is deleted until you pass `--confirm`.
- Deletes are paced: 10 per batch, then a 5 minute pause, with random jitter.
- Every handled id goes into a JSONL progress log. A rerun skips ids that are
  already deleted, so you can stop and resume at any time.
- No credentials are stored in the script or printed. You log in yourself.

Requires Python 3.9 or newer and
`pip install playwright && playwright install chromium`.

## What gets deleted

- Your Activity only lists comments you wrote, so nothing else can be ticked.
- The page shows no comment ids. Each row's id is a hash of its text and post
  thumbnail, so the progress log can still record what was handled. Two
  identical comments on the same post share that hash, so a rerun may skip the
  second one; delete it by hand, or move the progress log aside and rerun.
- When Instagram shows **Something went wrong**, the batch is retried after an
  exponential backoff (`--backoff`, doubling up to `--max-retries` times). A
  "try again later" or action-blocked message stops the run.

## Usage

```bash
# Dry run: a browser opens; log in once, press Enter, get instagram-cleanup-items-<stamp>.csv
./instagram_cleanup.py

# Delete
./instagram_cleanup.py --confirm

# At most 25 this run, slower pacing
./instagram_cleanup.py --confirm --limit 25 --batch-size 5 --delay 1800

# Exported cookies instead of a browser profile
./instagram_cleanup.py --cookies cookies.json --confirm
```

| Option | Default | Meaning |
|---|---|---|
| `--confirm` | off | Delete. Without it the run is a dry run. |
| `--limit` | none | Handle at most N items this run. |
| `--batch-size` | `10` | Comments ticked and deleted together. |
| `--delay` | `300` | Seconds to pause between batches. |
| `--item-delay` | `1` | Seconds between checkbox clicks. |
| `--jitter` | `0.3` | Random +/- fraction applied to every pause. |
| `--max-retries` | `5` | Retries per batch after "Something went wrong". |
| `--backoff` | `60` | First backoff wait in seconds; doubles each retry. |
| `--max-failures` | `3` | Stop after N failed batches in a row. |
| `--max-scrolls` | `200` | Scroll limit while listing. |
| `--progress` | `instagram-cleanup-progress.jsonl` | Resumable progress log. |
| `--csv` | `instagram-cleanup-items-<stamp>.csv` | Dry-run listing. |
| `--profile-dir` | `~/.instagram-cleanup-profile` | Persistent browser profile you log in to. |
| `--cookies` | none | JSON cookies file (Playwright storage state, or a Cookie-Editor export). |
| `--headless` | off | No browser window. Needs a profile or cookies that are already logged in. |

Deletes from the last `--delay` seconds in the progress log count toward the
current batch, so restarting does not skip the long pause. The run stops at
once, keeping the progress log, when Instagram redirects to a login or
checkpoint page or says to try again later. Rerun later with the same command
to resume. Exit codes: `0` ok, `1` some deletes failed or the run stopped, `2`
usage error.

## Selectors may break

The tool clicks Instagram's normal web UI: **Select**, the row checkboxes, **Delete**, then **Delete** in the dialog.
Instagram changes its markup often. All selectors are in the `SELECTORS` dict
at the top of `instagram_cleanup.py`; fix them there if listing or deleting starts
failing. Three failures in a row stop the run, and a run that finds nothing
prints a warning.

## Safety notes

- **Deletion is permanent.** Read the dry-run CSV first.
- **Keep your cookies file private.** It logs in as you. Delete it after use.
- Pacing does not guarantee Instagram will not limit the account. Slower is safer.
- Follow Instagram's terms of service.

## Testing

```bash
python3 -m unittest discover -s instagram-cleanup   # from repo root
```

The tests cover link and row parsing, ownership checks, the progress log,
pacing, backoff, cookies and the dry-run and delete flow with a fake browser.
They need no Playwright, account or network.

## Disclaimer

Unofficial tool, not affiliated with or endorsed by Meta Platforms. Use at your
own risk. MIT licensed. See the repository [LICENSE](../LICENSE).
