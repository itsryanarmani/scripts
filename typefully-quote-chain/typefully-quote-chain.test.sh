#!/usr/bin/env bash
# Tests for typefully-quote-chain against a local fake Typefully API.
# Each case is a way the chain could post wrong: scheduled before its quote,
# a platform or media dropped, the quote on the wrong platform, a schedule in
# the past, a later link run early, a crash on an API error.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
tool="$here/typefully-quote-chain"
tmp=$(mktemp -d); trap 'kill $srv 2>/dev/null; rm -rf "$tmp"' EXIT
port=$((20000 + RANDOM % 20000))
fails=0
export TYPEFULLY_API_KEY=test TYPEFULLY_API_BASE="http://127.0.0.1:$port" TQC_HOME="$tmp/home" TQC_NO_LAUNCHCTL=1
mkdir -p "$TQC_HOME"
echo '{}' >"$tmp/state.json"
python3 "$here/fake_typefully.py" "$port" "$tmp/state.json" & srv=$!
for _ in $(seq 50); do curl -s "http://127.0.0.1:$port/" >/dev/null 2>&1 && break; sleep 0.1; done

ok()   { echo "ok   $1"; }
fail() { echo "FAIL $1"; fails=$((fails + 1)); }
q()    { python3 -c "import json,sys;s=json.load(open('$tmp/state.json'));print(eval(sys.argv[1]))" "$1"; }

# draft <id> <status> [published_url] [published_at]
seed() {
  python3 - "$tmp/state.json" "$@" <<'PY'
import json, sys
path, rows = sys.argv[1], sys.argv[2:]
s = {}
for r in rows:
    i, status, url, at = (r.split("|") + ["", ""])[:4]
    plat = lambda: {"enabled": True, "posts": [{"text": f"post {i}", "media_ids": [f"m{i}"]}]}
    s[i] = {"id": int(i), "status": status, "x_published_url": url or None, "published_at": at or None,
            "platforms": {"x": plat(), "linkedin": plat(), "bluesky": plat(), "threads": plat(), "mastodon": None}}
json.dump(s, open(path, "w"))
PY
}
chain() { echo "{\"social_set\": 1, \"gap_days\": 2, \"chain\": [$1]}" >"$TQC_HOME/chain.json"; }

# 1. The previous post is not live: the next draft is not touched.
chain "1, 2"; seed "1|scheduled" "2|draft"
out=$("$tool" run | tail -1)
[ "$out" = waiting ] && [ "$(q 's["2"]["status"]')" = draft ] && [ "$(q 's["2"].get("_patches",0)')" = 0 ] \
  && ok "waits, and leaves the next draft unscheduled, until the previous post is live" \
  || fail "scheduled a draft before the post it quotes was live ($out)"

# 2. The previous post is live: quote on X only, every platform kept, scheduled 2 days later.
soon=$(python3 -c 'import datetime as d;print((d.datetime.now(d.timezone.utc)).isoformat().replace("+00:00","Z"))')
seed "1|published|https://x.com/u/status/111|$soon" "2|draft"
"$tool" run >/dev/null
[ "$(q 's["2"]["platforms"]["x"]["posts"][0].get("quote_post_url")')" = "https://x.com/u/status/111" ] \
  && ok "sets the previous post's URL as the X quote" || fail "X quote not set"
[ "$(q 'sorted(k for k,v in s["2"]["platforms"].items() if v)')" = "['bluesky', 'linkedin', 'threads', 'x']" ] \
  && ok "keeps every enabled platform" || fail "dropped a platform: $(q 'sorted(k for k,v in s["2"]["platforms"].items() if v)')"
[ "$(q 'all(p["posts"][0]["text"]=="post 2" and p["posts"][0]["media_ids"]==["m2"] for p in s["2"]["platforms"].values() if p)')" = True ] \
  && ok "keeps each platform's text and media" || fail "changed text or media"
[ "$(q 'any("quote_post_url" in p["posts"][0] for k,p in s["2"]["platforms"].items() if p and k!="x")')" = False ] \
  && ok "puts the quote on X only" || fail "quote leaked to another platform"
[ "$(q 'round((__import__("datetime").datetime.fromisoformat(s["2"]["scheduled_date"].replace("Z","+00:00"))-__import__("datetime").datetime.fromisoformat(s["1"]["published_at"].replace("Z","+00:00"))).total_seconds()/86400,2)')" = 2.0 ] \
  && ok "schedules gap_days after the previous post" || fail "wrong schedule: $(q 's["2"]["scheduled_date"]')"

# 3. The previous post went live long ago: never schedule in the past.
seed "1|published|https://x.com/u/status/111|2020-01-01T00:00:00Z" "2|draft"
"$tool" run >/dev/null
[ "$(q '(__import__("datetime").datetime.fromisoformat(s["2"]["scheduled_date"].replace("Z","+00:00"))-__import__("datetime").datetime.now(__import__("datetime").timezone.utc)).total_seconds()>25*60')" = True ] \
  && ok "moves a schedule that would be in the past to at least 25 minutes ahead" || fail "scheduled in the past: $(q 's["2"]["scheduled_date"]')"

# 4. A link in the middle is scheduled but not live: the one after it waits.
chain "1, 2, 3"; seed "1|published|https://x.com/u/status/111|$soon" "2|scheduled" "3|draft"
out=$("$tool" run | tail -1)
[ "$out" = waiting ] && [ "$(q 's["3"]["status"]')" = draft ] \
  && ok "does not run a later link while an earlier one waits" || fail "ran a later link early ($out)"

# 5. An API error is logged, not fatal.
seed "1|published|x|$soon" "2|draft"; python3 -c "import json;p='$tmp/state.json';s=json.load(open(p));s['2']['_fail']=True;json.dump(s,open(p,'w'))"
"$tool" run >/dev/null; code=$?
[ $code = 0 ] && grep -q "error:" "$TQC_HOME/chain.log" \
  && ok "logs an API error and exits 0, so launchd runs it again" || fail "an API error crashed the job (exit $code)"

# 6. Every link done: reports complete.
chain "1, 2"; seed "1|published|https://x.com/u/status/111|$soon" "2|published|https://x.com/u/status/222|$soon"
[ "$("$tool" run | tail -1)" = complete ] && grep -q "chain complete" "$TQC_HOME/chain.log" \
  && ok "reports the chain complete when every link is done" || fail "did not report complete"

# 7. selftest re-sends a draft and finds it unchanged.
seed "1|draft"
"$tool" selftest 1 | grep -q unchanged && ok "selftest finds a re-sent draft unchanged" || fail "selftest"

[ $fails = 0 ] && echo "typefully-quote-chain: all tests passed" || { echo "typefully-quote-chain: $fails failed"; exit 1; }
