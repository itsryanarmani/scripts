#!/usr/bin/env python3
"""Delete your own SoundCloud tracks and playlists.

Lists the items on your Tracks and Playlists tabs (soundcloud.com/<you>/tracks
and /sets) in a browser you are logged in to, driven by Playwright, then
deletes each one from its own page. Dry run is the default and only writes a
CSV of what would be deleted; pass --confirm to delete.
Unofficial; not affiliated with SoundCloud.
"""
import argparse
import csv
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

TOOL = "soundcloud-cleanup"
BASE = "https://soundcloud.com"
HOME_URL = BASE + "/discover"
COOKIE_DOMAIN = ".soundcloud.com"
KINDS = {"tracks": {"track"}, "playlists": {"playlist"}, "both": {"track", "playlist"}}
RESERVED = {"tracks", "sets", "albums", "reposts", "likes", "followers", "following",
            "popular-tracks", "comments", "you", "discover", "stream", "upload"}

# SoundCloud changes its markup often, so these selectors WILL break at some
# point. They are all here so a fix is one edit. Check them in your browser's
# inspector if listing or deleting starts failing.
SELECTORS = {
    "logged_in": ".header__userNavUsernameButton, .header__userNavButton",
    "item": ".soundList__item",
    "title_link": "a.soundTitle__title",
    "repost": ".soundContext__repost",
    "hero": ".l-listen-hero, .fullHero",
    "more": '.l-listen-engagement button.sc-button-more, .listenEngagement button[aria-label="More"]',
    "menu_item": ".moreActions button, .dropdownMenu button, [role='menuitem']",
    "confirm": ".modal button, [role='dialog'] button",
}
MISSING_TEXT = re.compile(r"we can.t find that|this (track|playlist) (was|has been) (deleted|removed)", re.I)
BLOCK_URL = re.compile(r"/signin|/login|secure\.soundcloud\.com", re.I)

LIST_JS = """([sel]) => [...document.querySelectorAll(sel.item)].map(it => {
  const a = it.querySelector(sel.title_link);
  return {href: a ? a.getAttribute('href') || '' : '', repost: !!it.querySelector(sel.repost),
          text: (a ? a.innerText : '').trim().slice(0, 300)};
})"""


# ----------------------------------------------------------- site logic

def normalize_user(value):
    value = (value or "").strip()
    m = re.search(r"soundcloud\.com/([^/?#]+)", value)
    name = (m.group(1) if m else value).strip("/").lower()
    if not re.fullmatch(r"[a-z0-9_-]{2,60}", name) or name in RESERVED:
        raise UsageError(f"not a SoundCloud profile name: {value!r}")
    return name


def own_path(href, user):
    """(kind, path) when href is one of `user`'s tracks or playlists, else None."""
    m = re.match(r"(?:https?://(?:www\.)?soundcloud\.com)?/([^/?#]+)/(sets/)?([^/?#]+)"
                 r"(/s-[A-Za-z0-9]+)?/?(?:[?#]|$)", href or "")
    if not m or m.group(1).lower() != user or (not m.group(2) and m.group(3) in RESERVED):
        return None
    kind = "playlist" if m.group(2) else "track"
    # A private item's link carries its secret token (/s-...); keep it so the page opens.
    return kind, f"/{m.group(1).lower()}/{m.group(2) or ''}{m.group(3)}{m.group(4) or ''}"


def items_from(raw, user):
    out = []
    for r in raw:
        hit = own_path(r.get("href"), user)
        if hit and not r.get("repost"):
            out.append({"id": hit[1], "kind": hit[0], "text": r.get("text", ""), "url": BASE + hit[1]})
    return out


def check_page(page):
    if BLOCK_URL.search(page.url):
        raise StopRun(f"SoundCloud redirected to {page.url}; check the account in the browser")


def collect(page, args, done):
    items, kinds = [], KINDS[args.what]
    for tab, kind in (("tracks", "track"), ("sets", "playlist")):
        if kind in kinds:
            page.goto(f"{BASE}/{args.user}/{tab}")
            page.wait_for_timeout(3000)
            check_page(page)
            items += scroll_collect(page, lambda: items_from(page.evaluate(LIST_JS, [SELECTORS]),
                                                             args.user), args, done, kinds)
    return items


def delete_one(page, item):
    page.goto(item["url"])
    page.wait_for_timeout(3000)
    check_page(page)
    if not page.locator(SELECTORS["hero"]).count():
        if MISSING_TEXT.search(page.inner_text("body")):
            return "gone"
        raise RuntimeError(f"{item['kind']} page did not load")
    page.locator(SELECTORS["more"]).first.click(timeout=5000)
    click_menu_item(page, re.compile(rf"^\s*Delete {item['kind']}\s*$", re.I))
    confirm = page.locator(SELECTORS["confirm"]).filter(has_text=re.compile(r"delete", re.I)).last
    confirm.click(timeout=5000)
    page.wait_for_timeout(2500)
    if confirm.is_visible():
        raise RuntimeError("the delete dialog is still open; not marking it deleted")
    return "deleted"


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


def find_on_page(page, selector, scrolls=8):
    """First element matching selector, scrolling to load more; None if it never shows."""
    for _ in range(scrolls):
        loc = page.locator(selector)
        if loc.count():
            return loc.first
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1000)
    return None


def click_menu_item(page, pattern, timeout=5000):
    page.locator(SELECTORS["menu_item"]).filter(has_text=pattern).first.click(timeout=timeout)


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


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Delete your own SoundCloud tracks and playlists. Dry run by default.",
        epilog="Exit codes: 0 ok, 1 some deletes failed or the run stopped, 2 usage error.")
    ap.add_argument("--user", required=True, help="your profile name, as in soundcloud.com/<name> (or the URL)")
    ap.add_argument("--what", choices=sorted(KINDS), default="both",
                    help="tracks, playlists or both (default: both; reposts are never touched)")
    add_common_args(ap, batch_size=10, delay=300, item_delay=5)
    args = ap.parse_args(argv)
    check_common_args(ap, args)
    return args


def main(argv=None, sleep=time.sleep, browser=open_browser):
    try:
        args = parse_args(argv)
        args.user = normalize_user(args.user)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    return run(args, collect, lambda page, it: delete_one(page, it), KINDS[args.what], sleep, browser)


if __name__ == "__main__":
    sys.exit(main())
