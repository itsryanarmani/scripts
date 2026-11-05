#!/usr/bin/env python3
"""Offline tests for soundcloud_cleanup.py: parsing, progress, pacing, CLI flow. No network."""
import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soundcloud_cleanup as m  # noqa: E402

REQUIRED = ["--user", "jane-doe"]
DELETER = "delete_one"
KIND = "track"


class SiteTest(unittest.TestCase):
    def test_normalize_user(self):
        for value in ("jane-doe", "Jane-Doe", "https://soundcloud.com/jane-doe/tracks"):
            with self.subTest(value=value):
                self.assertEqual(m.normalize_user(value), "jane-doe")
        for bad in ("", "a b", "tracks", "discover"):
            with self.subTest(bad=bad), self.assertRaises(m.UsageError):
                m.normalize_user(bad)

    def test_own_path(self):
        cases = [
            ("/jane-doe/first-song", ("track", "/jane-doe/first-song")),
            ("https://soundcloud.com/Jane-Doe/sets/mix-1?si=x", ("playlist", "/jane-doe/sets/mix-1")),
            ("/jane-doe/private-demo/s-AbC123", ("track", "/jane-doe/private-demo/s-AbC123")),
            ("/jane-doe/tracks", None),
            ("/jane-doe/likes", None),
            ("/jane-doe/sets", None),
            ("/bob/song", None),
            ("/jane-doe/song/comments", None),
            ("", None),
        ]
        for href, expected in cases:
            with self.subTest(href=href):
                self.assertEqual(m.own_path(href, "jane-doe"), expected)

    def test_items_from_skips_reposts_and_others(self):
        raw = [{"href": "/jane-doe/a", "repost": False, "text": "A"},
               {"href": "/jane-doe/b", "repost": True, "text": "reposted own"},
               {"href": "/bob/c", "repost": True, "text": "bob's"},
               {"href": "/jane-doe/sets/p", "repost": False, "text": "P"}]
        items = m.items_from(raw, "jane-doe")
        self.assertEqual([(i["kind"], i["id"], i["url"]) for i in items],
                         [("track", "/jane-doe/a", "https://soundcloud.com/jane-doe/a"),
                          ("playlist", "/jane-doe/sets/p", "https://soundcloud.com/jane-doe/sets/p")])

    def test_bad_user_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(["--user", "a b"], browser=None), 2)


class FakePage:
    url = "about:blank"


class FakeHandle:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def stop(self):
        self.closed = True


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def read(self, name):
        with open(self.path(name), encoding="utf-8") as f:
            return f.read()

    def write(self, name, text):
        with open(self.path(name), "w", encoding="utf-8") as f:
            f.write(text)
        return self.path(name)

    def args(self, *extra):
        return m.parse_args([*REQUIRED, "--progress", self.path("p.jsonl"), *extra])


class ProgressTest(Base):
    def test_resume_skips_deleted_and_gone_only(self):
        log = m.ProgressLog(self.path("p.jsonl"))
        self.assertEqual(log.done_ids(), set())
        log.add("1", "deleted")
        log.add("2", "failed", "boom")
        log.add("3", "gone")
        with open(self.path("p.jsonl"), "a") as f:
            f.write('{"id": "4", "status": "del')  # torn line from a crash
        self.assertEqual(log.done_ids(), {"1", "3"})
        self.assertEqual(json.loads(self.read("p.jsonl").splitlines()[1])["error"], "boom")

    def test_recent_deletes_carry_over(self):
        log = m.ProgressLog(self.path("p.jsonl"))
        now = datetime.now(timezone.utc)
        with open(self.path("p.jsonl"), "w") as f:
            for age, status in ((10, "deleted"), (50, "deleted"), (50, "failed"), (5000, "deleted")):
                ts = (now - timedelta(seconds=age)).isoformat()
                f.write(json.dumps({"ts": ts, "id": str(age), "status": status}) + "\n")
            f.write('{"id": "no-ts", "status": "deleted"}\n')
        self.assertEqual(log.recent_deletes(100, now), 2)
        self.assertEqual(log.recent_deletes(7200, now), 3)


