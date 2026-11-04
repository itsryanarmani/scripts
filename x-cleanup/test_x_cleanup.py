#!/usr/bin/env python3
"""Offline tests for x_cleanup.py: parsing, selection, progress, pacing. No network."""
import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_cleanup as xc  # noqa: E402

ARCHIVE = "window.YTD.tweets.part0 = " + json.dumps([
    {"tweet": {"id_str": "100", "full_text": "hello world",
               "created_at": "Wed Oct 10 20:19:24 +0000 2018"}},
    {"tweet": {"id_str": "200", "full_text": "@bob agreed", "in_reply_to_status_id_str": "5",
               "created_at": "Mon Jan 02 10:00:00 +0000 2023"}},
    {"tweet": {"id_str": "300", "full_text": "RT @alice: something",
               "created_at": "Tue Mar 05 08:00:00 +0000 2024"}},
    {"tweet": {"id": "400", "text": "old api shape", "created_at": "Fri Jun 07 12:00:00 +0000 2024"}},
    {"tweet": {"id_str": "not-a-number"}},
])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def write(self, name, text):
        with open(self.path(name), "w", encoding="utf-8") as f:
            f.write(text)
        return self.path(name)

    def read(self, name):
        with open(self.path(name), encoding="utf-8") as f:
            return f.read()

    def args(self, *extra):
        return xc.parse_args(["--ids-csv", "x.csv", "--progress", self.path("p.jsonl"), *extra])


