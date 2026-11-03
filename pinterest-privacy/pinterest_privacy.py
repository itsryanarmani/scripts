#!/usr/bin/env python3
"""Make all your Pinterest boards private (secret), or optionally delete them.

API mode (default) uses the official Pinterest API v5 with a token from
PINTEREST_ACCESS_TOKEN. Browser mode (--browser) drives Pinterest's normal web
UI with Playwright after you log in yourself. Dry run is the default; pass
--apply to change anything. Unofficial; not affiliated with Pinterest.
"""
import argparse
import fnmatch
import json
import os
import random
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DEFAULT_API_BASE = "https://api.pinterest.com/v5"
EXIT_OK, EXIT_PARTIAL, EXIT_USAGE = 0, 1, 2
DELETE_WARNING = (
    "WARNING: deleting a board also deletes its Pins. Pinterest only lets you "
    "restore deleted boards for about 7 days, and --undo cannot restore deletions."
)


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class AuthError(ApiError):
    pass


class PinterestClient:
    """Minimal Pinterest API v5 client with retry on 429/5xx."""

    def __init__(self, token, base=DEFAULT_API_BASE, max_retries=5, sleep=time.sleep):
        self.token = token
        self.base = base.rstrip("/")
        self.max_retries = max_retries
        self.sleep = sleep

    def _backoff(self, attempt, retry_after):
        try:
            return max(0.0, float(retry_after))
        except (TypeError, ValueError):
            return min(60.0, 2.0 ** attempt) + random.uniform(0, 1)

    def request(self, method, path, params=None, body=None):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                if e.code in (401, 403):
                    raise AuthError(e.code, detail)
                if (e.code == 429 or e.code >= 500) and attempt < self.max_retries:
                    wait = self._backoff(attempt, e.headers.get("Retry-After"))
                    print(f"  HTTP {e.code}, retrying in {wait:.1f}s ({attempt + 1}/{self.max_retries})")
                    self.sleep(wait)
                    continue
                raise ApiError(e.code, detail)
            except urllib.error.URLError as e:
                if attempt < self.max_retries:
                    self.sleep(self._backoff(attempt, None))
                    continue
                raise ApiError(0, str(e.reason))

    def list_boards(self):
        boards, bookmark = [], None
        while True:
            params = {"page_size": 250}
            if bookmark:
                params["bookmark"] = bookmark
            page = self.request("GET", "/boards", params=params)
            boards.extend(page.get("items", []))
            bookmark = page.get("bookmark")
            if not bookmark:
                return boards

    def set_privacy(self, board_id, privacy):
        path = "/boards/" + urllib.parse.quote(str(board_id), safe="")
        return self.request("PATCH", path, body={"privacy": privacy})

    def delete_board(self, board_id):
        return self.request("DELETE", "/boards/" + urllib.parse.quote(str(board_id), safe=""))


class ChangeLog:
    """JSON list of change entries, rewritten atomically after every entry."""

    def __init__(self, path):
        self.path = path
        self.entries = []

    def add(self, action, item, status, error=None, mode="api"):
        self.entries.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "board_id": item["id"],
            "board_name": item["name"],
            "previous_privacy": item["previous"],
            "new_privacy": item["new"],
            "status": status,
            "error": error,
            "mode": mode,
        })
        folder = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".pinterest-privacy-", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(self.entries, f, indent=2)
        os.replace(tmp, self.path)


def matches(board, patterns):
    name = str(board.get("name", "")).lower()
    for pattern in patterns:
        p = pattern.lower()
        if pattern == str(board.get("id")) or p in name or fnmatch.fnmatchcase(name, p):
            return True
    return False


def select(boards, include, exclude):
    return [b for b in boards
            if (not include or matches(b, include)) and not (exclude and matches(b, exclude))]