class PacingTest(Base):
    def test_jitter_bounds(self):
        self.assertEqual(m.jittered(100, 0.3, rng=lambda: 0.5), 100)
        self.assertAlmostEqual(m.jittered(100, 0.3, rng=lambda: 0.0), 70)
        self.assertAlmostEqual(m.jittered(100, 0.3, rng=lambda: 1.0), 130)
        self.assertEqual(m.jittered(5, 0, rng=lambda: 0.9), 5)

    def test_batch_schedule(self):
        args = self.args("--batch-size", "3", "--delay", "100", "--item-delay", "2", "--jitter", "0")
        self.assertEqual([m.pause_before(i, args) for i in range(7)], [0, 2, 2, 100, 2, 2, 100])

    def test_run_deletions_paces_logs_and_continues(self):
        args = self.args("--batch-size", "2", "--delay", "100", "--item-delay", "1", "--jitter", "0")
        log, sleeps, calls = m.ProgressLog(args.progress), [], []

        def delete_one(item):
            calls.append(item["id"])
            if item["id"] == "b":
                raise RuntimeError("menu not found")
            return "gone" if item["id"] == "d" else "deleted"
        plan = [{"id": i, "kind": KIND} for i in "abcd"]
        with contextlib.redirect_stdout(io.StringIO()):
            ok, failed = m.run_deletions(plan, delete_one, args, log, sleeps.append)
            self.assertEqual((ok, failed, calls), (3, 1, ["a", "b", "c", "d"]))
            self.assertEqual(sleeps, [1, 100, 1])
            self.assertEqual(log.done_ids(), {"a", "c", "d"})
            sleeps.clear()
            m.run_deletions(plan[:2], lambda it: "deleted", args, log, sleeps.append, offset=1)
        self.assertEqual(sleeps, [1, 100])

    def test_stop_run_and_failure_streak_stop_early(self):
        args = self.args("--item-delay", "0", "--max-failures", "2")
        log, calls = m.ProgressLog(args.progress), []

        def stop(item):
            raise m.StopRun("blocked")

        def broken(item):
            calls.append(item["id"])
            raise RuntimeError("selector")
        plan = [{"id": str(i), "kind": KIND} for i in range(5)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(m.run_deletions(plan, stop, args, log, lambda s: None), (0, 1))
            m.run_deletions(plan, broken, args, log, lambda s: None)
        self.assertEqual(calls, ["0", "1"])
        self.assertIn('"stopped"', self.read("p.jsonl"))


class CoreTest(Base):
    def test_select_and_merge(self):
        items = [{"id": str(i), "kind": KIND} for i in range(5)] + [{"id": "x", "kind": "other"}]
        self.assertEqual([i["id"] for i in m.select(items, {"1"}, {KIND}, 0)], ["0", "2", "3", "4"])
        self.assertEqual([i["id"] for i in m.select(items, set(), {KIND}, 2)], ["0", "1"])
        found = {}
        self.assertEqual(m.merge_items(found, [{"id": "a"}, {"id": "b"}, {"id": ""}]), 2)
        self.assertEqual(m.merge_items(found, [{"id": "a", "text": "new"}, {"id": "c"}]), 1)
        self.assertEqual(list(found), ["a", "b", "c"])
        self.assertNotIn("text", found["a"])

    def test_load_cookies_formats(self):
        ext = self.write("ext.json", json.dumps([
            {"name": "s", "value": "v", "expirationDate": 1999999999.5,
             "sameSite": "no_restriction", "httpOnly": True}]))
        state = self.write("state.json", json.dumps({"cookies": [
            {"name": "t", "value": "w", "domain": "a.example", "expires": -1, "sameSite": "Lax"}]}))
        a, = m.load_cookies(ext)
        self.assertEqual((a["sameSite"], a["expires"], a["domain"]), ("None", 1999999999.5, m.COOKIE_DOMAIN))
        b, = m.load_cookies(state)
        self.assertEqual((b["sameSite"], b["domain"]), ("Lax", "a.example"))
        self.assertNotIn("expires", b)

    def test_usage_errors(self):
        for bad in (["--batch-size", "0"], ["--jitter", "1"], ["--delay", "-1"], ["--limit", "-2"]):
            with self.subTest(bad=bad), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(m.main([*REQUIRED, *bad], browser=None), 2)


class CliTest(Base):
    """main() end to end with the browser, listing and deleting faked."""

    def setUp(self):
        super().setUp()
        self.items = [{"id": f"id{i}", "kind": KIND, "url": f"https://example.test/{i}", "text": f"t{i}"}
                      for i in range(4)]
        self.deleted, self.handles = [], [FakeHandle(), FakeHandle()]
        patch(self, "collect", lambda page, args, done: list(self.items))
        patch(self, DELETER, self.fake_delete)

    def fake_delete(self, page, item, *rest):
        if isinstance(item, list):  # a batch deleter
            self.deleted.extend(it["id"] for it in item)
            return {it["id"]: "deleted" for it in item}
        self.deleted.append(item["id"])
        return "deleted"

    def browser(self, args):
        return self.handles[0], self.handles[1], FakePage()

    def run_main(self, *extra):
        argv = [*REQUIRED, "--progress", self.path("p.jsonl"), "--csv", self.path("o.csv"),
                "--item-delay", "0", *extra]
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code = m.main(argv, sleep=lambda s: None, browser=self.browser)
        self.out = out.getvalue()
        return code

    def test_dry_run_lists_and_deletes_nothing(self):
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.deleted, [])
        rows = list(csv.DictReader(io.StringIO(self.read("o.csv"))))
        self.assertEqual([r["id"] for r in rows], ["id0", "id1", "id2", "id3"])
        self.assertEqual(list(rows[0]), m.CSV_FIELDS)
        self.assertTrue(all(h.closed for h in self.handles))
        self.assertFalse(os.path.exists(self.path("p.jsonl")))

    def test_block_while_listing_stops_cleanly(self):
        def blocked(page, args, done):
            raise m.StopRun("redirected to a checkpoint")
        patch(self, "collect", blocked)
        self.assertEqual(self.run_main(), 1)
        self.assertTrue(all(h.closed for h in self.handles))

    def test_nothing_found_warns(self):
        self.items = []
        with contextlib.redirect_stderr(io.StringIO()) as err:
            argv = [*REQUIRED, "--progress", self.path("p.jsonl"), "--csv", self.path("o.csv")]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(m.main(argv, sleep=lambda s: None, browser=self.browser), 0)
        self.assertIn("nothing found", err.getvalue())

    def test_confirm_deletes_then_rerun_resumes(self):
        self.assertEqual(self.run_main("--confirm", "--limit", "3"), 0)
        self.assertEqual(self.deleted, ["id0", "id1", "id2"])
        self.assertEqual(self.run_main("--confirm"), 0)
        self.assertEqual(self.deleted, ["id0", "id1", "id2", "id3"])
        self.assertIn("count toward this batch", self.out)
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.read("o.csv").strip(), ",".join(m.CSV_FIELDS))


def patch(test, name, value):
    old = getattr(m, name)
    setattr(m, name, value)
    test.addCleanup(setattr, m, name, old)


if __name__ == "__main__":
    unittest.main()
