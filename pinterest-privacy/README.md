# pinterest-privacy

Make all of your Pinterest boards private (secret) in one go, or delete
them if you choose to. The tool uses the official Pinterest API v5. A browser
mode is also included. It drives Pinterest's normal web UI after you log in
yourself.

- Dry run is the default. Nothing changes until you pass `--apply`.
- Only `PUBLIC` boards are changed. `SECRET` and `PROTECTED` boards are skipped.
- Every change is recorded in a JSON log, and `--undo` can reverse it.

## Requirements

- Python 3.9 or newer. API mode uses only the standard library.
- Browser mode only: `pip install playwright && playwright install chromium`

## Get a Pinterest API access token

1. Create an app at <https://developers.pinterest.com/apps/>. New apps may
   start with **Trial** access. Trial access is enough to manage your own
   boards.
2. Generate an access token with the **`boards:read`** and **`boards:write`**
   scopes. Use the developer portal's token generator or the standard OAuth
   flow.
3. Export it in your shell:

   ```bash
   export PINTEREST_ACCESS_TOKEN='pina_...'
   ```

## Usage

```bash
# Dry run (default): show which boards would become secret
./pinterest_privacy.py

# Make every public board secret
./pinterest_privacy.py --apply

# Only some boards (case-insensitive substring, glob, or exact board id)
./pinterest_privacy.py --include 'recipes' --include 'travel*' --exclude 'shared' --apply
./pinterest_privacy.py --include 1234567890123456789 --apply

# Undo: restore boards to the privacy recorded in a log (dry run first)
./pinterest_privacy.py --undo pinterest-privacy-log-20261103T120000Z.json
./pinterest_privacy.py --undo pinterest-privacy-log-20261103T120000Z.json --apply

# Delete matched boards (asks you to type "DELETE <N> BOARDS")
./pinterest_privacy.py --delete --include 'old*'            # dry run
./pinterest_privacy.py --delete --include 'old*' --apply
./pinterest_privacy.py --delete --apply --yes-i-understand-delete   # non-interactive

# Browser mode: log in yourself in the opened window, then press Enter
./pinterest_privacy.py --browser --username yourname          # dry run
./pinterest_privacy.py --browser --username yourname --apply
```

Other options: `--delay` (seconds between writes, default 0.5), `--max-retries`
(retries on HTTP 429 and 5xx, default 5), `--log FILE`, `--api-base URL` (or
`PINTEREST_API_BASE`, for testing), `--profile-dir`, and `--screenshot-dir`.
Run `--help` for the full list.

Exit codes: `0` ok, `1` some changes failed, `2` usage or auth error, or an
aborted delete.

### Browser mode

Browser mode opens a headed Chromium window with its own profile
(`~/.pinterest-privacy-profile` by default). You log in yourself. For each
board, the tool uses only the normal UI: it opens the board, clicks the ⋯
options button, clicks **Edit board**, ticks the secret checkbox if it is not
already ticked, and clicks **Save** or **Done**. If a step fails, the tool
saves a screenshot to `pinterest-privacy-screenshots/`.

Browser mode does not extract cookies, call internal APIs or intercept
requests. Pinterest's UI changes often, so the selectors may need updating.
Delete is API-only. To delete boards in the browser, do it by hand.

## Safety notes

- **Dry run is the default.** Read the plan before you add `--apply`.
- **Deletion is serious.** Pinterest only lets you restore deleted boards for
  about 7 days, from its account settings. `--undo` cannot restore deleted
  boards.
- **Secret does not mean only you.** Collaborators on a board can still see it
  after it becomes secret.
- **Keep the log file.** `--undo` needs it. The tool rewrites the log
  atomically after every change, so a crash keeps what was done.
- Undo restores boards changed in API mode. Reverse browser-mode changes by
  hand.

## Privacy

Your token stays on your machine. The tool sends it only to the Pinterest API,
in the `Authorization` header. It is never printed or written to the log.

## Testing

```bash
python3 -m unittest pinterest-privacy/test_pinterest_privacy.py   # from repo root
python3 test_pinterest_privacy.py                                 # from this folder
```

The tests run against a local mock of the API. They need no token or network.

## Disclaimer

This is an unofficial tool. It is not affiliated with or endorsed by
Pinterest. Use it at your own risk. Respect Pinterest's Terms of Service and
API rate limits. MIT licensed. See the repository [LICENSE](../LICENSE).