def print_plan(plan):
    print(f"{'ID':<22} {'PRIVACY':<10} {'ACTION':<18} NAME")
    for item in plan:
        name = item["name"] if len(item["name"]) <= 40 else item["name"][:37] + "..."
        print(f"{item['id']:<22} {str(item['previous']):<10} {item['label']:<18} {name}")
    todo = sum(1 for i in plan if i["action"] != "skip")
    print(f"\n{len(plan)} board(s) matched, {todo} to change.")


def execute(plan, args, perform, mode="api"):
    """Run perform(item) for each actionable item; returns the failure count."""
    todo = [i for i in plan if i["action"] != "skip"]
    log = ChangeLog(args.log)
    failures = 0
    for n, item in enumerate(todo):
        if n and args.delay:
            time.sleep(args.delay)
        try:
            changed = perform(item)
        except AuthError as e:
            log.add(item["action"], item, "failed", str(e), mode)
            raise
        except Exception as e:  # keep going; record the failure
            failures += 1
            log.add(item["action"], item, "failed", str(e), mode)
            print(f"  [FAILED] {item['name']}: {e}")
            continue
        if changed is False:
            print(f"  [skip]   {item['name']}: already secret")
            continue
        log.add(item["action"], item, "ok", None, mode)
        print(f"  [ok]     {item['name']}: {item['label']}")
    if log.entries:
        print(f"\nLog written to {log.path}")
    print(f"Done: {len(todo) - failures} ok, {failures} failed.")
    return failures


def build_plan(boards, args):
    plan = []
    for b in select(boards, args.include, args.exclude):
        item = {"id": str(b["id"]), "name": b.get("name", ""), "previous": b.get("privacy")}
        if args.delete:
            item.update(action="delete", new=None, label="DELETE")
        elif b.get("privacy") == "PUBLIC":
            item.update(action="set_privacy", new="SECRET", label="make SECRET")
        else:
            item.update(action="skip", new=b.get("privacy"), label="skip")
        plan.append(item)
    return plan


def build_undo_plan(path, args):
    with open(path) as f:
        entries = json.load(f)
    plan, seen = [], set()
    for e in entries:
        if e.get("status") != "ok" or e["board_id"] in seen:
            continue
        if e.get("action") == "delete":
            print(f"  note: {e['board_name']} was deleted; --undo cannot restore it "
                  "(use Pinterest's restore option within ~7 days).")
            continue
        if e.get("mode") == "browser":
            print(f"  note: {e['board_name']} was changed in browser mode; undo it manually.")
            continue
        seen.add(e["board_id"])
        target = e.get("previous_privacy") or "PUBLIC"
        plan.append({"id": e["board_id"], "name": e["board_name"], "previous": e.get("new_privacy"),
                     "new": target, "action": "set_privacy", "label": f"restore {target}"})
    return select(plan, args.include, args.exclude)


def confirm_delete(count, args):
    if args.yes_i_understand_delete:
        return True
    expected = f"DELETE {count} BOARDS"
    try:
        typed = input(f"Type '{expected}' to confirm: ")
    except EOFError:
        typed = ""
    return typed.strip() == expected


def run_api(args):
    token = os.environ.get("PINTEREST_ACCESS_TOKEN", "").strip()
    if not token:
        print("error: set PINTEREST_ACCESS_TOKEN (scopes: boards:read, boards:write).", file=sys.stderr)
        return EXIT_USAGE
    base = args.api_base or os.environ.get("PINTEREST_API_BASE") or DEFAULT_API_BASE
    client = PinterestClient(token, base, max_retries=args.max_retries)
    if args.undo:
        plan = build_undo_plan(args.undo, args)
    else:
        plan = build_plan(client.list_boards(), args)
    print_plan(plan)
    if args.delete:
        print("\n" + DELETE_WARNING)
    if not args.apply:
        print("\nDry run: nothing changed. Re-run with --apply to make these changes.")
        return EXIT_OK
    todo = sum(1 for i in plan if i["action"] != "skip")
    if not todo:
        return EXIT_OK
    if args.delete and not confirm_delete(todo, args):
        print("Aborted: confirmation did not match. Nothing was deleted.")
        return EXIT_USAGE

    def perform(item):
        if item["action"] == "delete":
            client.delete_board(item["id"])
        else:
            client.set_privacy(item["id"], item["new"])
        return True

    return EXIT_PARTIAL if execute(plan, args, perform) else EXIT_OK


