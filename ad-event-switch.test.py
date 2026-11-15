#!/usr/bin/env python3
"""E2E: real ad-event-switch against a fake Graph API server. No Meta account is touched.

Ways a switch can fail, written before the tool. Each one is a case below:
 1. A dry run writes something.
 2. --execute alone activates an object, or touches the original.
 3. --activate leaves the original running, or the copy has the old event.
 4. A minimum budget over --max-extra-cents is accepted, or one within it is not used.
 5. A rerun creates a second copy.
 6. A rate limit (17 / 2446079) is not retried, or another error is retried.
 7. The token shows in output or in a URL.
 8. An ad create fails midway: the original is paused, or the created objects are not listed.
 9. A paused ad set, or an ad set with another event, is copied.
Set AD_EVENT_SWITCH_TRANSCRIPT=<file> to keep the transcript as the artifact.
"""
import json, os, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
TOOL = Path(__file__).with_name("ad-event-switch")
TOKEN = "EAAB-fake-token-0123456789"
STATE = {}
def adset(i, name, event="ADD_TO_CART", status="ACTIVE", remaining="641"):
    return {"id": i, "name": name, "effective_status": status, "status": status, "campaign_id": "c" + i,
            "lifetime_budget": "1000", "budget_remaining": remaining, "daily_budget": "0", "end_time": "2026-11-20T22:00:00-0700",
            "billing_event": "IMPRESSIONS", "optimization_goal": "OFFSITE_CONVERSIONS", "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "targeting": {"age_min": 25}, "destination_type": "WEBSITE", "pacing_type": ["standard"],
            "attribution_spec": [{"event_type": "CLICK_THROUGH", "window_days": 7}],
            "promoted_object": {"pixel_id": "p1", "custom_event_type": event}}
def reset(**mode):
    STATE.clear()
    STATE.update(mode=mode, posts=[], paths=[], headers=[], n=500, rl=0, min_budget=mode.get("min_budget"),
                 sets={"1": adset("1", "A $29"), "2": adset("2", "B paused", status="PAUSED"), "3": adset("3", "C lead", event="LEAD")},
                 ads={"1": [{"id": "a1", "name": "ad one", "effective_status": "ACTIVE", "creative": {"id": "cr1"}},
                            {"id": "a2", "name": "ad two", "effective_status": "ACTIVE", "creative": {"id": "cr2"}},
                            {"id": "a3", "name": "ad off", "effective_status": "PAUSED", "creative": {"id": "cr3"}}]})
class Fake(BaseHTTPRequestHandler):
    log_message = lambda *a: None
    def send(self, code, body):
        self.send_response(code), self.end_headers(), self.wfile.write(json.dumps(body).encode())
    def err(self, code, sub=None, msg="error"):
        self.send(400, {"error": {"code": code, "error_subcode": sub, "message": msg, "type": "OAuthException"}})
    def do_GET(self):
        u = urlparse(self.path)
        STATE["paths"].append(self.path), STATE["headers"].append(self.headers.get("Authorization"))
        parts = u.path.strip("/").split("/")[1:]
        if parts[-1] == "adsets":
            return self.send(200, {"data": list(STATE["sets"].values())})
        if parts[-1] == "ads":
            return self.send(200, {"data": STATE["ads"].get(parts[0], [])})
        return self.send(200, STATE["sets"].get(parts[0], {}))
    def do_POST(self):
        u = urlparse(self.path)
        body = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()).items()}
        STATE["posts"].append((u.path, body)), STATE["headers"].append(self.headers.get("Authorization"))
        mode, parts = STATE["mode"], u.path.strip("/").split("/")[1:]
        if mode.get("rate_limit") and STATE["rl"] < mode["rate_limit"]:
            STATE["rl"] += 1
            return self.err(17, 2446079, "User request limit reached")
        if mode.get("other_error") and parts[-1] == "adsets":
            return self.err(100, 1, "Invalid parameter " + TOKEN)
        if parts[-1] == "adsets":
            floor = STATE["min_budget"]
            if floor and int(body["lifetime_budget"]) < floor:
                return self.err(100, 1, f"Your ad set budget must be more than CA${(floor - 1) / 100:.2f} or your ads may not deliver.")
            STATE["n"] += 1
            nid = str(STATE["n"])
            STATE["sets"][nid] = {**adset(nid, body["name"], status=body["status"], event=json.loads(body["promoted_object"])["custom_event_type"]),
                                  "budget_remaining": body["lifetime_budget"], "lifetime_budget": body["lifetime_budget"]}
            return self.send(200, {"id": nid})
        if parts[-1] == "ads":
            if mode.get("fail_ad") and any(p[0].endswith("/ads") for p in STATE["posts"][:-1]):
                return self.err(100, 2, "creative rejected")
            STATE["n"] += 1
            return self.send(200, {"id": "ad" + str(STATE["n"])})
        if len(parts) == 1 and "status" in body:
            if parts[0] in STATE["sets"]:
                STATE["sets"][parts[0]]["status"] = STATE["sets"][parts[0]]["effective_status"] = body["status"]
            return self.send(200, {"success": True})
        return self.err(100, None, "unexpected " + u.path)
