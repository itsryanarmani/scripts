#!/usr/bin/env python3
"""E2E for adsense-check. Local http.server fixture; no real network.

ads.txt 404, wrong content type, HTML soft-404, wrong/uppercase cert id
FAIL; BOM and trailing comment PASS. Meta tag missing, duplicated, wrong/
bare-pub-/two ids, <noscript>/<body> FAIL. Off-domain, sibling and ftp:
redirects FAIL even when the target is valid; www-to-apex PASSes. Bad ids
exit 2 unfetched. Only GETs to the two URLs. --json has status/hops, no bodies.
A trickling body hits the deadline.
"""
import json, os, re, socket, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOOL = Path(__file__).with_name("adsense-check")
PUB = "ca-pub-0000000000000000"
DIG = "0000000000000000"
ADS_OK = f"google.com, pub-{DIG}, DIRECT, f08c47fec0942fa0\n"
META = f'<meta name="google-adsense-account" content="{PUB}">'
HOME_OK = f"<html><head>{META}</head><body>example</body></html>"
SENT = "BODY-SENTINEL-9f3e"
OKW = ["PASS ads.txt", "PASS meta tag", "adsense-check: ok"]
FW = ["FAIL ads.txt", "adsense-check: failed"]

ROUTES = {}  # (host, path) -> (status, headers, body), ("redirect", loc) or ("trickle",)
LOG = []     # (method, host, path); every request method is logged


class Fake(BaseHTTPRequestHandler):
    log_message = lambda *a: None

    def _record(self):
        LOG.append((self.command, self.headers.get("Host", "").split(":")[0], self.path))

    def do_GET(self):
        self._record()
        host = self.headers.get("Host", "").split(":")[0]
        spec = (ROUTES.get((host, self.path)) or ROUTES.get(("*", self.path)) or (404, {}, "x"))
        if spec[0] == "redirect":
            self.send_response(301)
            self.send_header("Location", spec[1])
            self.end_headers()
            return
        if spec[0] == "trickle":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            try:
                while True:
                    self.wfile.write(b"x"); self.wfile.flush(); time.sleep(0.2)
            except OSError:
                pass
            return
        status, headers, body = spec
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode())

    def _reject(self):
        self._record()
        self.send_error(501)

    do_HEAD = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _reject


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_port


def plain(body=ADS_OK, ctype="text/plain"):
    return (200, {"Content-Type": ctype}, body)


def home(body=HOME_OK):
    return (200, {"Content-Type": "text/html"}, body)


def site(ads=None, page=None):
    ROUTES.clear()
    LOG.clear()
    ROUTES[("*", "/ads.txt")] = ads if ads is not None else plain()
    ROUTES[("*", "/")] = page if page is not None else home()


