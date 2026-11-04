# linkedin-cleanup

Delete your own LinkedIn comments and posts. The tool reads your activity pages,
`linkedin.com/in/<you>/recent-activity/comments/` and `/all/`, in a browser you
are logged in to, driven by [Playwright](https://playwright.dev/python/), and
deletes through LinkedIn's normal menus.

- Dry run is the default. It lists what would be deleted in a CSV and changes
  nothing. Nothing is deleted until you pass `--confirm`.
- Deletes are paced: 10 per batch, then a 15 minute pause, with random jitter.
- Every handled id goes into a JSONL progress log. A rerun skips ids that are
  already deleted, so you can stop and resume at any time.
- No credentials are stored in the script or printed. You log in yourself.

Requires Python 3.9 or newer and
`pip install playwright && playwright install chromium`.

## What gets deleted

- Comments: only comments whose author link is your own profile are listed.
  Other people's comments on the same post are ignored.
- Posts: only cards you wrote, with no "reposted" or "likes this" header, are
  listed as `post`. Reposts and other people's posts are listed as `other` and
  never deleted. The header check expects LinkedIn in English.

## Usage

```bash
# Dry run: a browser opens; log in once, press Enter, get linkedin-cleanup-items-<stamp>.csv
./linkedin_cleanup.py --user jane-doe

# Delete
./linkedin_cleanup.py --user jane-doe --confirm

# At most 25 this run, slower pacing
./linkedin_cleanup.py --user jane-doe --confirm --limit 25 --batch-size 5 --delay 1800

# Exported cookies instead of a browser profile
./linkedin_cleanup.py --user jane-doe --cookies cookies.json --confirm
```

| Option | Default | Meaning |
|---|---|---|
| `--user` | required | Your profile name from `linkedin.com/in/<name>/`, or the full URL. |
| `--what` | `both` | `comments`, `posts` or `both`. |
| `--confirm` | off | Delete. Without it the run is a dry run. |
| `--limit` | none | Handle at most N items this run. |
| `--batch-size` | `10` | Deletes per batch. |
| `--delay` | `900` | Seconds to pause between batches. |
| `--item-delay` | `8` | Seconds between single deletes. |
| `--jitter` | `0.3` | Random +/- fraction applied to every pause. |
| `--max-failures` | `3` | Stop after N failed deletes in a row. |
| `--max-scrolls` | `200` | Scroll limit while listing. |
| `--progress` | `linkedin-cleanup-progress.jsonl` | Resumable progress log. |
| `--csv` | `linkedin-cleanup-items-<stamp>.csv` | Dry-run listing. |
| `--profile-dir` | `~/.linkedin-cleanup-profile` | Persistent browser profile you log in to. |
| `--cookies` | none | JSON cookies file (Playwright storage state, or a Cookie-Editor export). |
| `--headless` | off | No browser window. Needs a profile or cookies that are already logged in. |

Deletes from the last `--delay` seconds in the progress log count toward the
current batch, so restarting does not skip the long pause. The run stops at
once, keeping the progress log, when LinkedIn redirects to a login or
checkpoint page or says to try again later. Rerun later with the same command
to resume. Exit codes: `0` ok, `1` some deletes failed or the run stopped, `2`
usage error.

## Selectors may break

The tool clicks LinkedIn's normal web UI: the comment's `...` menu, or the post's control menu, then **Delete** and the
confirm button.
LinkedIn changes its markup often. All selectors are in the `SELECTORS` dict
at the top of `linkedin_cleanup.py`; fix them there if listing or deleting starts
failing. Three failures in a row stop the run, and a run that finds nothing
prints a warning.

## Safety notes

- **Deletion is permanent.** Read the dry-run CSV first.
- **Keep your cookies file private.** It logs in as you. Delete it after use.
- Pacing does not guarantee LinkedIn will not limit the account. Slower is safer.
- Follow LinkedIn's terms of service.

## Testing

```bash
python3 -m unittest discover -s linkedin-cleanup   # from repo root
```

The tests cover link and row parsing, ownership checks, the progress log,
pacing, cookies and the dry-run and delete flow with a fake browser.
They need no Playwright, account or network.

## Disclaimer

Unofficial tool, not affiliated with or endorsed by LinkedIn Corporation. Use at your
own risk. MIT licensed. See the repository [LICENSE](../LICENSE).
