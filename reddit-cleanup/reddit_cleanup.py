#!/usr/bin/env python3
"""Delete your own Reddit comments, and optionally your posts.

Uses the official Reddit API through PRAW and a "script" app you create at
https://www.reddit.com/prefs/apps. Credentials come from REDDIT_* environment
variables. Dry run is the default; pass --apply to change anything.
Unofficial; not affiliated with Reddit.
"""
import argparse
import csv
import os
import random
import sys
import time
from datetime import datetime, timezone

EXIT_OK, EXIT_PARTIAL, EXIT_USAGE = 0, 1, 2
ENV_VARS = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD")
DEFAULT_PLACEHOLDER = "This content was removed by its author."
BACKUP_FIELDS = ["fullname", "id", "type", "subreddit", "created_utc", "score",
                 "permalink", "title", "body", "url"]
LOG_FIELDS = ["timestamp", "fullname", "type", "action", "status", "error"]
INFO_BATCH = 100
# Exceptions retried with backoff. None means prawcore's TooManyRequests,
# ServerError and RequestException; tests set their own tuple.
RETRY_EXCEPTIONS = None


class UsageError(Exception):
    pass


def retryable_exceptions():
    if RETRY_EXCEPTIONS is not None:
        return RETRY_EXCEPTIONS
    try:
        from prawcore import exceptions as pe
    except ImportError:
        return ()
    return (pe.TooManyRequests, pe.ServerError, pe.RequestException)


def retry_after(exc):
    value = getattr(exc, "retry_after", None)
    if value is None:
        headers = getattr(getattr(exc, "response", None), "headers", None) or {}
        value = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def with_retries(fn, max_retries, sleep, what="request"):
    """Call fn(), retrying rate-limit/server/network errors with backoff + jitter."""
    errors = retryable_exceptions()
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except errors as e:
            if attempt >= max_retries:
                raise
            wait = retry_after(e)
            if wait is None:
                wait = min(60.0, 2.0 ** attempt) + random.uniform(0, 1)
            print(f"  {type(e).__name__} on {what}, retrying in {wait:.1f}s "
                  f"({attempt + 1}/{max_retries})")
            sleep(wait)


def read_credentials(env):
    missing = [k for k in ENV_VARS if not env.get(k, "").strip()]
    if missing:
        raise UsageError("missing environment variable(s): " + ", ".join(missing)
                         + ". See README.md for how to create a script app.")
    creds = {k: env[k] if k == "REDDIT_PASSWORD" else env[k].strip() for k in ENV_VARS}
    creds["REDDIT_USER_AGENT"] = (env.get("REDDIT_USER_AGENT", "").strip()
                                  or f"reddit-cleanup/1.0 by u/{creds['REDDIT_USERNAME']}")
    return creds


def connect_praw(creds):
    """The only place PRAW is touched. Tests pass their own connect function."""
    try:
        import praw
    except ImportError:
        raise UsageError("PRAW is not installed. Run: pip install praw")
    return praw.Reddit(
        client_id=creds["REDDIT_CLIENT_ID"], client_secret=creds["REDDIT_CLIENT_SECRET"],
        username=creds["REDDIT_USERNAME"], password=creds["REDDIT_PASSWORD"],
        user_agent=creds["REDDIT_USER_AGENT"], ratelimit_seconds=300, check_for_updates=False)


def login(reddit, creds):
    try:
        me = reddit.user.me()
    except Exception as e:
        raise UsageError(f"Reddit login failed ({type(e).__name__}: {e}). Check the "
                         "REDDIT_* variables; for 2FA use REDDIT_PASSWORD='password:123456'.")
    if me is None:
        raise UsageError("Reddit login failed: not authenticated as a user.")
    return str(me)