# ---------------------------------------------------------------- browser mode

RESERVED_PATHS = {"boards", "pins", "_saved", "_created", "followers", "following", "_profile"}


def run_browser(args):
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as PWTimeout
    except ImportError:
        print("error: browser mode needs Playwright:\n"
              "  pip install playwright && playwright install chromium", file=sys.stderr)
        return EXIT_USAGE

    def find(page, what, factories, state="visible", timeout=5000):
        for factory in factories:
            loc = factory().first
            try:
                loc.wait_for(state=state, timeout=timeout)
                return loc
            except PWTimeout:
                continue
        raise RuntimeError(f"could not find {what}")

    def detect_username(page):
        for sel in ('[data-test-id="header-profile"] a', 'a[aria-label*="profile" i]',
                    'div[data-test-id="header-profile"] a[href]'):
            try:
                href = page.locator(sel).first.get_attribute("href", timeout=3000) or ""
            except PWTimeout:
                continue
            parts = [p for p in href.split("/") if p]
            if parts and "." not in parts[-1]:
                return parts[0]
        return None

    def collect_boards(page, username):
        page.goto(f"https://www.pinterest.com/{username}/boards/")
        page.wait_for_timeout(3000)
        found, stable = {}, 0
        while stable < 3:
            links = page.eval_on_selector_all(
                f'a[href^="/{username}/"]',
                "els => els.map(e => [e.getAttribute('href'), e.getAttribute('aria-label') || e.innerText])")
            before = len(found)
            for href, label in links:
                parts = [p for p in href.split("?")[0].split("/") if p]
                if len(parts) == 2 and parts[1] not in RESERVED_PATHS:
                    name = (label or "").strip().split("\n")[0] or parts[1]
                    found.setdefault(f"/{parts[0]}/{parts[1]}/", name)
            stable = stable + 1 if len(found) == before else 0
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1200)
        return [{"id": path, "name": name, "privacy": "unknown"} for path, name in found.items()]

    def make_secret(page, path):
        page.goto("https://www.pinterest.com" + path)
        page.wait_for_timeout(1500)
        find(page, "board options button", [
            lambda: page.get_by_role("button", name=re.compile(r"(more|board) (board )?(options|actions)", re.I)),
            lambda: page.locator('[data-test-id="board-header-details"] button, [data-test-id*="more" i] button'),
            lambda: page.locator('button[aria-label*="options" i], div[role="button"][aria-label*="options" i]'),
        ]).click()
        find(page, "Edit board", [
            lambda: page.get_by_role("menuitem", name=re.compile(r"edit board", re.I)),
            lambda: page.get_by_role("button", name=re.compile(r"edit board", re.I)),
            lambda: page.get_by_text(re.compile(r"^\s*edit board\s*$", re.I)),
        ]).click()
        secret_re = re.compile(r"keep this board secret|make this board (private|secret)|secret", re.I)
        box = find(page, "secret checkbox", [
            lambda: page.get_by_role("checkbox", name=secret_re),
            lambda: page.get_by_label(secret_re),
            lambda: page.locator('input[type="checkbox"][id*="secret" i], input[type="checkbox"][name*="secret" i]'),
        ], state="attached")
        if box.is_checked():
            page.keyboard.press("Escape")
            return False
        box.check(force=True)
        find(page, "Save/Done button", [
            lambda: page.get_by_role("button", name=re.compile(r"^\s*(save|done)\s*$", re.I)),
            lambda: page.get_by_text(re.compile(r"^\s*(save|done)\s*$", re.I)),
        ]).click()
        page.wait_for_timeout(1500)
        return True

    profile = os.path.expanduser(args.profile_dir)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.pinterest.com/")
        input("Log in to Pinterest in the browser window, then press Enter here... ")
        username = args.username or detect_username(page)
        if not username:
            print("error: could not detect your username; pass --username.", file=sys.stderr)
            ctx.close()
            return EXIT_USAGE
        plan = []
        for b in select(collect_boards(page, username), args.include, args.exclude):
            plan.append({"id": b["id"], "name": b["name"], "previous": "unknown",
                         "new": "SECRET", "action": "set_privacy", "label": "ensure SECRET"})
        print_plan(plan)
        if not args.apply:
            print("\nDry run: nothing changed. Re-run with --apply to make these changes.")
            ctx.close()
            return EXIT_OK

        def perform(item):
            try:
                changed = make_secret(page, item["id"])
            except Exception:
                os.makedirs(args.screenshot_dir, exist_ok=True)
                slug = re.sub(r"[^A-Za-z0-9_-]+", "_", item["id"]).strip("_")
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                try:
                    page.screenshot(path=os.path.join(args.screenshot_dir, f"{slug}-{stamp}.png"))
                except Exception:
                    pass
                raise
            if changed:
                item["previous"] = "PUBLIC"
            return changed

        failures = execute(plan, args, perform, mode="browser")
        ctx.close()
    return EXIT_PARTIAL if failures else EXIT_OK


