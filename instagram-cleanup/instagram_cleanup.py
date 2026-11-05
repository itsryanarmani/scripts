#!/usr/bin/env python3
"""Delete your own Instagram comments in batches through Your Activity.

Drives instagram.com/your_activity/interactions/comments with Playwright in a
browser you are logged in to: Select, tick a batch, Delete. "Something went
wrong" is retried with exponential backoff. Dry run (the default) only writes
a CSV; pass --confirm to delete. Unofficial; not affiliated with Meta.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

TOOL = "instagram-cleanup"
HOME_URL = "https://www.instagram.com/"
ACTIVITY_URL = HOME_URL + "your_activity/interactions/comments"
COOKIE_DOMAIN = ".instagram.com"
KINDS = {"comment"}

# Your Activity has almost no stable attributes, so these selectors WILL break
# at some point. They are all here so a fix is one edit in your inspector.
SELECTORS = {
    "logged_in": 'svg[aria-label="Home"], a[href="/direct/inbox/"]',
    "select": 'span:text-is("Select"), div[role="button"]:text-is("Select")',
    "checkbox": '[aria-label="Toggle checkbox"]',
    "delete": 'span:text-is("Delete"), div[role="button"]:text-is("Delete")',
    "confirm": '[role="dialog"] button:has-text("Delete"), [role="dialog"] [role="button"]:has-text("Delete")',
    "notice": '[role="dialog"], [role="alert"], [data-bloks-name="bk.components.Toast"]',
}
ERROR_TEXT = re.compile(r"something went wrong", re.I)
LIMIT_TEXT = re.compile(r"try again later|we limit how often|action blocked", re.I)
AGE_LINE = re.compile(r"^\d+\s*[smhdwy]$|^(edited|reply|see translation)$", re.I)
BLOCK_URL = re.compile(r"/accounts/login|/challenge|/accounts/suspended", re.I)

# A row (comment text + post thumbnail) is the largest ancestor holding one checkbox.
ROWS_JS = """([sel]) => [...document.querySelectorAll(sel.checkbox)].map(cb => {
  let row = cb;
  for (let i = 0; i < 12 && row.parentElement && !/^(MAIN|BODY|FORM)$/.test(row.parentElement.tagName)
       && row.parentElement.querySelectorAll(sel.checkbox).length === 1; i++) row = row.parentElement;
  const img = row.querySelector('img');
  return {text: row.innerText.trim().slice(0, 300), img: img ? img.getAttribute('src') || '' : ''};
})"""


# ----------------------------------------------------------- site logic

def row_key(text, img):
    """Stable id for a comment row: Instagram shows no comment id on this page.
    Lines like "2w" or "Reply" are dropped so the id does not drift with age."""
    lines = [ln.strip() for ln in (text or "").splitlines()]
    words = " ".join(" ".join(ln for ln in lines if ln and not AGE_LINE.match(ln)).split())
    thumb = (img or "").split("?", 1)[0].rsplit("/", 1)[-1]
    return hashlib.sha1(f"{words}|{thumb}".encode()).hexdigest()[:16]


def rows_to_items(raw):
    """Items in page order; a repeated text+thumbnail gets a #2, #3 suffix."""
    seen, out = {}, []
    for r in raw:
        key = row_key(r.get("text"), r.get("img"))
        seen[key] = seen.get(key, 0) + 1
        out.append({"id": key if seen[key] == 1 else f"{key}#{seen[key]}", "kind": "comment",
                    "text": r.get("text", ""), "url": ACTIVITY_URL})
    return out


def backoff_delay(attempt, base, cap=3600.0, rng=random.random):
    """Exponential backoff: base*2^attempt capped, randomised in its top half."""
    ceiling = min(cap, base * 2 ** attempt)
    return ceiling / 2 + rng() * ceiling / 2