def describe(thing):
    fullname = str(thing.fullname)
    comment = fullname.startswith("t1_")
    created = float(getattr(thing, "created_utc", 0) or 0)
    permalink = str(getattr(thing, "permalink", "") or "")
    return {
        "thing": thing, "fullname": fullname, "id": str(thing.id),
        "type": "comment" if comment else "post",
        "subreddit": str(getattr(thing, "subreddit", "") or ""),
        "created": created,
        "created_utc": datetime.fromtimestamp(created, timezone.utc).isoformat(),
        "score": int(getattr(thing, "score", 0) or 0),
        "permalink": "https://www.reddit.com" + permalink if permalink.startswith("/") else permalink,
        "title": "" if comment else str(getattr(thing, "title", "") or ""),
        "body": str(getattr(thing, "body" if comment else "selftext", "") or ""),
        "url": "" if comment else str(getattr(thing, "url", "") or ""),
        "is_self": comment or bool(getattr(thing, "is_self", False)),
        "author": str(getattr(thing, "author", "") or ""),
    }


def export_files(path):
    """(fullname prefix, csv path) pairs for an export folder or a single CSV."""
    if os.path.isdir(path):
        files = [(p, os.path.join(path, n)) for p, n in (("t1_", "comments.csv"), ("t3_", "posts.csv"))]
        files = [(p, f) for p, f in files if os.path.isfile(f)]
        if not files:
            raise UsageError(f"no comments.csv or posts.csv in {path}")
        return files
    if not os.path.isfile(path):
        raise UsageError(f"export file not found: {path}")
    return [("t3_" if "post" in os.path.basename(path).lower() else "t1_", path)]