def env_for(base, deadline=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ADSENSE_CHECK_")}
    env["ADSENSE_CHECK_TEST_BASE_URL"] = base
    if deadline: env["ADSENSE_CHECK_TEST_DEADLINE"] = str(deadline)
    return env


def run(name, base, pub=PUB, args=(), fix=None, want_rc=1, want=(), check=None, deadline=None):
    (fix or site)()
    try:
        r = subprocess.run([str(TOOL), "example.com", pub, *args], env=env_for(base, deadline),
                           capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        print(f"  FAIL {name}: subprocess timed out"); return ["timeout"]
    out = r.stdout + r.stderr
    bad = [f"exit {r.returncode} != {want_rc}"] if r.returncode != want_rc else []
    bad += [f"missing {w!r}" for w in want if not re.search(w, out)]
    bad += check() if check else []
    print(("  ok   " if not bad else "  FAIL ") + name + ("" if not bad else f": {bad}"))
    return bad


def only_two_gets():
    return [f"unexpected {m} {h}{p}" for m, h, p in LOG if m != "GET" or p not in ("/", "/ads.txt")]


def no_host(host):
    return lambda: [] if host not in [h for _, h, _ in LOG] else [f"fetched {host}"]


def resolves(host):
    try: socket.gethostbyname(host); return True
    except OSError: return False


def json_run(base):
    r = subprocess.run([str(TOOL), "example.com", PUB, "--json"], env=env_for(base), capture_output=True, text=True, timeout=25)
    return r, json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}


def main():
    srv, port = serve()
    base = f"http://127.0.0.1:{port}"
    lbase = f"http://localhost:{port}"
    fails = []
    other = "ca-pub-" + "1" * 16  # synthetic id, clearly not a real publisher

    def redir(routes):
        def f():
            site()  # wildcard fallback serves every other host a valid site
            ROUTES.update({k: ("redirect", v) for k, v in routes.items()})
        return f

    page = lambda p: (lambda: site(page=home(p)))
    ads_line = lambda cert: lambda: site(ads=plain(f"google.com, pub-{DIG}, DIRECT, {cert}\n"))
    rows = [
        ("correct site passes", base, None, OKW, only_two_gets),
        ("ads.txt 404 fails", base, lambda: site(ads=(404, {"Content-Type": "text/plain"}, "x")), FW),
        ("ads.txt text/html fails", base, lambda: site(ads=plain(ctype="text/html")), [r"FAIL ads\.txt.*content-type"]),
        ("ads.txt soft-404 html fails", base, lambda: site(ads=plain(ADS_OK + "<html><body>soft 404</body></html>")), ["FAIL ads.txt"]),
        ("wrong cert id fails", base, ads_line("f08c47fec0942fa1"), ["FAIL ads.txt"]),
        ("uppercase cert id fails", base, ads_line("F08C47FEC0942FA0"), ["FAIL ads.txt"]),
        ("bom and comment pass", base, lambda: site(ads=plain("\ufeff" + ADS_OK.rstrip("\n") + " # main\n")), OKW),
        ("meta tag missing fails", base, page("<html><head></head><body>x</body></html>"), ["FAIL meta tag"]),
        ("meta tag twice fails", base, page(HOME_OK.replace("</head>", META + "</head>")), ["FAIL meta tag"]),
        ("meta tag two ids fails", base,
         page(f'<html><head>{META}<meta name="google-adsense-account" content="{other}"></head><body>x</body></html>'),
         ["FAIL meta tag", re.escape(other), re.escape(PUB)]),
        ("meta tag wrong id fails", base, page(HOME_OK.replace(PUB, other)), ["FAIL meta tag", re.escape(other), re.escape(PUB)]),
        ("meta tag in noscript fails", base, page(f"<html><head><noscript>{META}</noscript></head><body>x</body></html>"), ["FAIL meta tag"]),
        ("meta tag in body fails", base, page(f"<html><head></head><body>{META}</body></html>"), ["FAIL meta tag", "outside head"]),
        ("meta tag bare pub- fails", base, page(HOME_OK.replace(PUB, "pub-" + DIG)), ["FAIL meta tag"]),
        ("redirect off-domain fails", lbase,
         redir({("localhost", "/ads.txt"): f"http://127.0.0.1:{port}/ads.txt",
                ("localhost", "/"): f"http://127.0.0.1:{port}/"}),
         ["FAIL", "left the site domain"], lambda: only_two_gets() + no_host("127.0.0.1")()),
        ("ftp redirect fails", lbase, redir({("localhost", "/ads.txt"): "ftp://localhost/x"}), ["FAIL ads.txt", "unsupported URL"]),
        ("trickle body hits deadline", base, lambda: site(ads=("trickle",)), ["deadline exceeded"], None, 1.0),
    ]
    if resolves("www.localhost"):
        rows.append(("www to apex redirect passes", f"http://www.localhost:{port}",
                     redir({("www.localhost", "/ads.txt"): f"http://localhost:{port}/ads.txt", ("www.localhost", "/"): f"http://localhost:{port}/"}),
                     OKW, only_two_gets))
    if resolves("bar.localhost"):
        rows.append(("sibling subdomain redirect fails", f"http://foo.localhost:{port}",
                     redir({("foo.localhost", "/ads.txt"): f"http://bar.localhost:{port}/ads.txt", ("foo.localhost", "/"): f"http://bar.localhost:{port}/"}),
                     ["FAIL", "left the site domain"], no_host("bar.localhost")))
    for name, b, fix, want, *rest in rows:
        fails += run(name, b, fix=fix, want=want,
                     check=rest[0] if rest else None,
                     want_rc=0 if want is OKW else 1,
                     deadline=rest[1] if len(rest) > 1 else None)

    # Bad publisher ids: exit 2, nothing fetched.
    for bad_id in ("ca-pub-123", "abc", "ca-pub-٠١٢٣٤٥٦٧٨٩٠١٢٣٤٥"):
        fails += run(f"{bad_id!r} rejected", base, pub=bad_id, want_rc=2, want=["publisher id"],
                     check=lambda: [] if not LOG else [f"fetched {LOG}"])

    # --json parses, carries status codes and hops, leaks no body text.
    site(ads=plain(ADS_OK + f"# {SENT}\n"), page=home(HOME_OK.replace("</body>", f"<!-- {SENT} --></body>")))
    r, doc = json_run(base)
    out = r.stdout + r.stderr
    bad = [f"exit {r.returncode} != 0"] if r.returncode != 0 else []
    bad += [] if doc.get("ok") is True else ["json ok is not true"]
    for key in ("ads.txt", "home"):
        f = (doc.get("fetches") or {}).get(key) or {}
        if f.get("status") != 200 or (f.get("hops") or [{}])[-1].get("status") != 200:
            bad.append(f"fetches.{key} lacks status/hops")
    bad += ["response body leaked"] if SENT in out else []
    print(("  ok   " if not bad else "  FAIL ") + "json output clean" + ("" if not bad else f": {bad}"))
    fails += bad

    # --json records every redirect hop (www to apex fixture).
    bad = []
    if resolves("www.localhost"):
        redir({("www.localhost", "/ads.txt"): f"http://localhost:{port}/ads.txt",
               ("www.localhost", "/"): f"http://localhost:{port}/"})()
        r, doc = json_run(f"http://www.localhost:{port}")
        try:
            hops = doc["fetches"]["ads.txt"]["hops"]
            bad = [] if [h["status"] for h in hops] == [301, 200] else [f"hops {[h.get('status') for h in hops]}"]
        except Exception as e:
            bad = [f"json hops: {e}"]
    print(("  ok   " if not bad else "  FAIL ") + "json redirect hops" + ("" if not bad else f": {bad}"))
    fails += bad

    srv.shutdown()
    print(f"{'PASS' if not fails else 'FAIL'}: {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
