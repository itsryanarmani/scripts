#!/usr/bin/env python3
"""Tests for reddit_cleanup.py with fake Reddit objects (no PRAW, no network)."""
import contextlib
import csv
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reddit_cleanup as rc  # noqa: E402

ENV = {"REDDIT_CLIENT_ID": "cid", "REDDIT_CLIENT_SECRET": "s3cret-value",
       "REDDIT_USERNAME": "me", "REDDIT_PASSWORD": "hunter2"}


class FakeTooManyRequests(Exception):
    def __init__(self, retry_after=None):
        super().__init__("429 Too Many Requests")
        self.retry_after = retry_after


class FakeThing:
    def __init__(self, reddit, fullname, sub="python", date="2024-06-01", score=1,
                 text="hello world", is_self=True, author="me"):
        self.reddit, self.fullname, self.id = reddit, fullname, fullname[3:]
        self.subreddit, self.score, self.author = sub, score, author
        self.created_utc = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        self.permalink = f"/r/{sub}/comments/{self.id}/"
        if fullname.startswith("t1_"):
            self.body = text
        else:
            self.title, self.is_self = f"Title {self.id}", is_self
            self.selftext = text if is_self else ""
            self.url = self.permalink if is_self else "https://example.com/link"

    def _write(self, call):
        if self.reddit.fail.get(self.fullname):
            self.reddit.fail[self.fullname] -= 1
            raise FakeTooManyRequests(retry_after=0)
        self.reddit.on_write(self)
        self.reddit.calls.append(call)

    def edit(self, text):
        self._write(("edit", self.fullname, text))

    def delete(self):
        self._write(("delete", self.fullname))


class FakeListing:
    def __init__(self, things):
        self.things = things

    def new(self, limit=None):
        return iter(self.things)


class FakeReddit:
    def __init__(self):
        self.calls, self.fail, self.info_calls = [], {}, []
        self.on_write = lambda thing: None
        self.user = type("U", (), {"me": lambda _self: "me"})()
        self.comments = [
            FakeThing(self, "t1_c1", "python", "2024-06-01", 10, "nice post"),
            FakeThing(self, "t1_c2", "AskReddit", "2023-01-15", -3, "bad take"),
            FakeThing(self, "t1_c3", "news", "2022-05-05", 50, "old comment"),
        ]
        self.posts = [
            FakeThing(self, "t3_p1", "python", "2024-02-02", 5, "self text"),
            FakeThing(self, "t3_p2", "pics", "2024-03-03", 99, is_self=False),
        ]
        # Only reachable through reddit.info (older than the listing window).
        self.archive = [FakeThing(self, "t1_old1", "python", "2015-01-01", 2, "ancient"),
                        FakeThing(self, "t1_gone", "python", "2015-01-02", 1, "[deleted]", author=None)]

    def redditor(self, name):
        return type("R", (), {"comments": FakeListing(self.comments),
                              "submissions": FakeListing(self.posts)})()

    def info(self, fullnames):
        self.info_calls.append(list(fullnames))
        by_name = {t.fullname: t for t in self.comments + self.posts + self.archive}
        return [by_name[n] for n in fullnames if n in by_name]


