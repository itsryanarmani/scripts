# threads-cleanup

Delete your own Threads posts and replies. The tool reads the **Threads** and
**Replies** tabs of your profile (`threads.com/@<you>`; `threads.net` redirects
there) in a browser you are logged in to, driven by
[Playwright](https://playwright.dev/python/), and deletes each item from its
own page.

- Dry run is the default. It lists what would be deleted in a CSV and changes
  nothing. Nothing is deleted until you pass `--confirm`.
- Deletes are paced: 10 per batch, then a 15 minute pause, with random jitter.
- Every handled id goes into a JSONL progress log. A rerun skips ids that are
  already deleted, so you can stop and resume at any time.
- No credentials are stored in the script or printed. You log in yourself.

Requires Python 3.9 or newer and
`pip install playwright && playwright install chromium`.

## What gets deleted

- Only permalinks of the form `/@<you>/post/<code>` are listed. The post you
  replied to, shown above each reply on the Replies tab, belongs to someone
  else and is ignored.
- The Threads tab is always read, so your own posts shown above replies are
  known as posts, and `--what replies` does not delete them. If that tab is
  longer than `--max-scrolls`, the run stops before deleting anything.
- On the post page the tool opens the `...` menu of the innermost box holding
  that permalink only.

## Usage

```bash
# Dry run: a browser opens; log in once, press Enter, get threads-cleanup-items-<stamp>.csv
./threads_cleanup.py --user jane.doe

# Delete
./threads_cleanup.py --user jane.doe --confirm

# At most 25 this run, slower pacing
./threads_cleanup.py --user jane.doe --confirm --limit 25 --batch-size 5 --delay 1800

# Exported cookies instead of a browser profile
./threads_cleanup.py --user jane.doe --cookies cookies.json --confirm
```

| Option | Default | Meaning |
|---|---|---|
| `--user` | required | Your username, with or without `@`, or a profile URL. |
| `--what` | `both` | `posts`, `replies` or `both`. |
| `--confirm` | off | Delete. Without it the run is a dry run. |
| `--limit` | none | Handle at most N items this run. |
| `--batch-size` | `10` | Deletes per batch. |
| `--delay` | `900` | Seconds to pause between batches. |
| `--item-delay` | `10` | Seconds between single deletes. |
| `--jitter` | `0.3` | Random +/- fraction applied to every pause. |
| `--max-failures` | `3` | Stop after N failed deletes in a row. |
| `--max-scrolls` | `200` | Scroll limit while listing. |
| `--progress` | `threads-cleanup-progress.jsonl` | Resumable progress log. |
| `--csv` | `threads-cleanup-items-<stamp>.csv` | Dry-run listing. |
| `--profile-dir` | `~/.threads-cleanup-profile` | Persistent browser profile you log in to. |
| `--cookies` | none | JSON cookies file (Playwright storage state, or a Cookie-Editor export). |
| `--headless` | off | No browser window. Needs a profile or cookies that are already logged in. |

Deletes from the last `--delay` seconds in the progress log count toward the
current batch, so restarting does not skip the long pause. The run stops at
once, keeping the progress log, when Threads redirects to a login or
checkpoint page or says to try again later. Rerun later with the same command
to resume. Exit codes: `0` ok, `1` some deletes failed or the run stopped, `2`
usage error.

## Selectors may break

The tool clicks Threads's normal web UI: the post's **More** (`...`) button, **Delete**, then **Delete** in the dialog.
Threads changes its markup often. All selectors are in the `SELECTORS` dict
at the top of `threads_cleanup.py`; fix them there if listing or deleting starts
failing. Three failures in a row stop the run, and a run that finds nothing
prints a warning.

## Safety notes

- **Deletion is permanent.** Read the dry-run CSV first.
- **Keep your cookies file private.** It logs in as you. Delete it after use.
- Pacing does not guarantee Threads will not limit the account. Slower is safer.
- Follow Threads's terms of service.

## Testing

```bash
python3 -m unittest discover -s threads-cleanup   # from repo root
```

The tests cover link and row parsing, ownership checks, the progress log,
pacing, cookies and the dry-run and delete flow with a fake browser.
They need no Playwright, account or network.

## Disclaimer

Unofficial tool, not affiliated with or endorsed by Meta Platforms. Use at your
own risk. MIT licensed. See the repository [LICENSE](../LICENSE).
