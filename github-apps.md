# GitHub Apps

Use an App for automation that needs its own permissions and rate budget.
Use a personal token for short tasks that must act as your user.
The existing Boat installation returned `x-ratelimit-limit: 12500` on 2026-10-11.
That measured limit belongs to this installation. Other installations can have different limits.

## Per-repo fleet

Use a separate App installation when one private repository exhausts a shared budget.
See [Per-repository GitHub App fleet](github-app-per-repo-fleet.md) for names, permissions, and rollout commands.
Measure the new installation limit before assigning work.

## Create and install

Install Python 3.9 or later, OpenSSL, curl, zsh, and `browser-personal` first.
The browser command must work in `zsh -ic` and use your personal Chrome login.
Run the helper from this repository, or put it on your `PATH`.

```sh
./gh-app create --name my-runner-app \
  --perm administration=write --perm actions=read
./gh-app install my-runner-app --owner YOUR_GITHUB_LOGIN
```

Creation opens a local form in a new Chrome tab.
Submit the form. Then approve the App name on GitHub.
The helper waits up to ten minutes for the redirect.
Set `GH_APP_WAIT_SECONDS` to change that limit.
Use the returned `APP_SLUG` for installation when it differs from the chosen name.
Choose the repositories on GitHub and finish installation.
The helper checks the saved App ID and expected account before recording the installation ID.

Add `--hook-url https://example.com/webhook --allow-hook-host example.com --event workflow_job` for an active webhook.
The helper prints the approved destination host before it opens Chrome.
Use `--owner` to specify the expected installation account.
Repeat `--perm` and `--event` as needed. Events require a webhook URL.
Add `--public` only when other accounts must install the App.
Without that flag, the App is private.
Without a webhook URL, the manifest uses an inactive `https://example.com/unused` placeholder.
GitHub requires a URL in the webhook object. The inactive hook sends no events.

Files go under `~/Documents/Personal/.secrets/<name>/`:

- `app.env` holds `APP_ID`, `APP_SLUG`, and `APP_CLIENT_ID`.
- Installation adds `APP_INSTALLATION_ID` to `app.env`.
- `app.pem` holds the original private key.
- `app-pkcs8.pem` holds the converted private key.
- `conversion.json` preserves the conversion response, including the webhook secret.
- `create.html` holds the manifest form.

The folder uses mode `0700`. All files use mode `0600`.
Creation refuses an existing folder. Keep saved keys out of Git.
A failed conversion or browser wait can leave the folder in place.
Check GitHub before retrying. Move the folder aside only after checking its contents.
If key conversion fails, recover from `conversion.json`; the redirect code cannot be reused.

## Request a token

`token` deliberately writes a secret to stdout. Capture it instead of displaying it.

```sh
GH_TOKEN="$(./gh-app token my-runner-app)" gh api installation/repositories
```

Creation and installation never print secrets.
The helper signs an RS256 JWT with OpenSSL and exchanges it for an installation token.
Its JWT starts 60 seconds in the past and expires 540 seconds in the future.
The token has only the permissions and repositories granted to the installation.

## Traps and Worker use

The manifest redirect code expires after one hour.
The browser tab list is shared with other sessions.
Creation matches a random `state` in the redirect URL.
Installation follows only the new tab opened by this run.
See GitHub's [manifest flow](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest).

GitHub returns a PKCS#1 key. WebCrypto imports the key as PKCS#8.
The helper uses `openssl pkcs8 -topk8 -nocrypt` to convert it.
The [Boat Worker change](https://github.com/itsryanarmani/scripts/pull/527) uses this pattern:

1. Read `APP_ID`, `APP_INSTALLATION_ID`, and `APP_PRIVATE_KEY` from Worker secrets.
2. Decode the PKCS#8 PEM body into DER bytes.
3. Import it with `crypto.subtle.importKey` using `RSASSA-PKCS1-v1_5` and `SHA-256`.
4. Encode the JWT header and payload with base64url, without padding.
5. Sign those two parts with `crypto.subtle.sign`.
6. Send the JWT to `POST /app/installations/{id}/access_tokens`.
7. Cache the installation token until five minutes before its expiry.

Store the contents of `app-pkcs8.pem` as `APP_PRIVATE_KEY`.
See GitHub's [installation token guide](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app).

## Verify without App changes

Run `python3 gh-app.test.py`.
The E2E test uses a fake browser and API with a temporary home folder.
It checks creation, installation, file modes, shared tabs, failures, and real OpenSSL signatures.
Its final `PASS` line provides a repeatable result. It does not contact GitHub.