class ParsingTest(Base):
    def test_archive_kinds_dates_and_bad_ids(self):
        items = {it["id"]: it for it in xc.parse_archive_text(ARCHIVE)}
        self.assertEqual(sorted(items), ["100", "200", "300", "400"])
        self.assertEqual([items[i]["kind"] for i in ("100", "200", "300", "400")],
                         ["post", "reply", "retweet", "post"])
        self.assertEqual(items["100"]["created_at"], "2018-10-10T20:19:24+00:00")
        self.assertEqual(items["400"]["text"], "old api shape")

    def test_archive_without_prefix_and_invalid_json(self):
        self.assertEqual(len(xc.parse_archive_text('[{"id_str": "7", "full_text": "x"}]')), 1)
        for bad in ("window.YTD.tweets.part0 = [oops", "window.YTD.tweets", '{"a": 1}'):
            with self.subTest(bad=bad), self.assertRaises(xc.UsageError):
                xc.parse_archive_text(bad)

    def test_archive_folder_finds_all_parts(self):
        os.makedirs(self.path("arc/data"))
        self.write("arc/data/tweets.js", ARCHIVE)
        self.write("arc/data/tweets-part1.js", 'window.YTD.tweets.part1 = [{"tweet": {"id_str": "900"}}]')
        self.write("arc/data/like.js", "window.YTD.like.part0 = []")
        files = [os.path.basename(f) for f in xc.archive_files(self.path("arc"))]
        self.assertEqual(files, ["tweets-part1.js", "tweets.js"])
        with self.assertRaises(xc.UsageError):
            xc.archive_files(self.path("missing.js"))

    def test_id_csv_shapes(self):
        cases = [
            ("tweet_id,text\n111,hi\n222,yo\n", ["111", "222"]),
            ("text,url\nhi,https://x.com/me/status/333?s=20\n", ["333"]),
            ("444\n555\n\n", ["444", "555"]),
            ("id\nnope\n666\n", ["666"]),
            ("https://twitter.com/me/statuses/777\n", ["777"]),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual([it["id"] for it in xc.parse_id_csv_text(text)], expected)

    def test_load_items_dedupes_and_builds_urls(self):
        arc = self.write("tweets.js", ARCHIVE)
        ids = self.write("ids.csv", "id\n100\n999\n")
        args = xc.parse_args(["--archive", arc, "--ids-csv", ids])
        items = xc.load_items(args)
        self.assertEqual([it["id"] for it in items], ["100", "200", "300", "400", "999"])
        self.assertEqual(items[-1]["url"], "https://x.com/i/status/999")


class SelectTest(Base):
    def setUp(self):
        super().setUp()
        self.items = xc.parse_archive_text(ARCHIVE)

    def ids(self, *extra, done=()):
        return [it["id"] for it in xc.select(self.items, self.args(*extra), set(done))]

    def test_filters(self):
        self.assertEqual(self.ids(), ["400", "200", "100"])  # newest first, no retweets
        self.assertEqual(self.ids("--kind", "replies"), ["200"])
        self.assertEqual(self.ids("--kind", "posts"), ["400", "100"])
        self.assertEqual(self.ids("--before", "2023-01-02"), ["100"])
        self.assertEqual(self.ids("--after", "2023-01-02"), ["400", "200"])
        self.assertEqual(self.ids("--limit", "1"), ["400"])
        self.assertEqual(self.ids(done={"400"}), ["200", "100"])

    def test_date_filter_drops_undated_csv_ids(self):
        self.items.append({"id": "5", "kind": "unknown", "text": "", "created_at": ""})
        self.assertIn("5", self.ids())
        self.assertNotIn("5", self.ids("--after", "2000-01-01"))


class ProgressTest(Base):
    def test_resume_skips_deleted_and_gone_only(self):
        log = xc.ProgressLog(self.path("p.jsonl"))
        self.assertEqual(log.done_ids(), set())
        log.add("1", "deleted")
        log.add("2", "failed", "boom")
        log.add("3", "gone")
        with open(self.path("p.jsonl"), "a") as f:
            f.write('{"id": "4", "status": "del')  # torn line from a crash
        self.assertEqual(log.done_ids(), {"1", "3"})
        rows = [json.loads(line) for line in self.read("p.jsonl").splitlines()[:3]]
        self.assertEqual(rows[1]["error"], "boom")


    def test_recent_deletes_carry_over(self):
        log = xc.ProgressLog(self.path("p.jsonl"))
        now = xc.datetime.now(xc.timezone.utc)
        with open(self.path("p.jsonl"), "w") as f:
            for age, status in ((10, "deleted"), (50, "deleted"), (50, "failed"), (5000, "deleted")):
                ts = (now - timedelta(seconds=age)).isoformat()
                f.write(json.dumps({"ts": ts, "id": str(age), "status": status}) + "\n")
            f.write('{"id": "no-ts", "status": "deleted"}\n')
        self.assertEqual(log.recent_deletes(100, now), 2)
        self.assertEqual(log.recent_deletes(7200, now), 3)


class PacingTest(Base):
    def test_jitter_bounds(self):
        self.assertEqual(xc.jittered(100, 0.3, rng=lambda: 0.5), 100)
        self.assertAlmostEqual(xc.jittered(100, 0.3, rng=lambda: 0.0), 70)
        self.assertAlmostEqual(xc.jittered(100, 0.3, rng=lambda: 1.0), 130)

    def test_default_schedule_is_15_then_two_hours(self):
        args = self.args("--jitter", "0")
        waits = [xc.pause_before(i, args) for i in range(31)]
        self.assertEqual(waits[0], 0)
        self.assertEqual(waits[15], 7200)
        self.assertEqual(waits[30], 7200)
        self.assertEqual(set(waits[1:15]), {20})

    def test_run_deletions_paces_logs_and_continues(self):
        args = self.args("--batch-size", "2", "--delay", "100", "--item-delay", "1", "--jitter", "0")
        log, sleeps, calls = xc.ProgressLog(args.progress), [], []

        def delete_one(item):
            calls.append(item["id"])
            if item["id"] == "b":
                raise RuntimeError("menu not found")
            return "gone" if item["id"] == "d" else "deleted"
        plan = [{"id": i} for i in "abcd"]
        with contextlib.redirect_stdout(io.StringIO()):
            ok, failed = xc.run_deletions(plan, delete_one, args, log, sleeps.append)
        self.assertEqual((ok, failed, calls), (3, 1, ["a", "b", "c", "d"]))
        self.assertEqual(sleeps, [1, 100, 1])
        self.assertEqual(log.done_ids(), {"a", "c", "d"})

    def test_offset_continues_the_previous_batch(self):
        args = self.args("--batch-size", "3", "--delay", "100", "--item-delay", "1", "--jitter", "0")
        sleeps = []
        with contextlib.redirect_stdout(io.StringIO()):
            xc.run_deletions([{"id": i} for i in "abc"], lambda it: "deleted", args,
                             xc.ProgressLog(args.progress), sleeps.append, offset=2)
        self.assertEqual(sleeps, [1, 100, 1])

    def test_stop_run_and_failure_streak_stop_early(self):
        args = self.args("--item-delay", "0", "--max-failures", "2")
        log = xc.ProgressLog(args.progress)

        def stop(item):
            raise xc.StopRun("HTTP 429")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(xc.run_deletions([{"id": "1"}, {"id": "2"}], stop, args, log, lambda s: None), (0, 1))
            calls = []

            def broken(item):
                calls.append(item["id"])
                raise RuntimeError("selector")
            xc.run_deletions([{"id": str(i)} for i in range(5)], broken, args, log, lambda s: None)
        self.assertEqual(calls, ["0", "1"])


class CliTest(Base):
    def run_main(self, *argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = xc.main(list(argv), env=env or {}, sleep=lambda s: None)
        self.out, self.err = out.getvalue(), err.getvalue()
        return code

    def test_dry_run_writes_csv_and_touches_nothing(self):
        arc = self.write("tweets.js", ARCHIVE)
        xc.ProgressLog(self.path("p.jsonl")).add("100", "deleted")
        code = self.run_main("--archive", arc, "--progress", self.path("p.jsonl"), "--csv", self.path("o.csv"))
        self.assertEqual(code, 0)
        rows = list(csv.DictReader(io.StringIO(self.read("o.csv"))))
        self.assertEqual([r["id"] for r in rows], ["400", "200"])
        self.assertEqual(list(rows[0]), xc.CSV_FIELDS)
        self.assertIn("1 retweet(s) ignored", self.out)
        self.assertIn("Dry run", self.out)

    def test_api_mode_needs_token(self):
        ids = self.write("ids.csv", "1\n")
        self.assertEqual(self.run_main("--ids-csv", ids, "--confirm", "--api",
                                       "--progress", self.path("p.jsonl")), 2)
        self.assertIn(xc.TOKEN_ENV, self.err)

    def test_usage_errors(self):
        self.assertEqual(self.run_main(), 2)
        self.assertEqual(self.run_main("--ids-csv", "a", "--batch-size", "0"), 2)
        self.assertEqual(self.run_main("--ids-csv", "a", "--jitter", "1.5"), 2)
        self.assertEqual(self.run_main("--ids-csv", "a", "--api", "--cookies", "c.json"), 2)
        self.assertEqual(self.run_main("--ids-csv", self.path("nope.csv")), 2)

    def test_load_cookies_formats(self):
        ext = self.write("ext.json", json.dumps([
            {"name": "auth_token", "value": "v", "domain": ".x.com", "expirationDate": 1999999999.5,
             "sameSite": "no_restriction", "httpOnly": True}]))
        state = self.write("state.json", json.dumps({"cookies": [{"name": "ct0", "value": "w",
                                                                  "domain": ".x.com", "path": "/",
                                                                  "expires": -1, "sameSite": "Lax"}]}))
        a, = xc.load_cookies(ext)
        self.assertEqual((a["sameSite"], a["expires"], a["httpOnly"]), ("None", 1999999999.5, True))
        b, = xc.load_cookies(state)
        self.assertEqual(b["sameSite"], "Lax")
        self.assertNotIn("expires", b)


if __name__ == "__main__":
    unittest.main()
