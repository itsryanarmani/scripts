#!/usr/bin/env python3
"""Delete your own X (Twitter) posts and replies.

Reads the ids from your X archive export (data/tweets.js) or from a CSV of
tweet ids, then deletes them in a logged-in browser driven by Playwright, or
through the official API when you supply a user token. Dry run is the default
and only writes a CSV of what would be deleted; pass --confirm to delete.
Deletes are paced in small batches (default 15, then a 2 hour pause) because
X has locked accounts that deleted quickly. Unofficial; not affiliated with X.
"""
import argparse
import csv
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

EXIT_OK, EXIT_PARTIAL, EXIT_USAGE = 0, 1, 2
API_BASE = "https://api.x.com/2"
TOKEN_ENV = "X_USER_ACCESS_TOKEN"
CSV_FIELDS = ["id", "kind", "created_at", "url", "text"]
DONE = {"deleted", "gone"}

# X changes its markup often, so these selectors WILL break at some point.
# They are all here so a fix is one edit. Check them in your browser's
# inspector if deletes start failing.
SELECTORS = {
    "logged_in": '[data-testid="SideNav_AccountSwitcher_Button"]',
    "article": 'article:has(a[href$="/status/{id}"])',
    "caret": '[data-testid="caret"]',
    "menu_item": '[role="menuitem"]',
    "confirm": '[data-testid="confirmationSheetConfirm"]',
    "toast": '[data-testid="toast"]',
}
MISSING_TEXT = re.compile(r"this (post|page) (is unavailable|doesn.t exist)|hmm\.\.\.this page", re.I)
LIMIT_TEXT = re.compile(r"rate limit|try again later|something went wrong", re.I)
LOCK_URL = re.compile(r"/account/access|/i/flow/login", re.I)


class UsageError(Exception):
    pass


class StopRun(Exception):
    """Rate limit, lock or auth problem: stop now, keep the progress log."""


# ------------------------------------------------------------- input parsing

def archive_files(path):
    if os.path.isdir(path):
        folder = os.path.join(path, "data") if os.path.isdir(os.path.join(path, "data")) else path
        names = sorted(n for n in os.listdir(folder) if re.fullmatch(r"tweets(-part\d+)?\.js", n))
        if not names:
            raise UsageError(f"no tweets.js in {folder}")
        return [os.path.join(folder, n) for n in names]
    if not os.path.isfile(path):
        raise UsageError(f"archive file not found: {path}")
    return [path]


def parse_created(value):
    try:
        return datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y").astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_archive_text(text):
    """Items from tweets.js: `window.YTD.tweets.part0 = [ {"tweet": {...}}, ... ]`."""
    body = text.split("=", 1)[-1] if text.lstrip().startswith("window.") else text
    try:
        entries = json.loads(body)
    except ValueError as e:
        raise UsageError(f"tweets.js is not valid JSON after the prefix: {e}")
    if not isinstance(entries, list):
        raise UsageError("tweets.js does not hold a list of tweets")
    items = []
    for entry in entries:
        t = entry.get("tweet", entry) if isinstance(entry, dict) else {}
        tid = str(t.get("id_str") or t.get("id") or "").strip()
        if not tid.isdigit():
            continue
        full = t.get("full_text") or t.get("text") or ""
        kind = ("retweet" if full.startswith("RT @")
                else "reply" if t.get("in_reply_to_status_id_str") or t.get("in_reply_to_status_id")
                else "post")
        created = parse_created(t.get("created_at"))
        items.append({"id": tid, "kind": kind, "text": full,
                      "created_at": created.isoformat() if created else ""})
    return items


ID_COLUMNS = ("tweet_id", "id", "id_str", "url", "link")
STATUS_RE = re.compile(r"/status(?:es)?/(\d+)")


def id_from_cell(cell):
    cell = (cell or "").strip()
    m = STATUS_RE.search(cell)
    return m.group(1) if m else (cell if cell.isdigit() else None)


def parse_id_csv_text(text):
    """Items from a CSV of tweet ids or status URLs, with or without a header."""
    rows = [r for r in csv.reader(text.splitlines()) if r and any(c.strip() for c in r)]
    col = 0
    if rows:
        header = [c.strip().lower() for c in rows[0]]
        named = [header.index(c) for c in ID_COLUMNS if c in header]
        if named:
            col, rows = named[0], rows[1:]
    items = []
    for r in rows:
        tid = id_from_cell(r[col] if col < len(r) else "")
        if tid:
            items.append({"id": tid, "kind": "unknown", "text": "", "created_at": ""})
    return items


