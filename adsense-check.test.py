#!/usr/bin/env python3
"""E2E for adsense-check. A local http.server fixture; no real network.

Correct site passes; ads.txt 404, wrong content type, HTML soft-404, wrong
or uppercase cert id FAIL while BOM and a trailing comment PASS; meta tag
missing, twice, wrong or bare pub- id, inside <noscript> or <body> FAIL;
off-domain redirect FAILs even when it serves a valid site, www-to-apex
PASSes, sibling subdomain FAILs; bad publisher ids exit 2 unfetched; only
GETs to the two URLs happen; --json parses, carries status/hops, no bodies.
"""
import json, os, re, socket, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOOL = Path(__file__).with_name("adsense-check")
PUB = "ca-pub-0000000000000000"
DIG = "0000000000000000"
ADS_OK = f"google.com, pub-{DIG}, DIRECT, f08c47fec0942fa0\n"
META = f'<meta name="google-adsense-account" content="{PUB}">'
HOME_OK = f"<html><head>{META}</head><body>example</body></html>"
SENT = "BODY-SENTINEL-9f3e"

ROUTES = {}  # (host, path) -> (status, headers, body) or ("redirect", location)
LOG = []     # (method, host, path); every request method is logged


class Fake(BaseHTTPRequestHandler):
    log_message = lambda *a: None

    def _record(self):
        LOG.append((self.command, self.headers.get("Host", "").split(":")[0], self.path))

    def do_GET(self):
        self._record()
        host = self.headers.get("Host", "").split(":")[0]
        spec = (ROUTES.get((host, self.path)) or ROUTES.get(("*", self.path))
                or (404, {}, "not found"))
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


def run(name, base, domain="example.com", pub=PUB, args=(), fix=None, want_rc=0, want=(), check=None):
    (fix or site)()
    env = {k: v for k, v in os.environ.items() if not k.startswith("ADSENSE_CHECK_")}
    env["ADSENSE_CHECK_TEST_BASE_URL"] = base
    r = subprocess.run([str(TOOL), domain, pub, *args], env=env, capture_output=True, text=True)
    out = r.stdout + r.stderr
    bad = [f"exit {r.returncode} != {want_rc}"] if r.returncode != want_rc else []
    bad += [f"missing {w!r}" for w in want if not re.search(w, out)]
    bad += check() if check else []
    print(("  ok   " if not bad else "  FAIL ") + name + ("" if not bad else f": {bad}"))
    return bad


def only_two_gets():
    return [f"unexpected request {m} {h}{p}" for m, h, p in LOG
            if m != "GET" or p not in ("/", "/ads.txt")]


def not_fetched():
    return lambda: [] if not LOG else [f"fetched {LOG}"]


def no_host(host):
    return lambda: [] if host not in [h for _, h, _ in LOG] else [f"fetched {host}"]


def resolves(host):
    try:
        socket.gethostbyname(host)
        return True
    except OSError:
        return False


def json_run(base):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ADSENSE_CHECK_")}
    env["ADSENSE_CHECK_TEST_BASE_URL"] = base
    r = subprocess.run([str(TOOL), "example.com", PUB, "--json"], env=env,
                       capture_output=True, text=True)
    return r, json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}


