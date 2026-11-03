# reddit-cleanup

Delete all of your own Reddit comments, and optionally your posts. The tool
uses the official Reddit API through [PRAW](https://praw.readthedocs.io/).

- Dry run is the default. Nothing changes until you pass `--apply`.
- Only items you wrote are touched. Filter by date, subreddit, score or id.
- Before any change, every selected item is saved to a backup CSV, and each
  action is recorded in a progress log as it happens.

Requires Python 3.9 or newer and `pip install praw`.

## Create a Reddit script app

1. Go to <https://www.reddit.com/prefs/apps> and click **create another app**.
2. Name: anything, for example `reddit-cleanup`. Type: **script**.
   Redirect URI: `http://localhost:8080` (it is not used, but it is required).
3. Click **create app**. The client id is the short string under the app
   name. The secret is labelled **secret**.
4. Export your credentials:

   ```bash
   export REDDIT_CLIENT_ID='abc123...'
   export REDDIT_CLIENT_SECRET='...'
   export REDDIT_USERNAME='yourname'
   export REDDIT_PASSWORD='...'
   export REDDIT_USER_AGENT='reddit-cleanup/1.0 by u/yourname'   # optional, this is the default
   ```

**Two-factor authentication:** if your account uses 2FA, add the current
6-digit code to the password with a colon: `REDDIT_PASSWORD='password:123456'`.
The code expires quickly, so start the run right after setting it.

## Usage

```bash
# Dry run (default): list every comment that would be deleted
./reddit_cleanup.py

# Delete them (asks you to type "DELETE <N> ITEMS")
./reddit_cleanup.py --apply
./reddit_cleanup.py --apply --yes          # non-interactive

# Overwrite the text first, then delete (link posts are deleted without an edit)
./reddit_cleanup.py --overwrite --apply
./reddit_cleanup.py --overwrite --placeholder '.' --apply

# Filters (dates are YYYY-MM-DD in UTC; --after is inclusive, --before is not)
./reddit_cleanup.py --before 2023-01-01 --apply
./reddit_cleanup.py --after 2020-01-01 --before 2021-01-01
./reddit_cleanup.py --subreddit AskReddit --subreddit news --apply
./reddit_cleanup.py --exclude-subreddit python --max-score 5 --apply
./reddit_cleanup.py --keep-ids abc123,t1_def456 --keep-ids-file keep.txt --apply

# Posts too, or posts only
./reddit_cleanup.py --posts --apply
./reddit_cleanup.py --posts-only --apply

# Older items from a Reddit data export (folder, comments.csv or posts.csv)
./reddit_cleanup.py --posts --from-export ~/Downloads/export_yourname --apply
```

Other options: `--backup FILE` (default `reddit-backup-<UTC stamp>.csv`; in dry
run a backup is written only when you pass it), `--log FILE` (default
`reddit-cleanup-log-<UTC stamp>.csv`), `--delay` (seconds between write calls,
default 2.0) and `--max-retries` (default 5). Rate limits, server errors and
network errors are retried with exponential backoff and jitter, honouring
Reddit's retry-after hint. Items that still fail are logged and the run
continues. Run `--help` for the full list.

Exit codes: `0` ok, `1` some items failed, `2` usage or auth error, or an
aborted confirmation.

## The 1,000-item limit

Reddit listings return only about the most recent 1,000 items each, so the
tool may not see older comments and posts. To reach them:

1. Request your data at <https://www.reddit.com/settings/data-request>.
2. When the email arrives, download and unzip the export.
3. Run with `--from-export` pointing at the folder, or at `comments.csv` or
   `posts.csv`. The tool reads the `id` column, looks the items up through the
   API in batches of 100, and merges them with the listings. Items already
   deleted are skipped.

Run it again after a big cleanup: the listings may show older items once the
newer ones are gone.

## Safety notes

- **Deletion is permanent.** Reddit has no undo. Read the dry run first.
- **Keep the backup CSV safe.** It contains the full text of everything you
  deleted. Delete it when you no longer need it.
- **Overwrite is optional.** It replaces the text before deleting. Copies
  made by archives, search engines and third parties may still persist.
- If overwriting an item fails, the item is not deleted, so you can retry.
- The progress log is flushed after every item, so a crash leaves a record.
- Your credentials are only sent to Reddit. They are never printed or logged.
- Follow Reddit's [API terms](https://www.redditinc.com/policies/data-api-terms)
  and rate limits.

## Testing

```bash
python3 -m unittest reddit-cleanup/test_reddit_cleanup.py   # from repo root
python3 test_reddit_cleanup.py                              # from this folder
```

The tests use fake Reddit objects. They need no PRAW, credentials or network.

## Disclaimer

This is an unofficial tool. It is not affiliated with or endorsed by Reddit.
Use it at your own risk. MIT licensed. See the repository [LICENSE](../LICENSE).