def load_items(args):
    items = []
    for path in args.archive:
        for f in archive_files(path):
            with open(f, encoding="utf-8-sig") as fh:
                items.extend(parse_archive_text(fh.read()))
    for path in args.ids_csv:
        if not os.path.isfile(path):
            raise UsageError(f"CSV not found: {path}")
        with open(path, encoding="utf-8-sig", newline="") as fh:
            items.extend(parse_id_csv_text(fh.read()))
    seen, out = set(), []
    for it in items:
        if it["id"] not in seen:
            seen.add(it["id"])
            it["url"] = f"https://x.com/i/status/{it['id']}"
            out.append(it)
    return out


def select(items, args, done):
    """Filter by kind and date, drop done ids, apply --limit. Newest first."""
    kinds = {"all": {"post", "reply", "unknown"}, "posts": {"post"}, "replies": {"reply"}}[args.kind]
    out = []
    for it in items:
        if it["id"] in done or it["kind"] not in kinds:
            continue
        if (args.before or args.after) and not it["created_at"]:
            continue
        if args.before and it["created_at"] >= args.before:
            continue
        if args.after and it["created_at"] < args.after:
            continue
        out.append(it)
    out.sort(key=lambda it: (it["created_at"], int(it["id"])), reverse=True)
    return out[:args.limit] if args.limit else out


# ------------------------------------------------------ progress and pacing

class ProgressLog:
    """JSONL of handled ids, flushed per line. Ids marked deleted/gone are skipped on rerun."""

    def __init__(self, path):
        self.path = path

    def rows(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # a torn last line from a crash
                if isinstance(row, dict):
                    yield row

    def done_ids(self):
        return {str(row.get("id")) for row in self.rows() if row.get("status") in DONE}

    def recent_deletes(self, window, now=None):
        """Deletes logged in the last `window` seconds, so pacing carries over a rerun."""
        now = now or datetime.now(timezone.utc)
        count = 0
        for row in self.rows():
            try:
                age = (now - datetime.fromisoformat(row["ts"])).total_seconds()
            except (KeyError, TypeError, ValueError):
                continue
            count += row.get("status") == "deleted" and age < window
        return count

    def add(self, item_id, status, error=""):
        row = {"ts": datetime.now(timezone.utc).isoformat(), "id": item_id, "status": status}
        if error:
            row["error"] = error
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())


def jittered(seconds, jitter, rng=random.random):
    """seconds +/- jitter fraction, never negative."""
    return max(0.0, seconds * (1 + jitter * (2 * rng() - 1)))


def pause_before(index, args, rng=random.random):
    """Seconds to wait before item `index` (0-based): a long pause between batches."""
    if index == 0:
        return 0.0
    if index % args.batch_size == 0:
        return jittered(args.delay, args.jitter, rng)
    return jittered(args.item_delay, args.jitter, rng)


def run_deletions(plan, delete_one, args, log, sleep=time.sleep, rng=random.random, offset=0):
    """Delete each item with pacing. `offset` deletes already count toward this batch.
    Returns (deleted, failed)."""
    ok = failed = streak = 0
    for i, item in enumerate(plan):
        wait = pause_before(i + offset, args, rng)
        if wait and (i + offset) % args.batch_size == 0:
            print(f"  batch of {args.batch_size} done; pausing {wait / 60:.0f} min "
                  f"(resume any time; done ids are skipped)")
        if wait:
            sleep(wait)
        try:
            status = delete_one(item)
        except StopRun as e:
            log.add(item["id"], "stopped", str(e))
            print(f"  stopped at {item['id']}: {e}", file=sys.stderr)
            return ok, failed + 1
        except Exception as e:  # keep going; record the failure
            failed += 1
            streak += 1
            log.add(item["id"], "failed", f"{type(e).__name__}: {e}")
            print(f"  [{i + 1}/{len(plan)}] FAILED {item['id']}: {e}")
            if streak >= args.max_failures:
                print(f"  {streak} failures in a row; stopping. Selectors may be out of date.",
                      file=sys.stderr)
                return ok, failed
            continue
        streak = 0
        ok += 1
        log.add(item["id"], status)
        print(f"  [{i + 1}/{len(plan)}] {status} {item['id']}")
    return ok, failed