def main():
    srv, port = serve()
    base = f"http://127.0.0.1:{port}"
    fails = []

    fails += run("correct site passes", base,
                 want=["PASS ads.txt", "PASS meta tag", "adsense-check: ok"], check=only_two_gets)
    fails += run("ads.txt 404 fails", base, want_rc=1,
                 fix=lambda: site(ads=(404, {"Content-Type": "text/plain"}, "nope")),
                 want=["FAIL ads.txt", "adsense-check: failed"])
    fails += run("ads.txt text/html fails", base, want_rc=1,
                 fix=lambda: site(ads=plain(ctype="text/html")), want=[r"FAIL ads\.txt.*content-type"])
    fails += run("ads.txt soft-404 html fails", base, want_rc=1,
                 fix=lambda: site(ads=plain(ADS_OK + "<html><body>soft 404</body></html>")),
                 want=["FAIL ads.txt"])
    fails += run("wrong cert id fails", base, want_rc=1,
                 fix=lambda: site(ads=plain(f"google.com, pub-{DIG}, DIRECT, f08c47fec0942fa1\n")),
                 want=["FAIL ads.txt"])
    fails += run("uppercase cert id fails", base, want_rc=1,
                 fix=lambda: site(ads=plain(f"google.com, pub-{DIG}, DIRECT, F08C47FEC0942FA0\n")),
                 want=["FAIL ads.txt"])
    fails += run("bom and comment pass", base,
                 fix=lambda: site(ads=plain("\ufeff" + ADS_OK.rstrip("\n") + " # main\n")),
                 want=["PASS ads.txt", "adsense-check: ok"])
    other = "ca-pub-" + "1" * 16  # synthetic id, clearly not a real publisher
    meta_cases = [
        ("meta tag missing fails", "<html><head></head><body>x</body></html>", ["FAIL meta tag"]),
        ("meta tag twice fails", HOME_OK.replace("</head>", META + "</head>"), ["FAIL meta tag"]),
        ("meta tag wrong id fails", HOME_OK.replace(PUB, other),
         ["FAIL meta tag", re.escape(other), re.escape(PUB)]),
        ("meta tag in noscript fails",
         f"<html><head><noscript>{META}</noscript></head><body>x</body></html>", ["FAIL meta tag"]),
        ("meta tag in body fails", f"<html><head></head><body>{META}</body></html>",
         ["FAIL meta tag", "outside head"]),
        ("meta tag bare pub- fails", HOME_OK.replace(PUB, "pub-" + DIG), ["FAIL meta tag"]),
    ]
    for name, page, want in meta_cases:
        fails += run(name, base, want_rc=1, fix=lambda p=page: site(page=home(p)), want=want)

    # Redirects: off-domain host serving a valid site FAILS; www to apex
    # PASSes; a sibling subdomain FAILS.
    lbase = f"http://localhost:{port}"
    def off_domain():
        site()  # wildcard routes serve 127.0.0.1 a valid site via fallback
        ROUTES[("localhost", "/ads.txt")] = ("redirect", f"http://127.0.0.1:{port}/ads.txt")
        ROUTES[("localhost", "/")] = ("redirect", f"http://127.0.0.1:{port}/")
    fails += run("redirect off-domain fails", lbase, want_rc=1, fix=off_domain,
                 want=["FAIL", "left the site domain"],
                 check=lambda: only_two_gets() + no_host("127.0.0.1")())
    wbase = f"http://www.localhost:{port}"
    def www_pair():
        site()  # wildcard routes already serve localhost a valid site
        ROUTES[("www.localhost", "/ads.txt")] = ("redirect", f"http://localhost:{port}/ads.txt")
        ROUTES[("www.localhost", "/")] = ("redirect", f"http://localhost:{port}/")
    if resolves("www.localhost"):
        fails += run("www to apex redirect passes", wbase, fix=www_pair,
                     want=["PASS ads.txt", "PASS meta tag", "adsense-check: ok"],
                     check=only_two_gets)
    else:
        print("  ok   www.localhost does not resolve here; apex-pair case skipped")
    fbase = f"http://foo.localhost:{port}"
    def siblings():
        site()  # wildcard routes already serve bar.localhost a valid site
        ROUTES[("foo.localhost", "/ads.txt")] = ("redirect", f"http://bar.localhost:{port}/ads.txt")
        ROUTES[("foo.localhost", "/")] = ("redirect", f"http://bar.localhost:{port}/")
    if resolves("bar.localhost"):
        fails += run("sibling subdomain redirect fails", fbase, want_rc=1, fix=siblings,
                     want=["FAIL", "left the site domain"], check=no_host("bar.localhost"))
    else:
        print("  ok   *.localhost does not resolve here; sibling case skipped")

    # Bad publisher ids: exit 2, nothing fetched.
    for bad_id in ("ca-pub-123", "abc", "ca-pub-٠١٢٣٤٥٦٧٨٩٠١٢٣٤٥"):
        fails += run(f"{bad_id!r} rejected", base, pub=bad_id, want_rc=2,
                     want=["publisher id"], check=not_fetched())

    # --json parses, carries status codes and hops, leaks no body text.
    site(ads=plain(ADS_OK + f"# {SENT}\n"), page=home(HOME_OK.replace("</body>", f"<!-- {SENT} --></body>")))
    r, doc = json_run(base)
    out = r.stdout + r.stderr
    bad = [f"exit {r.returncode} != 0"] if r.returncode != 0 else []
    if doc.get("ok") is not True:
        bad.append("json ok is not true")
    for key in ("ads.txt", "home"):
        f = (doc.get("fetches") or {}).get(key) or {}
        if f.get("status") != 200 or not f.get("hops") or f["hops"][-1].get("status") != 200:
            bad.append(f"fetches.{key} lacks status/hops: {f}")
    if SENT in out:
        bad.append("response body leaked into output")
    print(("  ok   " if not bad else "  FAIL ") + "json output clean" + ("" if not bad else f": {bad}"))
    fails += bad

    # --json records every redirect hop (www to apex fixture).
    www_pair()
    r, doc = json_run(wbase)
    try:
        hops = doc["fetches"]["ads.txt"]["hops"]
        bad = [] if [h["status"] for h in hops] == [301, 200] else [f"hops {hops}"]
    except Exception as e:
        bad = [f"json hops: {e}"]
    print(("  ok   " if not bad else "  FAIL ") + "json redirect hops" + ("" if not bad else f": {bad}"))
    fails += bad

    srv.shutdown()
    print(f"{'PASS' if not fails else 'FAIL'}: {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
