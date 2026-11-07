# Per-repository GitHub App fleet

Give a busy private repository its own App and installation.
Register a new App for each target repository.
This separates its REST budget from other repositories.
Selecting one repository within a shared installation does not split that budget.
Use installation tokens for this budget; user tokens share the user's budget.
Minting more tokens for one installation does not create more budgets.

## Limits and choice

A user or organization can register up to **100 Apps**.
This is a registration limit, not an installation limit.
See GitHub's [registration limits](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app).

The target fleet budget is **12,500 REST requests per hour per installation**.
Measure each new installation before assigning work.
GitHub documents a 5,000 minimum and a 12,500 ceiling outside Enterprise Cloud.
Repository count and organization membership affect scaling.
A single selected repository does not guarantee 12,500.
Enterprise Cloud organization installations have a 15,000 limit.
See GitHub's [REST limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#primary-rate-limit-for-github-app-installations).

| App pattern | Use |
| --- | --- |
| Shared `boat-runners` | Runner management and its existing permissions. |
| Shared `sec-fleet` | Security automation with modest shared traffic. |
| Per-repository fleet | Heavy automation that competes for the shared installation budget. |

Keep shared Apps for their existing tasks.
Keep an inventory of registered Apps to reserve room below the 100-App limit.
Do not use extra Apps to bypass secondary limits.
Cache responses and honor GitHub's retry instructions.

## Names and permissions

Use `pooriaarab-<short>-fleet` for the App name and expected slug.
Choose a short alias that does not disclose the private repository name.
Use `pooriaarab-<short>-fleet-app` for its secrets folder (`<name>-app`).
Keep the alias-to-repository map in private records.
Public examples use only the alias `demo`.

Mirror the `pooriaarab-sec-fleet` repository permissions:

| Permission | Access |
| --- | --- |
| `contents` | write |
| `pull_requests` | write |
| `issues` | write |
| `workflows` | write |
| `actions` | read |
| `checks` | read |
| `statuses` | read |

GitHub adds metadata read access automatically.
Do not add administration or organization permissions.
The helper stores this template in its documented `STANDARD_PERMS` array.

## Plan and install

Read [GitHub Apps](github-apps.md) for prerequisites and the [gh-app helper](gh-app).
Run the rollout helper from this checkout:

```sh
./gh-app-per-repo-rollout plan demo
```

`plan` prints exact create, install, and captured-token commands.
It does not open a browser, create files, or contact GitHub.
Review the commands before running them.
The printed creation command uses the permissions above and keeps the App private.
The operator completes creation through `gh-app` when ready.

`gh-app create` saves a folder named after the App.
The plan then moves it to the required `<name>-app` folder.
It refuses creation when that destination already exists.
Run from a shell with command tracing disabled to keep captured tokens out of logs.
If GitHub assigns another slug, use the saved `APP_SLUG` for the install command.
The token command uses the secrets folder name, not the slug.

During installation, choose **Only select repositories**.
Select **only the target private repository** under `itsryanarmani`.
Do not select all repositories.
`gh-app install` checks the account and App ID, but does not enforce repository selection.
Confirm the single selected repository in GitHub before assigning automation.

## Verify

```sh
./gh-app-per-repo-rollout verify demo
./gh-app-per-repo-rollout verify demo --online
```

Local verification checks `~/Documents/Personal/.secrets/pooriaarab-demo-fleet-app/app.env` and `app.pem`.
It requires valid `APP_ID`, `APP_SLUG`, and `APP_INSTALLATION_ID` fields.
It parses the file as data and never executes its contents.
This check does not prove that the saved credentials work.

`--online` mints an installation token and calls `gh api rate_limit`.
It prints only numeric `limit`, `remaining`, and `reset` values for the core REST budget.
It withholds token output and API errors.
It does not create or install an App.
Record the measured limit in the private inventory; do not assume 12,500.

Run `./gh-app-per-repo-rollout.test.sh` for the smoke test.
Its fake commands check planning, invalid configuration, online success, and secret filtering.
The final `PASS` line provides a repeatable result without contacting GitHub.

## Boat boxes

Runner and agent boxes use `~/Documents/Personal/.secrets/` for GitHub App keys.
After you create or rotate a per-repo fleet App on the Mac, sync its folders to the
fleet pool:

```sh
./boat-fleet-app-secrets-sync --check   # list folders and target boxes
./boat-fleet-app-secrets-sync           # push to every box in ~/.sec-fleet/boxes.txt
```

The script copies each `pooriaarab-*-fleet-app/` directory with `tar` over `box ssh`.
It sets mode `700` on folders and `600` on key files. It never prints secrets.
Re-run after adding a new wave-1 row or registering a new per-repo App.

## Wave 2 batch rollout

Keep the repository-to-short manifest in a private repository only.
Do not commit that list to public repositories.

From this checkout, after wave 2 lands on `main`:

```sh
manifest=~/private-notes/github-app-per-repo-wave2-manifest.tsv
./gh-app-per-repo-rollout batch-status "$manifest"
./gh-app-per-repo-rollout batch-plan "$manifest" --limit 1
./gh-app-per-repo-rollout batch-verify "$manifest"
```

Register one App at a time in Chrome (`gh-app create` / `install`).
Update the private registry row to **live** with IDs from `app.env`.
Then sync keys to Boat boxes (see above).
