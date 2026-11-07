# directory-submit

Browser drivers that file a live directory site on third-party boards. They
replace the throwaway helpers from the round 3 batch run. The
`website-directory-submission` skill (itsryanarmani/skills) owns the directory
registry (`directories.csv`) and the fast run recipe. This folder owns the code
that does the filing.

Do not confuse it with `../directory-submission`. That folder generates the
copy-paste packet. This folder drives the browser and writes the ledger.

## What is here

| File | Job |
|---|---|
| `lib.py` | Browser call, snapshot ref lookup, packet loader, settings, Gmail reader. |
| `ledger.py` | Writes `submissions/ledger.csv` rows. Finds the pairs still pending. |
| `run.py` | Runs one driver over many sites. Stops on a rate limit. Retries failures. |
| `drivers/` | One module per directory. See `drivers/README.md`. |

## Set up

1. Check out the fleet template repository and set `DIRSUB_REPO` to its path. The
   default is the current directory.
2. Sign in once, by hand, to each board in the `browser-personal` Chrome
   profile. The drivers never type a password. Read the `agent-browser-profiles`
   skill first. Run one browser driver at a time.
3. Put the logo and cover images in `DIRSUB_ASSETS/<site>/logo.png` and
   `cover.png`.

## Read the site packet

A driver reads `sites/<site>/data/submission.json`. Keys it uses: `short`,
`long`, `contact_email`, `tags`. It reads `name`, `tagline` and the domain from
`sites/<site>/directory.config.ts`. Set `name`, `tagline` or `url` in the JSON to
override them. An optional `categories` map holds the category to pick on each
board, for example `{"clapstorm": "Finance", "unloc": "Coding Agents & Dev Tools"}`.

## Settings

A setting comes from the environment. If it is not there, the loader reads
`NAME=value` lines from `DIRSUB_SECRETS_FILE` (default
`~/.secrets/directory-submission.env`). An error names the setting. It never
shows a value. Nothing in this folder holds a password, token or account
address, except the default contact `hello@example.xyz`.

| Name | Meaning | Default |
|---|---|---|
| `DIRSUB_REPO` | Checkout of the directory repo. | `.` |
| `DIRSUB_ASSETS` | Folder with `<site>/logo.png` and `cover.png`. | `assets` |
| `DIRSUB_LEDGER` | Ledger file to write. | `<repo>/submissions/ledger.csv` |
| `DIRSUB_EMAIL` | Contact address typed into forms. | `hello@example.xyz` |
| `DIRSUB_MAKER_NAME`, `DIRSUB_COMPANY` | Name fields on forms that ask for a person. | none, required by those drivers |
| `DIRSUB_MAIL_ACCOUNT` | Mailbox that `gog` reads for confirm links. | none, required by those drivers |
| `DIRSUB_BROWSER` | The browser command. | `browser-personal` |

## Run

```sh
cd scripts/directory-submit
python3 run.py nhs                       # every site with a packet
python3 run.py unloc --sites robotaxis,doulas
python3 run.py clapstorm --dry-run       # fill the form, file nothing
python3 run.py buildvoyage --confirm     # second step: click the emailed links
```

The loop keeps these rules:

- A pair with a ledger row is not filed again. A blocked row is filed again once
  its `retry_after` date has passed.
- The first rate limit stops the loop. The site that hit it gets a blocked row
  with a `retry_after` date. The other sites stay pending. Do not rotate
  networks or accounts to get past a limit.
- A failed run writes nothing. The next run retries it.
- Exit code 0 means done, 1 means some failed, 3 means a rate limit stopped it.

Always check the result on the board's own page. A driver that prints
"submitted" proves nothing alone.

## Write a driver

Add `drivers/<name>.py`:

```python
from lib import Result, DriverFail, b, click, fill, final_click, go, must, packet, snap

TARGET = "Example Board"   # the catalog name, exactly
DELAY = 10                 # seconds between sites
RETRY_DAYS = 1             # wait after a rate limit

def submit(site, p):
    go("https://example.com/submit")
    s = snap()
    fill(s, r'textbox "URL', p["url"])
    s = snap()
    if not final_click(must(s, r'button "Submit"')):
        return Result("skipped", "dry run")
    return Result("submitted", "https://example.com/p/" + site)
```

Use `(?:...)` groups in patterns. A plain `(...)` group changes what `find`
returns. Raise `DriverFail` when the page is not what you expect. Raise
`RateLimited` when the board says stop.