def try_batch(batch, delete_batch, args, sleep=time.sleep, rng=random.random):
    """delete_batch(batch), retried with exponential backoff on TryAgain."""
    for attempt in range(args.max_retries):
        try:
            return delete_batch(batch)
        except TryAgain as e:
            wait = backoff_delay(attempt, args.backoff, rng=rng)
            print(f"  {e}; retry {attempt + 1}/{args.max_retries} in {wait / 60:.1f} min")
            sleep(wait)
    return delete_batch(batch)  # a TryAgain now ends the run


def run_batches(plan, delete_batch, args, log, sleep=time.sleep, rng=random.random):
    """Delete the plan in batches. Returns (deleted, failed)."""
    ok = failed = streak = 0
    size = args.batch_size
    for n, batch in enumerate(plan[i:i + size] for i in range(0, len(plan), size)):
        if n:
            sleep(jittered(args.delay, args.jitter, rng))
        try:
            statuses = try_batch(batch, delete_batch, args, sleep, rng)
        except StopRun as e:  # includes a TryAgain that outlived its retries
            for it in batch:
                log.add(it["id"], "stopped", str(e))
            print(f"  stopped: {e}. Rerun later to resume.", file=sys.stderr)
            return ok, failed + len(batch)
        except Exception as e:  # keep going; record the failure
            for it in batch:
                log.add(it["id"], "failed", f"{type(e).__name__}: {e}")
            failed, streak = failed + len(batch), streak + 1
            print(f"  batch {n + 1} FAILED: {e}")
            if streak >= args.max_failures:
                print(f"  {streak} failed batches in a row; stopping. Selectors may be out of date.",
                      file=sys.stderr)
                return ok, failed
            continue
        streak = deleted = 0
        for it in batch:
            status = statuses.get(it["id"], "deleted")
            log.add(it["id"], status)
            deleted += status == "deleted"
        ok, failed = ok + deleted, failed + len(batch) - deleted
        print(f"  batch {n + 1}: deleted {deleted} of {len(batch)} comment(s)")
    return ok, failed


def check_page(page):
    """Read only dialogs and toasts, so a comment quoting these phrases is not a false alarm."""
    if BLOCK_URL.search(page.url):
        raise StopRun(f"Instagram redirected to {page.url}; check the account in the browser")
    notices = " ".join(page.eval_on_selector_all(SELECTORS["notice"], "els => els.map(e => e.innerText)"))
    if LIMIT_TEXT.search(notices):
        raise StopRun("Instagram limited this action; rerun later to resume")
    if ERROR_TEXT.search(notices):
        raise TryAgain("Instagram says something went wrong")


def open_select_mode(page):  # Select shows the checkboxes; nothing is deleted
    page.goto(ACTIVITY_URL)
    page.wait_for_timeout(4000)
    check_page(page)
    page.locator(SELECTORS["select"]).first.click(timeout=10000)
    page.wait_for_timeout(1500)


def collect(page, args, done):
    open_select_mode(page)
    return scroll_collect(page, lambda: rows_to_items(page.evaluate(ROWS_JS, [SELECTORS])),
                          args, done, KINDS)


def delete_batch(page, batch, args):
    """Tick the batch's rows (re-read before each tick so the index cannot shift), then
    Delete once. A row never found is not_found, not done, so a rerun lists it again."""
    open_select_mode(page)
    wanted, statuses = {it["id"] for it in batch}, {}
    for _ in range(args.max_scrolls):
        while True:
            rows = rows_to_items(page.evaluate(ROWS_JS, [SELECTORS]))
            index = next((i for i, it in enumerate(rows)
                          if it["id"] in wanted and it["id"] not in statuses), None)
            if index is None:
                break
            page.locator(SELECTORS["checkbox"]).nth(index).click(timeout=5000)
            statuses[rows[index]["id"]] = "deleted"
            page.wait_for_timeout(int(jittered(args.item_delay, args.jitter) * 1000))
        if len(statuses) == len(wanted):
            break
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1500)
    if not statuses:
        raise RuntimeError("none of the batch's comments were found on the page")
    page.locator(SELECTORS["delete"]).last.click(timeout=5000)
    page.locator(SELECTORS["confirm"]).first.click(timeout=5000)
    page.wait_for_timeout(4000)
    try:
        check_page(page)
    except TryAgain:  # Delete was clicked: do not retry blindly, a rerun lists what is left
        raise RuntimeError("Instagram showed an error after Delete; rerun to see what is left")
    return {i: statuses.get(i, "not_found") for i in wanted}