class RedditCleanupTest(unittest.TestCase):
    def setUp(self):
        rc.RETRY_EXCEPTIONS = (FakeTooManyRequests,)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reddit = FakeReddit()
        self.sleeps = []

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def run_main(self, *argv, env=ENV, typed="", connect=None):
        argv = list(argv) + ["--log", self.path("log.csv")]
        if "--apply" in argv and "--backup" not in argv:
            argv += ["--backup", self.path("backup.csv")]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rc.main(argv, env=env, connect=connect or (lambda creds: self.reddit),
                           sleep=self.sleeps.append, input_fn=lambda prompt: typed)
        self.out, self.err = out.getvalue(), err.getvalue()
        return code

    def deleted(self):
        return [c[1] for c in self.reddit.calls if c[0] == "delete"]

    def read_csv(self, name):
        with open(self.path(name), newline="") as f:
            return list(csv.DictReader(f))

    def test_dry_run_default_changes_nothing(self):
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.reddit.calls, [])
        self.assertIn("3 of 3 item(s) selected: 3 comment(s), 0 post(s)", self.out)
        self.assertIn("t1_c2", self.out)
        self.assertIn("AskReddit", self.out)
        self.assertNotIn("s3cret", self.out + self.err)
        self.assertFalse(os.path.exists(self.path("backup.csv")))
        self.assertFalse(os.path.exists(self.path("log.csv")))
        self.assertEqual(self.run_main("--backup", self.path("b.csv")), 0)
        self.assertEqual([r["fullname"] for r in self.read_csv("b.csv")], ["t1_c1", "t1_c2", "t1_c3"])
        self.assertEqual(self.reddit.calls, [])

    def test_apply_deletes_only_filtered_items(self):
        code = self.run_main("--apply", "--yes", "--subreddit", "PYTHON", "--subreddit", "news")
        self.assertEqual(code, 0)
        self.assertEqual(self.deleted(), ["t1_c1", "t1_c3"])
        statuses = [(r["fullname"], r["action"], r["status"]) for r in self.read_csv("log.csv")]
        self.assertEqual(statuses, [("t1_c1", "delete", "ok"), ("t1_c3", "delete", "ok")])
        self.assertEqual(self.sleeps, [2.0])

    def test_filters(self):
        cases = [
            (["--before", "2024-01-01"], ["t1_c2", "t1_c3"]),
            (["--after", "2023-01-15"], ["t1_c1", "t1_c2"]),
            (["--after", "2023-01-01", "--before", "2024-01-01"], ["t1_c2"]),
            (["--exclude-subreddit", "r/askreddit"], ["t1_c1", "t1_c3"]),
            (["--min-score", "10"], ["t1_c1", "t1_c3"]),
            (["--max-score", "0"], ["t1_c2"]),
            (["--keep-ids", "c1,t1_C3"], ["t1_c2"]),
            (["--posts", "--keep-ids", "t3_p2", "--keep-ids", "c2"], ["t1_c1", "t1_c3", "t3_p1"]),
            (["--posts-only"], ["t3_p2", "t3_p1"]),
        ]
        for extra, expected in cases:
            with self.subTest(extra=extra):
                self.reddit.calls.clear()
                self.assertEqual(self.run_main("--apply", "--yes", "--delay", "0", *extra), 0)
                self.assertEqual(sorted(self.deleted()), sorted(expected))

    def test_keep_ids_file(self):
        with open(self.path("keep.txt"), "w") as f:
            f.write("# keep these\nt1_c1\nc2, c3\n")
        self.assertEqual(self.run_main("--apply", "--yes", "--keep-ids-file", self.path("keep.txt")), 0)
        self.assertEqual(self.deleted(), [])

    def test_overwrite_edits_then_deletes_and_skips_link_posts(self):
        code = self.run_main("--apply", "--yes", "--posts-only", "--overwrite", "--placeholder", "gone")
        self.assertEqual(code, 0)
        self.assertEqual(self.reddit.calls, [("delete", "t3_p2"), ("edit", "t3_p1", "gone"),
                                             ("delete", "t3_p1")])
        log = [(r["fullname"], r["action"], r["status"]) for r in self.read_csv("log.csv")]
        self.assertIn(("t3_p2", "edit", "skipped"), log)
        self.reddit.calls.clear()
        self.run_main("--apply", "--yes", "--overwrite", "--subreddit", "news")
        self.assertEqual(self.reddit.calls, [("edit", "t1_c3", rc.DEFAULT_PLACEHOLDER),
                                             ("delete", "t1_c3")])

    def test_backup_written_before_any_change(self):
        seen = []
        self.reddit.on_write = lambda thing: seen.append(
            [r["fullname"] for r in self.read_csv("backup.csv")])
        self.assertEqual(self.run_main("--apply", "--yes", "--posts"), 0)
        rows = self.read_csv("backup.csv")
        self.assertEqual(seen[0], [r["fullname"] for r in rows])
        self.assertEqual(list(rows[0].keys()), rc.BACKUP_FIELDS)
        p1 = next(r for r in rows if r["fullname"] == "t3_p1")
        self.assertEqual((p1["id"], p1["type"], p1["subreddit"], p1["score"], p1["title"], p1["body"]),
                         ("p1", "post", "python", "5", "Title p1", "self text"))
        self.assertEqual(p1["created_utc"], "2024-02-02T00:00:00+00:00")
        self.assertEqual(p1["permalink"], "https://www.reddit.com/r/python/comments/p1/")
        c2 = next(r for r in rows if r["fullname"] == "t1_c2")
        self.assertEqual((c2["body"], c2["title"], c2["url"]), ("bad take", "", ""))

    def test_from_export_folder(self):
        folder = self.path("export")
        os.mkdir(folder)
        with open(os.path.join(folder, "comments.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "permalink", "date", "ip", "subreddit", "gildings", "link",
                        "parent", "body", "media"])
            for cid in ("old1", "gone", "c1", "missing"):
                w.writerow([cid, f"https://www.reddit.com/r/python/comments/x/y/{cid}/",
                            "2015-01-01 00:00:00 UTC", "", "python", "0",
                            "https://www.reddit.com/r/python/comments/x/", "t3_x", "text", ""])
        code = self.run_main("--apply", "--yes", "--from-export", folder, "--subreddit", "python")
        self.assertEqual(code, 0)
        self.assertEqual(self.reddit.info_calls, [["t1_old1", "t1_gone", "t1_missing"]])
        self.assertEqual(sorted(self.deleted()), ["t1_c1", "t1_old1"])
        self.assertIn("Ignored 1 item(s) already deleted", self.out)

    def test_export_ids_batched_by_100(self):
        path = self.path("posts.csv")
        with open(path, "w", newline="") as f:
            f.write("id,permalink,date\n" + "".join(f"x{i},,\n" for i in range(250)))
        self.assertEqual(rc.export_fullnames([path])[:2], ["t3_x0", "t3_x1"])
        self.assertEqual(self.run_main("--posts", "--from-export", path), 0)
        self.assertEqual([len(b) for b in self.reddit.info_calls], [100, 100, 50])

    def test_rate_limit_retry_then_success(self):
        self.reddit.fail["t1_c1"] = 2
        self.assertEqual(self.run_main("--apply", "--yes", "--subreddit", "python"), 0)
        self.assertEqual(self.deleted(), ["t1_c1"])
        self.assertEqual(self.sleeps, [0.0, 0.0])
        self.assertIn("FakeTooManyRequests", self.out)
        self.sleeps.clear()
        errors = [FakeTooManyRequests(), FakeTooManyRequests()]  # no retry-after hint

        def flaky():
            if errors:
                raise errors.pop()
        with contextlib.redirect_stdout(io.StringIO()):
            rc.with_retries(flaky, 5, self.sleeps.append)
        self.assertTrue(1 <= self.sleeps[0] <= 2 and 2 <= self.sleeps[1] <= 3, self.sleeps)

    def test_retries_exhausted_records_failure_and_continues(self):
        self.reddit.fail["t1_c1"] = 10
        code = self.run_main("--apply", "--yes", "--max-retries", "1", "--delay", "0")
        self.assertEqual(code, 1)
        self.assertEqual(self.deleted(), ["t1_c2", "t1_c3"])
        failed = [r for r in self.read_csv("log.csv") if r["status"] == "failed"]
        self.assertEqual([r["fullname"] for r in failed], ["t1_c1"])

    def test_confirmation(self):
        self.assertEqual(self.run_main("--apply", typed="yes"), 2)
        self.assertEqual(self.reddit.calls, [])
        self.assertFalse(os.path.exists(self.path("backup.csv")))
        self.assertEqual(self.run_main("--apply", typed="DELETE 3 ITEMS"), 0)
        self.assertEqual(len(self.deleted()), 3)

    def test_missing_env_vars_exit_2(self):
        connected = []
        env = dict(ENV, REDDIT_PASSWORD="")
        del env["REDDIT_CLIENT_SECRET"]
        self.assertEqual(self.run_main(env=env, connect=connected.append), 2)
        self.assertEqual(connected, [])
        self.assertIn("REDDIT_CLIENT_SECRET, REDDIT_PASSWORD", self.err)

    def test_credentials_and_default_user_agent(self):
        creds = rc.read_credentials(ENV)
        self.assertEqual(creds["REDDIT_USER_AGENT"], "reddit-cleanup/1.0 by u/me")
        self.assertEqual(rc.read_credentials(dict(ENV, REDDIT_USER_AGENT="ua/2"))["REDDIT_USER_AGENT"], "ua/2")

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.run_main("--before", "2024/01/01"), 2)
        self.assertEqual(self.run_main("--posts", "--posts-only"), 2)
        self.assertEqual(self.run_main("--from-export", self.path("nope.csv")), 2)


if __name__ == "__main__":
    unittest.main()
