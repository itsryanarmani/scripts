"""A local stand-in for the Typefully v2 drafts API, for the tests.

It is strict on purpose: a PATCH replaces the whole platforms object, so a
platform the caller leaves out is dropped. A real-API PATCH that forgets a
platform would fail the same test. State lives in a JSON file so the test
can seed it and read it back.
"""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

STATE = sys.argv[2]


class H(BaseHTTPRequestHandler):
    def _drafts(self):
        return json.load(open(STATE))

    def _send(self, code, body):
        b = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)

    def _id(self):
        return self.path.rstrip("/").split("/")[-1]

    def do_GET(self):
        d = self._drafts().get(self._id())
        if d is None or d.get("_fail"):
            return self._send(500, {"error": "boom"})
        self._send(200, d)

    def do_PATCH(self):
        s = self._drafts(); d = s[self._id()]
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if "platforms" in body:
            d["platforms"] = body["platforms"]
        if "publish_at" in body:
            d["status"] = "scheduled"; d["scheduled_date"] = body["publish_at"]
        d.setdefault("_patches", 0); d["_patches"] += 1
        json.dump(s, open(STATE, "w"))
        self._send(200, d)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