# ------------------------------------------------------------------- core

EXIT_OK, EXIT_PARTIAL, EXIT_USAGE = 0, 1, 2
CSV_FIELDS = ["id", "kind", "url", "text"]
DONE = {"deleted", "gone"}


class UsageError(Exception):
    pass


class StopRun(Exception):
    """Rate limit, lock or login problem: stop now, keep the progress log."""


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
        print(f"  [{i + 1}/{len(plan)}] {status} {item['kind']} {item['id']}")
    return ok, failed


def select(items, done, kinds, limit):
    """Drop done ids and kinds not asked for, then apply --limit."""
    out = [it for it in items if it["id"] not in done and it["kind"] in kinds]
    return out[:limit] if limit else out


def merge_items(found, new):
    """Add new items to the ordered dict `found` by id; returns how many were new."""
    before = len(found)
    for it in new:
        if it.get("id"):
            found.setdefault(it["id"], it)
    return len(found) - before


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
        cookie = {"name": c["name"], "value": c["value"], "domain": c.get("domain", COOKIE_DOMAIN),
                  "path": c.get("path", "/"), "secure": bool(c.get("secure", True)),
                  "httpOnly": bool(c.get("httpOnly", False))}
        expires = c.get("expires", c.get("expirationDate"))
        if isinstance(expires, (int, float)) and expires > 0:
            cookie["expires"] = float(expires)
        if str(c.get("sameSite", "")).lower() in same:
            cookie["sameSite"] = same[str(c["sameSite"]).lower()]
        out.append(cookie)
    return out


# ------------------------------------------------------------------ browser

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
        page.goto(HOME_URL)
        if not logged_in(page) and not (args.cookies or args.headless):
            input("Log in in the browser window, then press Enter here... ")
        if not logged_in(page):
            raise UsageError("not logged in; refresh the cookies file or log in with --profile-dir")
    except BaseException:
        if ctx is not None:
            ctx.close()
        pw.stop()
        raise
    return pw, ctx, page


def scroll_collect(page, extract, args, done, kinds, on_cap=None):
    """Scroll, calling extract() for visible items, until no new ones appear or enough are found.
    on_cap() runs when --max-scrolls ran out first."""
    found, idle = {}, 0
    for _ in range(args.max_scrolls):
        new = merge_items(found, extract())
        idle = 0 if new else idle + 1
        wanted = sum(1 for k, it in found.items() if k not in done and it["kind"] in kinds)
        if idle >= 3 or (args.limit and wanted >= args.limit):
            break
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1500)
    else:
        print("warning: listing stopped at --max-scrolls; raise it to reach older items.",
              file=sys.stderr)
        if on_cap:
            on_cap()
    return list(found.values())


# --------------------------------------------------------------------- CLI

def add_common_args(ap, batch_size, delay, item_delay):
    ap.add_argument("--confirm", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument("--limit", type=int, default=0, help="handle at most N items (default: no limit)")
    ap.add_argument("--batch-size", type=int, default=batch_size,
                    help="deletes per batch (default: %(default)s)")
    ap.add_argument("--delay", type=float, default=delay,
                    help="seconds between batches (default: %(default)s)")
    ap.add_argument("--item-delay", type=float, default=item_delay,
                    help="seconds between deletes (default: %(default)s)")
    ap.add_argument("--jitter", type=float, default=0.3, help="random +/- fraction on waits (default: 0.3)")
    ap.add_argument("--max-failures", type=int, default=3, help="stop after N failures in a row (default: 3)")
    ap.add_argument("--max-scrolls", type=int, default=200, help="scroll limit while listing (default: 200)")
    ap.add_argument("--progress", default=f"{TOOL}-progress.jsonl",
                    help="resumable JSONL progress log (default: %(default)s)")
    ap.add_argument("--csv", metavar="PATH", help=f"dry-run listing (default: {TOOL}-items-<stamp>.csv)")
    ap.add_argument("--profile-dir", default=f"~/.{TOOL}-profile",
                    help="persistent browser profile you log in to (default: %(default)s)")
    ap.add_argument("--cookies", metavar="PATH", help="JSON cookies file instead of a profile")
    ap.add_argument("--headless", action="store_true", help="run the browser without a window")


def check_common_args(ap, args):
    if args.batch_size < 1 or args.limit < 0 or args.max_failures < 1 or args.max_scrolls < 1:
        ap.error("--batch-size, --max-failures and --max-scrolls must be >= 1, --limit >= 0")
    if min(args.delay, args.item_delay) < 0 or not 0 <= args.jitter < 1:
        ap.error("delays must be >= 0 and --jitter in [0, 1)")
    args.csv = args.csv or "{}-items-{}.csv".format(
        TOOL, datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))


