#!/usr/bin/env python3
"""Tests for pinterest_privacy.py against a local mock of the Pinterest API v5."""
import builtins
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pinterest_privacy as pp  # noqa: E402

TOKEN = "test-token-123"
INITIAL = [
    {"id": "b1", "name": "Recipes", "privacy": "PUBLIC"},
    {"id": "b2", "name": "Travel Ideas", "privacy": "SECRET"},
    {"id": "b3", "name": "Work Stuff", "privacy": "PROTECTED"},
    {"id": "b4", "name": "Travel 2024", "privacy": "PUBLIC"},
    {"id": "b5", "name": "Old Recipes", "privacy": "PUBLIC"},
]


class MockApi(BaseHTTPRequestHandler):
    boards = {}
    calls = []
    throttle_once = True

    def log_message(self, *args):
        pass

    def _send(self, code, payload=None, headers=None):
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        MockApi.calls.append((self.command, url.path, parse_qs(url.query), body))
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._send(401, {"message": "Authentication failed."})
        ordered = [MockApi.boards[b["id"]] for b in INITIAL if b["id"] in MockApi.boards]
        if self.command == "GET" and url.path == "/v5/boards":
            if parse_qs(url.query).get("bookmark") == ["p2"]:
                if MockApi.throttle_once:
                    MockApi.throttle_once = False
                    return self._send(429, {"message": "slow down"}, {"Retry-After": "0"})
                return self._send(200, {"items": ordered[3:], "bookmark": None})
            return self._send(200, {"items": ordered[:3], "bookmark": "p2"})
        board_id = url.path.rsplit("/", 1)[-1]
        if board_id not in MockApi.boards:
            return self._send(404, {"message": "not found"})
        if self.command == "PATCH":
            MockApi.boards[board_id]["privacy"] = body["privacy"]
            return self._send(200, MockApi.boards[board_id])
        if self.command == "DELETE":
            del MockApi.boards[board_id]
            return self._send(204)
        self._send(405)

    do_GET = do_PATCH = do_DELETE = _handle


class PinterestPrivacyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockApi)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/v5"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        MockApi.boards = {b["id"]: dict(b) for b in INITIAL}
        MockApi.calls = []
        MockApi.throttle_once = True
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "log.json")
        env = {"PINTEREST_ACCESS_TOKEN": TOKEN, "PINTEREST_API_BASE": self.base}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = pp.main(["--delay", "0", "--log", self.log, *argv])
        return code, out.getvalue()

    def writes(self, method="PATCH"):
        return [(c[1].rsplit("/", 1)[-1], c[3]) for c in MockApi.calls if c[0] == method]

    def privacy(self):
        return {k: v["privacy"] for k, v in MockApi.boards.items()}

    def test_defaults_are_dry_run(self):
        args = pp.parse_args([])
        self.assertFalse(args.apply)
        self.assertFalse(args.delete)
        self.assertEqual((args.max_retries, args.delay), (5, 0.5))
        self.assertTrue(args.log.startswith("pinterest-privacy-log-"))
        self.assertTrue(pp.parse_args(["--apply"]).apply)

    def test_dry_run_makes_no_changes(self):
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(self.writes(), [])
        self.assertIn("Dry run", out)
        self.assertIn("make SECRET", out)
        self.assertFalse(os.path.exists(self.log))
        self.assertNotIn(TOKEN, out)

    def test_apply_patches_only_public_boards(self):
        code, _ = self.run_main("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.writes(), [(b, {"privacy": "SECRET"}) for b in ("b1", "b4", "b5")])
        self.assertEqual(self.privacy()["b3"], "PROTECTED")

    def test_pagination_and_429_retry(self):
        with contextlib.redirect_stdout(io.StringIO()):
            boards = pp.PinterestClient(TOKEN, self.base, sleep=lambda s: None).list_boards()
        self.assertEqual([b["id"] for b in boards], ["b1", "b2", "b3", "b4", "b5"])
        gets = [c for c in MockApi.calls if c[0] == "GET"]
        self.assertEqual(len(gets), 3)  # page 1, throttled page 2, page 2 again
        self.assertEqual(gets[0][2]["page_size"], ["250"])
        self.assertEqual(gets[2][2]["bookmark"], ["p2"])

    def test_include_exclude(self):
        self.run_main("--apply", "--include", "recipes", "--exclude", "old")
        self.assertEqual([b for b, _ in self.writes()], ["b1"])
        MockApi.calls = []
        self.run_main("--apply", "--include", "travel*")
        self.assertEqual([b for b, _ in self.writes()], ["b4"])
        boards = [dict(b) for b in INITIAL]
        self.assertEqual([b["id"] for b in pp.select(boards, ["b3"], [])], ["b3"])
        self.assertEqual(len(pp.select(boards, [], ["*"])), 0)

    def test_log_written(self):
        self.run_main("--apply")
        with open(self.log) as f:
            entries = json.load(f)
        self.assertEqual([e["board_id"] for e in entries], ["b1", "b4", "b5"])
        e = entries[0]
        for key in ("timestamp", "action", "board_id", "board_name", "previous_privacy",
                    "new_privacy", "status", "error"):
            self.assertIn(key, e)
        self.assertEqual((e["previous_privacy"], e["new_privacy"], e["status"]), ("PUBLIC", "SECRET", "ok"))

    def test_undo_restores_public(self):
        self.run_main("--apply")
        undo_log = os.path.join(self.tmp.name, "undo.json")
        MockApi.calls = []
        self.run_main("--undo", self.log, "--log", undo_log)
        self.assertEqual(self.writes(), [])  # dry run by default
        code, _ = self.run_main("--undo", self.log, "--apply", "--log", undo_log)
        self.assertEqual(code, 0)
        self.assertEqual(self.writes(), [(b, {"privacy": "PUBLIC"}) for b in ("b1", "b4", "b5")])
        self.assertEqual(self.privacy(), {b["id"]: b["privacy"] for b in INITIAL})

    def test_delete_without_confirmation_aborts(self):
        with mock.patch.object(builtins, "input", return_value="yes"):
            code, out = self.run_main("--apply", "--delete", "--include", "recipes")
        self.assertEqual(code, 2)
        self.assertEqual(self.writes("DELETE"), [])
        self.assertIn("7 days", out)

    def test_delete_with_typed_confirmation(self):
        with mock.patch.object(builtins, "input", return_value="DELETE 2 BOARDS"):
            code, _ = self.run_main("--apply", "--delete", "--include", "recipes")
        self.assertEqual(code, 0)
        self.assertEqual([b for b, _ in self.writes("DELETE")], ["b1", "b5"])

    def test_delete_with_flag_calls_delete(self):
        code, _ = self.run_main("--apply", "--delete", "--yes-i-understand-delete", "--include", "recipes")
        self.assertEqual(code, 0)
        self.assertEqual([b for b, _ in self.writes("DELETE")], ["b1", "b5"])
        self.assertNotIn("b1", MockApi.boards)

    def test_missing_token_exits_2(self):
        with mock.patch.dict(os.environ, {"PINTEREST_ACCESS_TOKEN": ""}):
            code, _ = self.run_main()
        self.assertEqual(code, 2)
        self.assertEqual(MockApi.calls, [])

    def test_bad_token_exits_2_with_scope_hint(self):
        with mock.patch.dict(os.environ, {"PINTEREST_ACCESS_TOKEN": "wrong"}):
            code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("boards:write", out)
        self.assertNotIn("wrong", out)


if __name__ == "__main__":
    unittest.main()
