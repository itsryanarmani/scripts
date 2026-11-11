#!/usr/bin/env python3
"""E2E: real ad-launch against a fake Graph API server. No Meta account is touched.

Ways a launch can fail, written before the tool. Each one is a case below:
 1. Dead landing URL (404): --execute refuses before any write.
 2. Account currency differs from --accept-currency, or the flag is missing: refuse.
 3. Duplicate run: a campaign with the same name exists: refuse, create nothing.
 4. Copy has hardship wording, or a number or price that is not in the source text: refuse.
 5. Special ad category with no country: refuse.
 6. Rate limit (code 17 / subcode 2446079): wait 60, 120, 240 s, retry 3 times, then stop.
    Any other error is not retried.
 7. A create fails midway: stop, list every object that exists (all PAUSED), exit 3.
 8. An error body carries the token: the token never reaches the output.
 9. Read-back shows an object that is not PAUSED: warn, exit 4.
10. No write ever carries ACTIVE. The token is sent in a header, never in a URL.
Success case: dry run makes no write; --execute creates PAUSED objects, Facebook-only
placements, budget sharing off, special category with country; Instagram only with an identity.
Set AD_LAUNCH_TRANSCRIPT=<file> to keep the transcript as the artifact.
"""
import json, os, re, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
TOOL = Path(__file__).with_name("ad-launch")
EXAMPLE = Path(__file__).with_name("ad-launch.example.json")
TOKEN = "EAAB-fake-token-0123456789"
STATE = {}
def reset(**mode):
    STATE.clear()
    STATE.update(mode=mode, posts=[], paths=[], objs={}, n=100, rl=0)
class Fake(BaseHTTPRequestHandler):
    log_message = lambda *a: None
    def send(self, code, body):
        self.send_response(code), self.end_headers(), self.wfile.write(json.dumps(body).encode())
    def err(self, code, sub=None, msg="error"):
        self.send(400, {"error": {"code": code, "error_subcode": sub, "message": msg, "type": "OAuthException"}})
    def do_GET(self):
        u = urlparse(self.path)
        STATE["paths"].append(self.path)
        if u.path.startswith("/landing/"):
            return self.send(404 if "dead" in self.path else 200, "page")
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self.send(401, {"error": {"code": 190, "message": "bad token"}})
        m, parts = STATE["mode"], u.path.strip("/").split("/")[1:]
        if len(parts) == 1 and parts[0].startswith("act_"):
            return self.send(200, {"currency": m.get("currency", "CAD")})
        if parts[-1] == "campaigns":
            return self.send(200, {"data": [{"id": "1", "name": m["dup"]}] if m.get("dup") else []})
        obj = dict(STATE["objs"].get(parts[0], {}))
        if m.get("leak_active") and obj.get("kind") == "ads":
            obj["configured_status"] = obj["effective_status"] = "ACTIVE"
        return self.send(200, obj)
    def do_POST(self):
        STATE["paths"].append(self.path)
        n = int(self.headers.get("Content-Length", 0))
        body = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}
        kind, m = self.path.strip("/").split("/")[-1], STATE["mode"]
        STATE["posts"].append((kind, body))
        if m.get("other_error") and kind == "campaigns":
            return self.err(17, 1, "other limit")
        if kind == "campaigns" and STATE["rl"] < m.get("rate_limit", 0):
            STATE["rl"] += 1
            return self.err(17, 2446079, "User request limit reached")
        ads = sum(1 for k, _ in STATE["posts"] if k == "ads")
        if m.get("fail_ad") and kind == "ads" and ads == m["fail_ad"]:
            return self.err(100, None, f"Invalid parameter (access_token={TOKEN})")
        if kind == "adimages":
            return self.send(200, {"images": {"x": {"hash": f"h{len(STATE['posts'])}"}}})
        STATE["n"] += 1
        oid, eff = str(STATE["n"]), "PAUSED" if kind == "campaigns" else "CAMPAIGN_PAUSED"
        STATE["objs"][oid] = {**{k: (json.loads(v) if v[:1] in "[{" else v) for k, v in body.items()},
                              "id": oid, "kind": kind, "configured_status": body.get("status"), "effective_status": eff}
        self.send(200, {"id": oid})
