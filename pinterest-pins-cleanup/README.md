# pinterest-pins-cleanup

Delete the Pins you created on Pinterest. The tool reads your **Created** tab
(`pinterest.com/<you>/_created/`) in a browser you are logged in to, driven by
[Playwright](https://playwright.dev/python/), and deletes each Pin from its own
page. Boards are not touched; see [`pinterest-privacy/`](../pinterest-privacy/)
for those.

- Dry run is the default. It lists what would be deleted in a CSV and changes
  nothing. Nothing is deleted until you pass `--confirm`.
- Deletes are paced: 20 per batch, then a 10 minute pause, with random jitter.
- Every handled id goes into a JSONL progress log. A rerun skips ids that are
  already deleted, so you can stop and resume at any time.
- No credentials are stored in the script or printed. You log in yourself.

Requires Python 3.9 or newer and
`pip install playwright && playwright install chromium`.

## What gets deleted

- Only Pins on your Created tab are listed, so Pins you only saved are left
  alone.
- Before deleting, the tool checks that the Pin page's creator link is your
  profile. If it cannot confirm that, it does not delete the Pin.

## Usage

```bash
# Dry run: a browser opens; log in once, press Enter, get pinterest-pins-cleanup-items-<stamp>.csv
./pinterest_pins_cleanup.py --user jane_doe

# Delete
./pinterest_pins_cleanup.py --user jane_doe --confirm

# At most 25 this run, slower pacing
./pinterest_pins_cleanup.py --user jane_doe --confirm --limit 25 --batch-size 5 --delay 1800

# Exported cookies instead of a browser profile
./pinterest_pins_cleanup.py --user jane_doe --cookies cookies.json --confirm
```

| Option | Default | Meaning |
|---|---|---|
| `--user` | required | Your username from `pinterest.com/<name>/`, or the URL. |
| `--confirm` | off | Delete. Without it the run is a dry run. |
| `--limit` | none | Handle at most N items this run. |
| `--batch-size` | `20` | Deletes per batch. |
| `--delay` | `600` | Seconds to pause between batches. |
| `--item-delay` | `5` | Seconds between single deletes. |
| `--jitter` | `0.3` | Random +/- fraction applied to every pause. |
| `--max-failures` | `3` | Stop after N failed deletes in a row. |
| `--max-scrolls` | `200` | Scroll limit while listing. |
| `--progress` | `pinterest-pins-cleanup-progress.jsonl` | Resumable progress log. |
| `--csv` | `pinterest-pins-cleanup-items-<stamp>.csv` | Dry-run listing. |
| `--profile-dir` | `~/.pinterest-pins-cleanup-profile` | Persistent browser profile you log in to. |
| `--cookies` | none | JSON cookies file (Playwright storage state, or a Cookie-Editor export). |
| `--headless` | off | No browser window. Needs a profile or cookies that are already logged in. |

Deletes from the last `--delay` seconds in the progress log count toward the
current batch, so restarting does not skip the long pause. The run stops at
once, keeping the progress log, when Pinterest redirects to a login or
checkpoint page or says to try again later. Rerun later with the same command
to resume. Exit codes: `0` ok, `1` some deletes failed or the run stopped, `2`
usage error.

## Selectors may break

The tool clicks Pinterest's normal web UI: **More actions** (`...`), **Edit Pin**, **Delete**, then **Delete** to confirm.
Pinterest changes its markup often. All selectors are in the `SELECTORS` dict
at the top of `pinterest_pins_cleanup.py`; fix them there if listing or deleting starts
failing. Three failures in a row stop the run, and a run that finds nothing
prints a warning.

## Safety notes

- **Deletion is permanent.** Read the dry-run CSV first.
- **Keep your cookies file private.** It logs in as you. Delete it after use.
- Pacing does not guarantee Pinterest will not limit the account. Slower is safer.
- Follow Pinterest's terms of service.

## Testing

```bash
python3 -m unittest discover -s pinterest-pins-cleanup   # from repo root
```

The tests cover link and row parsing, ownership checks, the progress log,
pacing, cookies and the dry-run and delete flow with a fake browser.
They need no Playwright, account or network.

## Disclaimer

Unofficial tool, not affiliated with or endorsed by Pinterest, Inc.. Use at your
own risk. MIT licensed. See the repository [LICENSE](../LICENSE).