def run(args, collect, delete_one, kinds, sleep=time.sleep, browser=open_browser, runner=None):
    """Shared flow: list, write the CSV on a dry run, or delete with pacing.
    `runner(plan, page, args, log, sleep, offset)` replaces the one-by-one loop."""
    pw = ctx = None
    try:
        log = ProgressLog(args.progress)
        done = log.done_ids()
        pw, ctx, page = browser(args)
        items = collect(page, args, done)
        plan = select(items, done, kinds, args.limit)
        print(f"{len(items)} item(s) found, {len(done)} already done, {len(plan)} selected.")
        if not items:
            print("warning: nothing found. Check that you are logged in and that the "
                  "selectors still match.", file=sys.stderr)
        if not args.confirm:
            write_csv(args.csv, plan)
            print(f"Dry run: nothing deleted. Listing written to {args.csv}. Add --confirm to delete.")
            return EXIT_OK
        offset = log.recent_deletes(args.delay)
        if offset:
            print(f"{offset} delete(s) in the last {args.delay / 60:.0f} min count toward this batch.")
        if runner:
            ok, failed = runner(plan, page, args, log, sleep, offset)
        else:
            ok, failed = run_deletions(plan, lambda it: delete_one(page, it), args, log, sleep,
                                       offset=offset)
        print(f"\nDone: {ok} deleted or already gone, {failed} failed. Progress: {args.progress}")
        return EXIT_PARTIAL if failed else EXIT_OK
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    except StopRun as e:
        print(f"stopped: {e}", file=sys.stderr)
        return EXIT_PARTIAL
    except KeyboardInterrupt:
        print("\nInterrupted. Rerun the same command to resume.", file=sys.stderr)
        return EXIT_PARTIAL
    finally:
        if ctx is not None:
            ctx.close()
        if pw is not None:
            pw.stop()


class TryAgain(StopRun):
    """Instagram showed "Something went wrong": run_batches backs off and retries."""


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Delete your own Instagram comments via Your Activity. Dry run by default.",
        epilog="Exit codes: 0 ok, 1 some deletes failed or the run stopped, 2 usage error.")
    add_common_args(ap, batch_size=10, delay=300, item_delay=1)
    ap.add_argument("--max-retries", type=int, default=5,
                    help='retries per batch after "Something went wrong" (default: 5)')
    ap.add_argument("--backoff", type=float, default=60,
                    help="first backoff wait in seconds, doubling each retry (default: 60)")
    args = ap.parse_args(argv)
    check_common_args(ap, args)
    if args.max_retries < 0 or args.backoff < 0:
        ap.error("--max-retries and --backoff must be >= 0")
    return args


def main(argv=None, sleep=time.sleep, browser=open_browser):
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK

    def runner(plan, page, args, log, sleep, offset):
        if offset >= args.batch_size:
            sleep(jittered(args.delay, args.jitter))  # the last run just finished a batch
        return run_batches(plan, lambda batch: delete_batch(page, batch, args), args, log, sleep)
    return run(args, collect, None, KINDS, sleep, browser, runner=runner)


if __name__ == "__main__":
    sys.exit(main())