def write_csv(path, plan):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(plan)


def load_cookies(path):
    """Playwright storage state, or a JSON cookie list from a browser extension."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("cookies", []) if isinstance(data, dict) else data
    same = {"no_restriction": "None", "none": "None", "lax": "Lax", "strict": "Strict"}
    out = []
    for c in raw:
        cookie = {"name": c["name"], "value": c["value"], "domain": c.get("domain", ".x.com"),
                  "path": c.get("path", "/"), "secure": bool(c.get("secure", True)),
                  "httpOnly": bool(c.get("httpOnly", False))}
        expires = c.get("expires", c.get("expirationDate"))
        if isinstance(expires, (int, float)) and expires > 0:
            cookie["expires"] = float(expires)
        if str(c.get("sameSite", "")).lower() in same:
            cookie["sameSite"] = same[str(c["sameSite"]).lower()]
        out.append(cookie)
    return out


# ------------------------------------------------------------- delete modes

def api_deleter(token):
    def delete_one(item):
        req = urllib.request.Request(f"{API_BASE}/tweets/{item['id']}", method="DELETE",
                                     headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "gone"
            if e.code in (401, 403):
                raise StopRun(f"HTTP {e.code}: check {TOKEN_ENV} has the tweet.write scope")
            if e.code == 429:
                raise StopRun("HTTP 429 rate limited; rerun later to resume")
            raise RuntimeError(f"HTTP {e.code}")
        if not body.get("data", {}).get("deleted"):
            raise RuntimeError(f"unexpected response: {str(body)[:120]}")
        return "deleted"
    return delete_one


def logged_in(page):
    try:
        page.wait_for_selector(SELECTORS["logged_in"], timeout=15000)
        return True
    except Exception:
        return False


def open_browser(args):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise UsageError("Playwright is missing: pip install playwright && playwright install chromium")
    pw = sync_playwright().start()
    ctx = None
    try:
        if args.cookies:
            ctx = pw.chromium.launch(headless=args.headless).new_context()
            ctx.add_cookies(load_cookies(args.cookies))
        else:
            ctx = pw.chromium.launch_persistent_context(os.path.expanduser(args.profile_dir),
                                                        headless=args.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://x.com/home")
        if not logged_in(page) and not (args.cookies or args.headless):
            input("Log in to X in the browser window, then press Enter here... ")
        if not logged_in(page):
            raise UsageError("not logged in; refresh the cookies file or log in with --profile-dir")
    except BaseException:
        if ctx is not None:
            ctx.close()
        pw.stop()
        raise
    return pw, ctx, page


def browser_deleter(page):
    def delete_one(item):
        page.goto(item["url"])
        page.wait_for_timeout(2500)
        if LOCK_URL.search(page.url):
            raise StopRun(f"X redirected to {page.url}; check the account in the browser")
        article = page.locator(SELECTORS["article"].format(id=item["id"])).first
        if not article.count():
            # Only read the page text when the post is absent, so a post that
            # merely quotes these phrases is never mistaken for a missing one.
            body = page.inner_text("body")
            if MISSING_TEXT.search(body):
                return "gone"
            if LIMIT_TEXT.search(body):
                raise StopRun("X shows a rate-limit or error page; rerun later to resume")
        article.locator(SELECTORS["caret"]).first.click(timeout=10000)
        page.locator(SELECTORS["menu_item"]).filter(has_text=re.compile(r"^\s*Delete\s*$")).first.click(timeout=5000)
        page.locator(SELECTORS["confirm"]).first.click(timeout=5000)
        page.wait_for_timeout(1500)
        return "deleted"
    return delete_one


# --------------------------------------------------------------------- CLI

def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Delete your own X posts and replies. Dry run by default.",
        epilog="Exit codes: 0 ok, 1 some deletes failed or the run stopped, 2 usage error.")
    ap.add_argument("--archive", action="append", default=[], metavar="PATH",
                    help="X archive folder or tweets.js (repeatable)")
    ap.add_argument("--ids-csv", action="append", default=[], metavar="PATH",
                    help="CSV of tweet ids or status URLs (repeatable)")
    ap.add_argument("--confirm", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument("--api", action="store_true",
                    help=f"delete through the X API with an OAuth 2.0 user token in ${TOKEN_ENV}")
    ap.add_argument("--kind", choices=["all", "posts", "replies"], default="all",
                    help="what to delete (default: all; retweets are never touched)")
    ap.add_argument("--before", type=parse_date, metavar="DATE", help="only items before DATE (UTC)")
    ap.add_argument("--after", type=parse_date, metavar="DATE", help="only items on/after DATE (UTC)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N items (default: no limit)")
    ap.add_argument("--batch-size", type=int, default=15, help="deletes per batch (default: 15)")
    ap.add_argument("--delay", type=float, default=7200, help="seconds between batches (default: 7200)")
    ap.add_argument("--item-delay", type=float, default=20, help="seconds between deletes (default: 20)")
    ap.add_argument("--jitter", type=float, default=0.3, help="random +/- fraction on waits (default: 0.3)")
    ap.add_argument("--max-failures", type=int, default=3, help="stop after N failures in a row (default: 3)")
    ap.add_argument("--progress", default="x-cleanup-progress.jsonl",
                    help="resumable JSONL progress log (default: %(default)s)")
    ap.add_argument("--csv", metavar="PATH", help="dry-run listing (default: x-cleanup-items-<stamp>.csv)")
    ap.add_argument("--profile-dir", default="~/.x-cleanup-profile",
                    help="persistent browser profile you log in to (default: %(default)s)")
    ap.add_argument("--cookies", metavar="PATH", help="JSON cookies file instead of a profile")
    ap.add_argument("--headless", action="store_true", help="run the browser without a window")
    args = ap.parse_args(argv)
    if not args.archive and not args.ids_csv:
        ap.error("give --archive and/or --ids-csv")
    if args.batch_size < 1 or args.limit < 0 or args.max_failures < 1:
        ap.error("--batch-size and --max-failures must be >= 1, --limit >= 0")
    if min(args.delay, args.item_delay) < 0 or not 0 <= args.jitter < 1:
        ap.error("delays must be >= 0 and --jitter in [0, 1)")
    if args.api and args.cookies:
        ap.error("--api does not use a browser; drop --cookies")
    args.csv = args.csv or "x-cleanup-items-{}.csv".format(
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    return args


def main(argv=None, env=None, sleep=time.sleep):
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    env = os.environ if env is None else env
    ctx = pw = None
    try:
        log = ProgressLog(args.progress)
        done = log.done_ids()
        items = load_items(args)
        plan = select(items, args, done)
        retweets = sum(1 for it in items if it["kind"] == "retweet")
        print(f"{len(items)} item(s) read, {len(done)} already done, {len(plan)} selected"
              + (f", {retweets} retweet(s) ignored." if retweets else "."))
        undated = sum(1 for it in items if it["kind"] == "unknown" and it["id"] not in done)
        if undated and (args.kind != "all" or args.before or args.after):
            print(f"Note: {undated} id(s) from a CSV have no kind or date, so --kind, "
                  "--before and --after leave them out.")
        if not args.confirm:
            write_csv(args.csv, plan)
            batches = -(-len(plan) // args.batch_size)
            hours = (max(0, batches - 1) * args.delay + len(plan) * args.item_delay) / 3600
            print(f"Dry run: nothing deleted. Listing written to {args.csv}.\n"
                  f"At {args.batch_size} per batch that is {batches} batch(es), about "
                  f"{hours:.1f} h. Add --confirm to delete.")
            return EXIT_OK
        if not plan:
            return EXIT_OK
        if args.api:
            token = env.get(TOKEN_ENV, "").strip()
            if not token:
                raise UsageError(f"--api needs ${TOKEN_ENV} (OAuth 2.0 user token, tweet.write scope)")
            delete_one = api_deleter(token)
        else:
            pw, ctx, page = open_browser(args)
            delete_one = browser_deleter(page)
        offset = log.recent_deletes(args.delay)
        if offset:
            print(f"{offset} delete(s) in the last {args.delay / 60:.0f} min count toward this batch.")
        ok, failed = run_deletions(plan, delete_one, args, log, sleep, offset=offset)
        print(f"\nDone: {ok} deleted or already gone, {failed} failed. Progress: {args.progress}")
        return EXIT_PARTIAL if failed else EXIT_OK
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("\nInterrupted. Rerun the same command to resume.", file=sys.stderr)
        return EXIT_PARTIAL
    finally:
        if ctx is not None:
            ctx.close()
        if pw is not None:
            pw.stop()


if __name__ == "__main__":
    sys.exit(main())
