#!/usr/bin/env python3
"""E2E for adsense-check. A local http.server fixture; no real network.

Ways a check can fail, written before the tool. Each one is a case below:
 1. A correct site passes both checks, exit 0.
 2. ads.txt returns 404: FAIL, exit 1.
 3. ads.txt returns 200 with text/html: FAIL on content type.
 4. ads.txt returns 200 with an HTML soft-404 page: FAIL.
 5. ads.txt has the right line but the wrong certification id: FAIL.
 6. The meta tag is missing, present twice, or present with a different id: FAIL.
 7. A redirect to another registrable domain: FAIL. www to apex: PASS.
 8. A publisher id of ca-pub-123 or abc: exit 2, nothing fetched.
 9. The script makes no request other than GET to the two URLs.
10. --json output parses as JSON and has no body text.
"""
import json, os, re, socket, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOOL = Path(__file__).with_name("adsense-check")
PUB = "ca-pub-0000000000000000"
DIG = "0000000000000000"
ADS_OK = f"google.com, pub-{DIG}, DIRECT, f08c47fec0942fa0\n"
HOME_OK = (f'<html><head><meta name="google-adsense-account" content="{PUB}">'
           "</head><body>example</body></html>")
SENT = "BODY-SENTINEL-9f3e"

ROUTES = {}  # (host, path) -> (status, headers, body) or ("redirect", location)
LOG = []     # (method, host, path)


class Fake(BaseHTTPRequestHandler):
    log_message = lambda *a: None

    def do_GET(self):
        host = self.headers.get("Host", "").split(":")[0]
        LOG.append((self.command, host, self.path))
        spec = ROUTES.get((host, self.path)) or ROUTES.get(("*", self.path)) or (404, {}, "not found")
        if spec[0] == "redirect":
            self.send_response(301)
            self.send_header("Location", spec[1])
            self.end_headers()
            return
        status, headers, body = spec
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode())


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_port


def reset():
    ROUTES.clear()
    LOG.clear()


def plain(body=ADS_OK, ctype="text/plain"):
    return (200, {"Content-Type": ctype}, body)


def home(body=HOME_OK):
    return (200, {"Content-Type": "text/html"}, body)