def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    tmp = Path(tempfile.mkdtemp())
    (tmp / "creds.env").write_text(f"META_MARKETING_TOKEN={TOKEN}\n")
    (tmp / "images").mkdir()
    [(tmp / "images" / n).write_bytes(b"\xff\xd8fake\xff\xd9") for n in ("shed-a.jpg", "shed-b.jpg")]
    env = {**{k: v for k, v in os.environ.items() if not k.startswith(("META_", "AD_LAUNCH_"))}, "AD_LAUNCH_GRAPH_URL": base, "AD_LAUNCH_SLEEP_SCALE": "0",
           "AD_LAUNCH_ENV_FILE": str(tmp / "creds.env"), "META_AD_ACCOUNT_ID": "111",
           "META_PAGE_ID": "222", "META_PIXEL_ID": "333"}
    log, fails = [], []
    def spec(edit=None):
        s = json.loads(EXAMPLE.read_text())
        for ad in s["ads"]:
            ad["link_url"] = ad["link_url"].replace("https://shed-plans.example/guide", f"{base}/landing/ok")
        edit and edit(s)
        (tmp / "spec.json").write_text(json.dumps(s))
        return str(tmp / "spec.json")
    def run(name, mode, args, want_rc, want=(), check=None):
        reset(**mode)
        r = subprocess.run([sys.executable, "-I", str(TOOL), *args], env=env, capture_output=True, text=True)
        out = r.stdout + r.stderr
        log.append(f"\n===== {name}\n$ ad-launch {' '.join(a.replace(str(tmp), '<tmp>') for a in args)}\n"
                   f"{out.replace(base, '<fake-graph>').replace(str(tmp), '<tmp>')}[exit {r.returncode}]")
        bad = [f"exit {r.returncode} != {want_rc}"] if r.returncode != want_rc else []
        bad += [f"missing {w!r}" for w in want if not re.search(w, out)]
        bad += [f"found {b!r}" for b in (TOKEN,) if b in out]
        bad += [f"token in URL {p}" for p in STATE["paths"] if TOKEN in p]
        bad += [f"ACTIVE in a write: {k}" for k, b in STATE["posts"] if "ACTIVE" in json.dumps(b)]
        bad += check() if check else []
        print(("  ok   " if not bad else "  FAIL ") + name + ("" if not bad else f": {bad}"))
        fails.extend(bad)
    posts = lambda kind: [b for k, b in STATE["posts"] if k == kind]
    ex, nowrite = ["--execute", "--accept-currency", "CAD"], lambda: ["wrote"] if STATE["posts"] else []
    run("dry run makes no write", {}, [spec()], 0, ["DRY RUN", "landing: 200"], nowrite)
    run("refuses a dead landing URL", {}, [spec(lambda s: s["ads"][0].update(link_url=s["ads"][0]["link_url"] + "&v=dead")),
        *ex], 2, ["landing URL returned 404"], nowrite)
    run("refuses without --accept-currency", {}, [spec(), "--execute"], 2, ["--accept-currency CAD"])
    run("refuses a wrong currency", {"currency": "USD"}, [spec(), *ex], 2, ["account currency is USD"])
    run("refuses a duplicate run", {"dup": "shed_guide_ca_leads"}, [spec(), *ex], 2, ["already exists"], nowrite)
    run("refuses hardship wording", {}, [spec(lambda s: s["ads"][0].update(
        primary_text="You can\u2019t\npay for a shed? Get the guide."))], 1, ["hardship wording"])
    run("refuses a number not in the source", {}, [spec(lambda s: s["ads"][0].update(
        headline="12 steps to a level base"))], 1, ["number 12 is not in the source"])
    run("refuses a price not in the source", {}, [spec(lambda s: (s["ads"][1].update(description="From $5 or 5  USD"),
        s.update(source_text=s["source_text"] + "Plans from $50.")))], 1, [r"price \$5 is not in the source"])
    run("refuses a special category with no country", {}, [spec(lambda s: s["campaign"].update(
        special_ad_categories=["HOUSING"], special_ad_category_country=[]))], 1, ["special_ad_category_country"])
    run("retries the rate limit 60/120 then succeeds", {"rate_limit": 2}, [spec(), *ex], 0,
        ["retry 1/3 in 60s", "retry 2/3 in 120s", "All objects are PAUSED"])
    run("stops after 3 rate-limit retries", {"rate_limit": 9}, [spec(), *ex], 3,
        ["retry 3/3 in 240s", "STOPPED"], check=lambda: [] if len(posts("campaigns")) == 4 else ["not 4 tries"])
    run("does not retry another error", {"other_error": 1}, [spec(), *ex], 3, ["STOPPED"],
        check=lambda: [] if len(posts("campaigns")) == 1 else ["retried"])
    run("midway failure lists what exists, scrubs the token", {"fail_ad": 2}, [spec(), *ex], 3,
        ["STOPPED", "exists now, PAUSED: campaign", "exists now, PAUSED: ad ", "<redacted>"])
    run("read-back warns when an ad is not PAUSED", {"leak_active": 1}, [spec(), *ex], 4,
        ["WARNING: ad .* is not PAUSED"])
    def placements():
        t = json.loads(posts("adsets")[0]["targeting"])
        c = posts("campaigns")[0]
        bad = [] if t["publisher_platforms"] == ["facebook"] else ["instagram placement without identity"]
        bad += [] if c["is_adset_budget_sharing_enabled"] == "false" else ["budget sharing not off"]
        bad += [] if posts("adsets")[0]["lifetime_budget"] == "2000" else ["budget not in minor units"]
        bad += [] if all(b["status"] == "PAUSED" for k, b in STATE["posts"] if "status" in b) else ["not PAUSED"]
        bad += [] if "{adset} plans" in posts("adcreatives")[0]["object_story_spec"] else ["copy was rewritten"]
        return bad
    run("execute creates PAUSED, Facebook only", {}, [spec(lambda s: s["ads"][0].update(description="{adset} plans")), *ex], 0,
        ["configured=PAUSED effective=PAUSED", "lifetime_budget=2000", "link=", "All objects are PAUSED"],
        check=placements)
    def housing():
        c = posts("campaigns")[0]
        ok = json.loads(c["special_ad_categories"]) == ["HOUSING"] and json.loads(c["special_ad_category_country"]) == ["CA"]
        return [] if ok else ["special category not sent"]
    run("sends HOUSING with its country", {}, [spec(lambda s: (s["campaign"].update(
        special_ad_categories=["HOUSING"], special_ad_category_country=["CA"]), s["ad_set"].update(age_min=18))),
        *ex], 0, check=housing)
    def insta():
        t = json.loads(posts("adsets")[0]["targeting"])
        oss = json.loads(posts("adcreatives")[0]["object_story_spec"])
        ok = "instagram" in t["publisher_platforms"] and oss.get("instagram_user_id") == "444"
        return [] if ok else ["instagram identity not used"]
    run("adds Instagram only with an identity", {}, [spec(), *ex, "--instagram-user-id", "444"], 0, check=insta)
    srv.shutdown()
    if os.environ.get("AD_LAUNCH_TRANSCRIPT"):
        Path(os.environ["AD_LAUNCH_TRANSCRIPT"]).write_text("".join(log).lstrip() + "\n")
    print(f"{'PASS' if not fails else 'FAIL'}: {len(fails)} problem(s)")
    return 1 if fails else 0
if __name__ == "__main__":
    sys.exit(main())
