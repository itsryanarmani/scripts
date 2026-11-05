# soundcloud-cleanup

Delete your own SoundCloud tracks and playlists. The tool reads your **Tracks**
and **Playlists** tabs (`soundcloud.com/<you>/tracks` and `/sets`) in a browser
you are logged in to, driven by [Playwright](https://playwright.dev/python/),
and deletes each item from its own page.

- Dry run is the default. It lists what would be deleted in a CSV and changes
  nothing. Nothing is deleted until you pass `--confirm`.
- Deletes are paced: 10 per batch, then a 5 minute pause, with random jitter.
- Every handled id goes into a JSONL progress log. A rerun skips ids that are
  already deleted, so you can stop and resume at any time.
- No credentials are stored in the script or printed. You log in yourself.

Requires Python 3.9 or newer and
`pip install playwright && playwright install chromium`.

## What gets deleted

- Only links under `/<you>/` are listed, and reposts are skipped, so other
  artists' tracks are never touched. Private tracks keep their secret-link
  token so their page opens.
- **Download your originals first.** A deleted track, its plays, likes and
  comments cannot be restored.

## Usage

```bash
# Dry run: a browser opens; log in once, press Enter, get soundcloud-cleanup-items-<stamp>.csv
./soundcloud_cleanup.py --user jane-doe

# Delete
./soundcloud_cleanup.py --user jane-doe --confirm

# At most 25 this run, slower pacing
./soundcloud_cleanup.py --user jane-doe --confirm --limit 25 --batch-size 5 --delay 1800

# Exported cookies instead of a browser profile
./soundcloud_cleanup.py --user jane-doe --cookies cookies.json --confirm
```

| Option | Default | Meaning |
|---|---|---|
| `--user` | required | Your profile name from `soundcloud.com/<name>`, or the URL. |
| `--what` | `both` | `tracks`, `playlists` or `both`. |
| `--confirm` | off | Delete. Without it the run is a dry run. |
| `--limit` | none | Handle at most N items this run. |
| `--batch-size` | `10` | Deletes per batch. |
| `--delay` | `300` | Seconds to pause between batches. |
| `--item-delay` | `5` | Seconds between single deletes. |
| `--jitter` | `0.3` | Random +/- fraction applied to every pause. |
| `--max-failures` | `3` | Stop after N failed deletes in a row. |
| `--max-scrolls` | `200` | Scroll limit while listing. |
| `--progress` | `soundcloud-cleanup-progress.jsonl` | Resumable progress log. |
| `--csv` | `soundcloud-cleanup-items-<stamp>.csv` | Dry-run listing. |
| `--profile-dir` | `~/.soundcloud-cleanup-profile` | Persistent browser profile you log in to. |
| `--cookies` | none | JSON cookies file (Playwright storage state, or a Cookie-Editor export). |
| `--headless` | off | No browser window. Needs a profile or cookies that are already logged in. |

Deletes from the last `--delay` seconds in the progress log count toward the
current batch, so restarting does not skip the long pause. The run stops at
once, keeping the progress log, when SoundCloud redirects to a login or
checkpoint page or says to try again later. Rerun later with the same command
to resume. Exit codes: `0` ok, `1` some deletes failed or the run stopped, `2`
usage error.

## Selectors may break

The tool clicks SoundCloud's normal web UI: **More** (`...`), **Delete track** or **Delete playlist**, then the confirm button.
SoundCloud changes its markup often. All selectors are in the `SELECTORS` dict
at the top of `soundcloud_cleanup.py`; fix them there if listing or deleting starts
failing. Three failures in a row stop the run, and a run that finds nothing
prints a warning.

## Safety notes

- **Deletion is permanent.** Read the dry-run CSV first.
- **Keep your cookies file private.** It logs in as you. Delete it after use.
- Pacing does not guarantee SoundCloud will not limit the account. Slower is safer.
- Follow SoundCloud's terms of service.

## Testing

```bash
python3 -m unittest discover -s soundcloud-cleanup   # from repo root
```

The tests cover link and row parsing, ownership checks, the progress log,
pacing, cookies and the dry-run and delete flow with a fake browser.
They need no Playwright, account or network.

## Disclaimer

Unofficial tool, not affiliated with or endorsed by SoundCloud Global Limited. Use at your
own risk. MIT licensed. See the repository [LICENSE](../LICENSE).