def run(name, base, domain="example.com", pub=PUB, args=(), want_rc=0, want=(), ban=(), check=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ADSENSE_CHECK_")}
    env["ADSENSE_CHECK_BASE_URL"] = base
    r = subprocess.run([str(TOOL), domain, pub, *args], env=env, capture_output=True, text=True)
    out = r.stdout + r.stderr
    bad = [f"exit {r.returncode} != {want_rc}"] if r.returncode != want_rc else []
    bad += [f"missing {w!r}" for w in want if not re.search(w, out)]
    bad += [f"found banned {b!r}" for b in ban if b in out]
    bad += check() if check else []
    print(("  ok   " if not bad else "  FAIL ") + name + ("" if not bad else f": {bad}"))
    return bad


def only_two_gets():
    bad = [f"unexpected request {m}" for m, h, p in LOG if m != "GET" or p not in ("/", "/ads.txt")]
    return bad


def main():
    srv, port = serve()
    srv2, port2 = serve()
    base = f"http://127.0.0.1:{port}"
    fails = []

    # 1. A correct site passes both checks.
    reset()
    ROUTES[("*", "/ads.txt")] = plain()
    ROUTES[("*", "/")] = home()
    fails += run("correct site passes", base, want=["PASS ads.txt", "PASS meta tag", "adsense-check: ok"],
                 check=only_two_gets)

    # 2. ads.txt returns 404.
    reset()
    ROUTES[("*", "/ads.txt")] = (404, {"Content-Type": "text/plain"}, "nope")
    ROUTES[("*", "/")] = home()
    fails += run("ads.txt 404 fails", base, want_rc=1, want=["FAIL ads.txt", "adsense-check: failed"])

    # 3. ads.txt returns 200 with text/html.
    reset()
    ROUTES[("*", "/ads.txt")] = plain(ctype="text/html")
    ROUTES[("*", "/")] = home()
    fails += run("ads.txt text/html fails", base, want_rc=1,
                 want=[r"FAIL ads\.txt.*content-type"])

    # 4. ads.txt returns 200 with an HTML soft-404 page.
    reset()
    ROUTES[("*", "/ads.txt")] = plain(ADS_OK + "<html><body>soft 404</body></html>")
    ROUTES[("*", "/")] = home()
    fails += run("ads.txt soft-404 html fails", base, want_rc=1, want=["FAIL ads.txt"])

    # 5. Right line, wrong certification id.
    reset()
    ROUTES[("*", "/ads.txt")] = plain(f"google.com, pub-{DIG}, DIRECT, f08c47fec0942fa1\n")
    ROUTES[("*", "/")] = home()
    fails += run("wrong cert id fails", base, want_rc=1, want=["FAIL ads.txt"])

    # 6. Meta tag missing / twice / different id.
    reset()
    ROUTES[("*", "/ads.txt")] = plain()
    ROUTES[("*", "/")] = home('<html><head></head><body>x</body></html>')
    fails += run("meta tag missing fails", base, want_rc=1, want=["FAIL meta tag"])
    reset()
    two = HOME_OK.replace("</head>", '<meta name="google-adsense-account" content="%s"></head>' % PUB)
    ROUTES[("*", "/ads.txt")] = plain()
    ROUTES[("*", "/")] = home(two)
    fails += run("meta tag twice fails", base, want_rc=1, want=["FAIL meta tag"])
    reset()
    other = "ca-pub-" + "1" * 16  # synthetic id, clearly not a real publisher
    ROUTES[("*", "/ads.txt")] = plain()
    ROUTES[("*", "/")] = home(HOME_OK.replace(PUB, other))
    fails += run("meta tag wrong id fails", base, want_rc=1,
                 want=["FAIL meta tag", re.escape(other), re.escape(PUB)])

    # 7. Redirect off the registrable domain fails; www to apex passes.
    reset()
    lbase = f"http://localhost:{port}"
    ROUTES[("*", "/ads.txt")] = ("redirect", f"http://127.0.0.1:{port2}/ads.txt")
    ROUTES[("*", "/")] = ("redirect", f"http://127.0.0.1:{port2}/")
    fails += run("redirect off-domain fails", lbase, want_rc=1,
                 want=["FAIL", "redirect"], check=only_two_gets)
    reset()
    wbase = f"http://www.localhost:{port}"
    ROUTES[("www.localhost", "/ads.txt")] = ("redirect", f"http://localhost:{port}/ads.txt")
    ROUTES[("localhost", "/ads.txt")] = plain()
    ROUTES[("www.localhost", "/")] = ("redirect", f"http://localhost:{port}/")
    ROUTES[("localhost", "/")] = home()
    try:
        socket.gethostbyname("www.localhost")
    except OSError:
        print("  ok   www.localhost does not resolve here; apex-pair case skipped")
    else:
        fails += run("www to apex redirect passes", wbase, want=["PASS ads.txt", "PASS meta tag",
                     "adsense-check: ok"], check=only_two_gets)

    # 8. Bad publisher ids: exit 2, nothing fetched.
    reset()
    fails += run("ca-pub-123 rejected", base, pub="ca-pub-123", want_rc=2,
                 want=["publisher id"], check=lambda: [] if not LOG else [f"fetched {LOG}"])
    fails += run("abc rejected", base, pub="abc", want_rc=2,
                 want=["publisher id"], check=lambda: [] if not LOG else [f"fetched {LOG}"])

    # 9. Only GET to the two URLs (asserted inside cases 1 and 7; explicit log check here).
    reset()
    ROUTES[("*", "/ads.txt")] = plain()
    ROUTES[("*", "/")] = home()
    fails += run("request log clean", base, want=["adsense-check: ok"], check=only_two_gets)

    # 10. --json parses, carries results, and leaks no body text.
    reset()
    ROUTES[("*", "/ads.txt")] = plain(ADS_OK + f"# {SENT}\n")
    ROUTES[("*", "/")] = home(HOME_OK.replace("</body>", f"<!-- {SENT} --></body>"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("ADSENSE_CHECK_")}
    env["ADSENSE_CHECK_BASE_URL"] = base
    r = subprocess.run([str(TOOL), "example.com", PUB, "--json"], env=env, capture_output=True, text=True)
    out = r.stdout + r.stderr
    bad = []
    if r.returncode != 0:
        bad.append(f"exit {r.returncode} != 0")
    try:
        doc = json.loads(r.stdout)
    except Exception as e:
        bad.append(f"stdout is not JSON: {e}")
        doc = {}
    if doc.get("ok") is not True:
        bad.append("json ok is not true")
    if SENT in out:
        bad.append("response body leaked into output")
    print(("  ok   " if not bad else "  FAIL ") + "json output clean" + ("" if not bad else f": {bad}"))
    fails += bad

    srv.shutdown()
    srv2.shutdown()
    print(f"{'PASS' if not fails else 'FAIL'}: {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