def export_fullnames(paths):
    names = []
    for path in paths:
        for prefix, f in export_files(path):
            with open(f, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                if "id" not in (reader.fieldnames or []):
                    raise UsageError(f"{f} has no 'id' column")
                for row in reader:
                    rid = (row.get("id") or "").strip().lower()
                    if rid:
                        names.append(rid if rid[:3] in ("t1_", "t3_") else prefix + rid)
    return list(dict.fromkeys(names))


def collect(reddit, username, args, sleep):
    """Fetch the user's items from listings and any export, deduped by fullname."""
    items, foreign = {}, 0

    def add(thing):
        nonlocal foreign
        d = describe(thing)
        if d["author"].lower() != username.lower():
            foreign += 1  # already deleted, or not yours
        else:
            items.setdefault(d["fullname"], d)

    redditor = reddit.redditor(username)
    if args.what in ("comments", "both"):
        for thing in redditor.comments.new(limit=None):
            add(thing)
    if args.what in ("posts", "both"):
        for thing in redditor.submissions.new(limit=None):
            add(thing)
    if args.from_export:
        names = [n for n in export_fullnames(args.from_export) if n not in items]
        print(f"Looking up {len(names)} item(s) from the export...")
        for i in range(0, len(names), INFO_BATCH):
            batch = names[i:i + INFO_BATCH]
            for thing in with_retries(lambda: list(reddit.info(fullnames=batch)),
                                      args.max_retries, sleep, "info lookup"):
                add(thing)
    if foreign:
        print(f"Ignored {foreign} item(s) already deleted or not authored by u/{username}.")
    return sorted(items.values(), key=lambda d: d["created"], reverse=True)


def bare_id(value):
    value = value.strip().lower()
    return value[3:] if value[:3] in ("t1_", "t3_") else value


def load_keep_ids(args):
    raw = [part for v in args.keep_ids for part in v.split(",")]
    if args.keep_ids_file:
        with open(args.keep_ids_file, encoding="utf-8") as f:
            for line in f:
                raw.extend(line.split("#", 1)[0].replace(",", " ").split())
    return {bare_id(v) for v in raw if v.strip()}


def sub_set(names):
    return {n.strip().lower().removeprefix("r/") for n in names}


def select(items, args, keep):
    want = {"comments": {"comment"}, "posts": {"post"}, "both": {"comment", "post"}}[args.what]
    subs, excluded = sub_set(args.subreddit), sub_set(args.exclude_subreddit)
    out = []
    for d in items:
        sub = d["subreddit"].lower()
        if (d["type"] not in want or d["id"].lower() in keep
                or (args.before is not None and d["created"] >= args.before)
                or (args.after is not None and d["created"] < args.after)
                or (subs and sub not in subs) or sub in excluded
                or (args.min_score is not None and d["score"] < args.min_score)
                or (args.max_score is not None and d["score"] > args.max_score)):
            continue
        out.append(d)
    return out


def snippet(d, width=50):
    text = " ".join((d["title"] or d["body"] or d["url"]).split())
    return text if len(text) <= width else text[:width - 3] + "..."


def print_plan(plan, found):
    print(f"{'FULLNAME':<12} {'TYPE':<8} {'SUBREDDIT':<20} {'DATE':<10} {'SCORE':>6}  SNIPPET")
    for d in plan:
        print(f"{d['fullname']:<12} {d['type']:<8} {d['subreddit'][:20]:<20} "
              f"{d['created_utc'][:10]:<10} {d['score']:>6}  {snippet(d)}")
    comments = sum(1 for d in plan if d["type"] == "comment")
    print(f"\n{len(plan)} of {found} item(s) selected: {comments} comment(s), "
          f"{len(plan) - comments} post(s).")


def write_backup(path, plan):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=BACKUP_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(plan)
        f.flush()
        os.fsync(f.fileno())
    print(f"Backup of {len(plan)} item(s) written to {path} (it contains your content; keep it safe).")


class ProgressLog:
    """CSV of per-item status, flushed after every row so a crash leaves a record."""

    def __init__(self, path):
        self.path = path
        self.file = open(path, "a", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file, fieldnames=LOG_FIELDS)
        if self.file.tell() == 0:
            self.writer.writeheader()

    def add(self, d, action, status, error=""):
        self.writer.writerow({"timestamp": datetime.now(timezone.utc).isoformat(),
                              "fullname": d["fullname"], "type": d["type"],
                              "action": action, "status": status, "error": error})
        self.file.flush()
        os.fsync(self.file.fileno())

    def close(self):
        self.file.close()


def execute(plan, args, sleep):
    """Overwrite (optional) then delete each item; returns the failure count."""
    log = ProgressLog(args.log)
    failures, writes = 0, 0

    def write(fn, what):
        nonlocal writes
        if writes and args.delay:
            sleep(args.delay)
        writes += 1
        with_retries(fn, args.max_retries, sleep, what)

    try:
        for n, d in enumerate(plan, 1):
            thing, action = d["thing"], "edit"
            try:
                if args.overwrite and d["is_self"]:
                    write(lambda: thing.edit(args.placeholder), f"edit {d['fullname']}")
                    log.add(d, "edit", "ok")
                elif args.overwrite:
                    log.add(d, "edit", "skipped", "link post cannot be edited")
                action = "delete"
                write(thing.delete, f"delete {d['fullname']}")
            except Exception as e:  # keep going; record the failure
                failures += 1
                log.add(d, action, "failed", f"{type(e).__name__}: {e}")
                print(f"  [{n}/{len(plan)}] FAILED {action} {d['fullname']}: {e}")
                continue
            log.add(d, "delete", "ok")
            print(f"  [{n}/{len(plan)}] deleted {d['type']} {d['fullname']}")
    finally:
        log.close()
    print(f"\nProgress log: {args.log}\nDone: {len(plan) - failures} deleted, {failures} failed.")
    return failures


def confirm(count, args, input_fn):
    if args.yes:
        return True
    expected = f"DELETE {count} ITEMS"
    try:
        typed = input_fn(f"This is permanent. Type '{expected}' to confirm: ")
    except EOFError:
        typed = ""
    return typed.strip() == expected


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Delete your own Reddit comments (and optionally posts). Dry run by default.",
        epilog="Exit codes: 0 ok, 1 some items failed, 2 usage/auth error or aborted.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="apply", action="store_false",
                      help="show the plan and change nothing (default)")
    mode.add_argument("--apply", dest="apply", action="store_true", help="actually delete")
    what = ap.add_mutually_exclusive_group()
    what.add_argument("--comments-only", dest="what", action="store_const", const="comments",
                      help="comments only (default)")
    what.add_argument("--posts", dest="what", action="store_const", const="both",
                      help="comments and posts")
    what.add_argument("--posts-only", dest="what", action="store_const", const="posts",
                      help="posts only")
    ap.set_defaults(apply=False, what="comments")
    ap.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    ap.add_argument("--overwrite", action="store_true",
                    help="edit text to --placeholder before deleting (link posts are not edited)")
    ap.add_argument("--placeholder", default=DEFAULT_PLACEHOLDER,
                    help="overwrite text (default: %(default)r)")
    ap.add_argument("--before", type=parse_date, metavar="DATE",
                    help="only items created before DATE (YYYY-MM-DD, UTC)")
    ap.add_argument("--after", type=parse_date, metavar="DATE",
                    help="only items created on or after DATE (YYYY-MM-DD, UTC)")
    ap.add_argument("--subreddit", action="append", default=[], metavar="NAME",
                    help="only these subreddits (repeatable, case-insensitive)")
    ap.add_argument("--exclude-subreddit", action="append", default=[], metavar="NAME",
                    help="skip these subreddits (repeatable)")
    ap.add_argument("--min-score", type=int, metavar="N", help="only items with score >= N")
    ap.add_argument("--max-score", type=int, metavar="N", help="only items with score <= N")
    ap.add_argument("--keep-ids", action="append", default=[], metavar="ID[,ID...]",
                    help="never touch these ids or fullnames (repeatable)")
    ap.add_argument("--keep-ids-file", metavar="PATH", help="file of ids to keep, one per line")
    ap.add_argument("--from-export", action="append", default=[], metavar="PATH",
                    help="Reddit data export folder, comments.csv or posts.csv (repeatable)")
    ap.add_argument("--backup", metavar="PATH",
                    help="backup CSV (default with --apply: reddit-backup-<UTC stamp>.csv)")
    ap.add_argument("--log", metavar="PATH",
                    help="progress log CSV (default: reddit-cleanup-log-<UTC stamp>.csv)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between writes (default: 2.0)")
    ap.add_argument("--max-retries", type=int, default=5,
                    help="retries on rate limits and server/network errors (default: 5)")
    args = ap.parse_args(argv)
    if args.delay < 0 or args.max_retries < 0:
        ap.error("--delay and --max-retries must be >= 0")
    if not args.placeholder.strip():
        ap.error("--placeholder must not be empty")
    if args.before is not None and args.after is not None and args.after >= args.before:
        ap.error("--after must be earlier than --before")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.log = args.log or f"reddit-cleanup-log-{stamp}.csv"
    args.backup_given = args.backup is not None
    args.backup = args.backup or f"reddit-backup-{stamp}.csv"
    return args


def main(argv=None, env=None, connect=None, sleep=time.sleep, input_fn=input):
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    try:
        creds = read_credentials(os.environ if env is None else env)
        keep = load_keep_ids(args)
        reddit = (connect or connect_praw)(creds)
        username = login(reddit, creds)
        print(f"Logged in as u/{username}. Fetching your items...")
        items = collect(reddit, username, args, sleep)
        plan = select(items, args, keep)
        print_plan(plan, len(items))
        if not args.apply:
            if args.backup_given and plan:
                write_backup(args.backup, plan)
            print("\nDry run: nothing changed. Re-run with --apply to delete these items.")
            return EXIT_OK
        if not plan:
            return EXIT_OK
        if not confirm(len(plan), args, input_fn):
            print("Aborted: confirmation did not match. Nothing changed.", file=sys.stderr)
            return EXIT_USAGE
        write_backup(args.backup, plan)
        return EXIT_PARTIAL if execute(plan, args, sleep) else EXIT_OK
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("\nInterrupted. Items handled so far are in the progress log.", file=sys.stderr)
        return EXIT_PARTIAL
    except Exception as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