def run(args, **mode):
    reset(**mode)
    if mode.get("seed"):
        mode["seed"]()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as d:
        env_file = Path(d, "meta.env")
        env_file.write_text(f"META_MARKETING_TOKEN={TOKEN}\n")
        env = {**os.environ, "AD_EVENT_SWITCH_GRAPH_URL": f"http://127.0.0.1:{server.server_port}", "AD_EVENT_SWITCH_SLEEP_SCALE": "0"}
        p = subprocess.run([sys.executable, "-I", str(TOOL), "--ad-account-id", "1", "--env-file", str(env_file),
                            "--from-event", "ADD_TO_CART", "--to-event", "INITIATED_CHECKOUT", *args],
                           capture_output=True, text=True, env=env, timeout=60)
    server.shutdown()
    out = p.stdout + p.stderr
    TRANSCRIPT.append(f"$ ad-event-switch {' '.join(args)} (mode={mode})\n{out}exit={p.returncode}\n")
    return p.returncode, out
TRANSCRIPT, FAILED = [], []
def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if not ok and detail else ""))
    if not ok:
        FAILED.append(name)
writes = lambda: [p for p in STATE["posts"]]
statuses = lambda: [b.get("status") for _, b in STATE["posts"] if "status" in b]

code, out = run([])
check("1 dry run exits 0 and writes nothing", code == 0 and writes() == [], out)
check("1 dry run names the ad set and the budget", "A $29" in out and "641" in out, out)
check("9 dry run ignores the paused and the other-event ad sets", "B paused" not in out and "C lead" not in out, out)

code, out = run(["--execute"])
copy = [s for s in STATE["sets"].values() if s["name"].endswith("[INITIATED_CHECKOUT]")]
creates = [(p, b) for p, b in STATE["posts"] if p.endswith("/adsets") or p.endswith("/ads")]
check("2 --execute makes one PAUSED copy and two PAUSED ads", code == 0 and len(copy) == 1 and len(creates) == 3 and all(b["status"] == "PAUSED" for _, b in creates), out)
check("2 --execute never writes ACTIVE and never touches the original", "ACTIVE" not in statuses() and STATE["sets"]["1"]["status"] == "ACTIVE" and not any(p.endswith("/1") for p, _ in STATE["posts"]), out)
check("3 copy keeps the budget remaining and the new event", copy and copy[0]["lifetime_budget"] == "641" and copy[0]["promoted_object"]["custom_event_type"] == "INITIATED_CHECKOUT", out)
check("3 ads keep their creative id and skip the paused ad", sorted(json.loads(b["creative"])["creative_id"] for p, b in STATE["posts"] if p.endswith("/ads")) == ["cr1", "cr2"], out)

code, out = run(["--execute", "--activate"])
copy = [s for s in STATE["sets"].values() if s["name"].endswith("[INITIATED_CHECKOUT]")]
check("3 --activate activates the copy and pauses the original", code == 0 and copy and copy[0]["status"] == "ACTIVE" and STATE["sets"]["1"]["status"] == "PAUSED", out)
check("3 --activate activates the ads", statuses().count("ACTIVE") == 3, statuses())
check("7 the token is in a header and never in a URL or the output", TOKEN not in "".join(STATE["paths"]) and TOKEN not in out and all(h == f"Bearer {TOKEN}" for h in STATE["headers"]), out)

code, out = run(["--execute"], min_budget=760)
copy = [s for s in STATE["sets"].values() if s["name"].endswith("[INITIATED_CHECKOUT]")]
check("4 a minimum within the cap is used, and the rise is reported", code == 0 and copy and copy[0]["lifetime_budget"] == "760" and "119" in out, out)
code, out = run(["--execute"], min_budget=900)
check("4 a minimum over the cap is refused and nothing is created", code == 2 and len(STATE["sets"]) == 3 and not any(p.endswith("/ads") for p, _ in STATE["posts"]) and "max-extra-cents" in out, out)
code, out = run(["--execute", "--max-extra-cents", "400"], min_budget=900)
check("4 a raised cap lets the same minimum through", code == 0 and any(s["name"].endswith("[INITIATED_CHECKOUT]") and s["lifetime_budget"] == "900" for s in STATE["sets"].values()), out)

code, out = run(["--execute"], seed=lambda: STATE["sets"].update({"9": adset("9", "A $29 [INITIATED_CHECKOUT]", event="INITIATED_CHECKOUT")}))
check("5 a rerun creates nothing and says it skipped", code == 0 and "skip" in out.lower() and len(STATE["sets"]) == 4 and not STATE["posts"], out)

code, out = run(["--execute"], rate_limit=2)
check("6 a rate limit is retried and then succeeds", code == 0 and out.count("rate limited") == 2 and any(s["name"].endswith("[INITIATED_CHECKOUT]") for s in STATE["sets"].values()), out)
code, out = run(["--execute"], rate_limit=9)
check("6 a rate limit that stays is given up after three retries", code == 3 and out.count("rate limited") == 3, out)
code, out = run(["--execute"], other_error=True)
check("6/7 another error is not retried, and its token text is scrubbed", code == 3 and out.count("rate limited") == 0 and TOKEN not in out and len([p for p, _ in STATE["posts"] if p.endswith("/adsets")]) == 1, out)

code, out = run(["--execute", "--activate"], fail_ad=True)
check("8 a failed ad create exits 3, lists what exists and leaves the original running", code == 3 and "created" in out and STATE["sets"]["1"]["status"] == "ACTIVE" and "ACTIVE" not in statuses(), out)

if os.environ.get("AD_EVENT_SWITCH_TRANSCRIPT"):
    Path(os.environ["AD_EVENT_SWITCH_TRANSCRIPT"]).write_text("\n".join(TRANSCRIPT).replace(TOKEN, "<token>"))
print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all cases passed'}")
sys.exit(1 if FAILED else 0)