def parse_args(argv=None):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ap = argparse.ArgumentParser(
        description="Make your Pinterest boards secret (or delete them). Dry run by default.",
        epilog="Exit codes: 0 ok, 1 some changes failed, 2 usage/auth error or aborted.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="apply", action="store_false",
                      help="show the plan and change nothing (default)")
    mode.add_argument("--apply", dest="apply", action="store_true", help="actually make the changes")
    ap.set_defaults(apply=False)
    ap.add_argument("--include", action="append", default=[], metavar="PATTERN",
                    help="only boards whose name contains/globs PATTERN or whose id equals it (repeatable)")
    ap.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                    help="skip boards matching PATTERN (repeatable)")
    ap.add_argument("--delete", action="store_true",
                    help="DELETE matched boards instead of making them secret (API mode only)")
    ap.add_argument("--yes-i-understand-delete", action="store_true",
                    help="skip the typed delete confirmation (non-interactive use)")
    ap.add_argument("--undo", metavar="LOGFILE", help="restore privacy changes recorded in LOGFILE")
    ap.add_argument("--log", default=f"pinterest-privacy-log-{stamp}.json",
                    help="JSON log file for changes (default: %(default)s)")
    ap.add_argument("--max-retries", type=int, default=5, help="retries on 429/5xx (default: 5)")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between writes (default: 0.5)")
    ap.add_argument("--api-base", help=f"API base URL (env PINTEREST_API_BASE, default {DEFAULT_API_BASE})")
    ap.add_argument("--browser", action="store_true", help="use Pinterest's web UI via Playwright")
    ap.add_argument("--profile-dir", default="~/.pinterest-privacy-profile",
                    help="browser profile directory (default: %(default)s)")
    ap.add_argument("--username", help="your Pinterest username (browser mode)")
    ap.add_argument("--screenshot-dir", default="pinterest-privacy-screenshots",
                    help="where browser mode saves failure screenshots (default: %(default)s)")
    args = ap.parse_args(argv)
    if args.delete and args.undo:
        ap.error("--delete and --undo cannot be combined")
    if args.browser and args.delete:
        ap.error("delete is API-only; in the browser, delete boards manually")
    if args.browser and args.undo:
        ap.error("--undo is API-only")
    return args


def main(argv=None):
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    try:
        return run_browser(args) if args.browser else run_api(args)
    except AuthError as e:
        print(f"error: Pinterest rejected the token ({e}).\n"
              "Check that PINTEREST_ACCESS_TOKEN is valid, not expired, and has the "
              "boards:read and boards:write scopes.", file=sys.stderr)
        return EXIT_USAGE
    except (ApiError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("\nInterrupted. Changes made so far are in the log.", file=sys.stderr)
        return EXIT_PARTIAL


if __name__ == "__main__":
    sys.exit(main())
