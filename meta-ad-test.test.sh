#!/usr/bin/env bash
# meta-ad-test.test.sh — no network, no Meta account.
# The unsafe plans come first: each must be refused before anything is sent.
set -u
PASS=0; FAIL=0
ok(){ echo "  ok   $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL $1"; FAIL=$((FAIL+1)); }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
HERE="$(cd "$(dirname "$0")" && pwd)"

plan() { # plan <jq-free python edit> ; writes $TMP/plan.json from the valid base with a mutation applied
  python3 - "$1" > "$TMP/plan.json" <<'PY'
import json,sys
p={"campaign":{"name":"t","slug":"t_2601","lifetimeBudget":100,"flightDays":7,"pageId":"1","baseUrl":"https://example.test",
 "geo":{"countries":["CA"]},"age":[25,64],"placements":{"facebook":["feed"]}},
 "utmTemplate":"utm_source=meta&utm_content={ad}&utm_term={persona}",
 "ads":[{"id":"a-1","persona":"p","landing":"/lp/p","creative":"a.png","headline":"h","primaryText":"t","hypothesis":"h","killGate":"k"}]}
exec(sys.argv[1])
print(json.dumps(p))
PY
}

refused() { # refused <name> <mutation> <expected text>
  plan "$2"
  out="$(META_MARKETING_TOKEN=SECRETTOKEN node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" 2>&1)"; rc=$?
  if [ $rc -ne 0 ] && echo "$out" | grep -q "$3"; then ok "refuses $1"; else no "refuses $1 (rc=$rc)"; echo "$out" | head -3; fi
}

refused "a plan with no geo"        'del p["campaign"]["geo"]' "geo is required"
refused "a plan with no budget cap"  'del p["campaign"]["lifetimeBudget"]' "lifetimeBudget"
refused "a plan with no flight"      'del p["campaign"]["flightDays"]' "flightDays"
refused "an ad with no hypothesis"   'del p["ads"][0]["hypothesis"]' "hypothesis"
refused "an ad with no kill gate"    'del p["ads"][0]["killGate"]' "kill gate"
refused "a UTM template without the ad id" 'p["utmTemplate"]="utm_source=meta"' "utm_content"

plan 'pass'
out="$(META_MARKETING_TOKEN=SECRETTOKEN node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" 2>&1)"; rc=$?
[ $rc -eq 0 ] && ok "dry run accepts a valid plan" || { no "dry run accepts a valid plan"; echo "$out" | head -3; }
echo "$out" | grep -q 'utm_content=a_1' && ok "builds the UTM from the ad id" || no "builds the UTM from the ad id"
echo "$out" | grep -q 'example.test/lp/p?' && ok "joins the base URL and landing path" || no "joins the base URL and landing path"
echo "$out" | grep -q SECRETTOKEN && no "dry run prints the token" || ok "dry run never prints the token"

# Going live needs the approval flag, and needs it before any network call.
echo '{}' > "$TMP/created.json"
out="$(META_MARKETING_TOKEN=SECRETTOKEN META_ADS_AD_ACCOUNT_ID=1 node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --activate 2>&1)"; rc=$?
[ $rc -ne 0 ] && echo "$out" | grep -q I_APPROVE_SPEND && ok "activate refuses without I_APPROVE_SPEND" || no "activate refuses without I_APPROVE_SPEND"

# --report. The failure modes first: a report must never crash on missing data, never pause on a guess,
# and never touch the network when it reads a saved fixture.
report() { # report <name> <plan-mutation> <insights-json> <expected text> [extra flags]
  name="$1"; mut="$2"; ins="$3"; want="$4"; shift 4
  plan "p['ads'][0]['expected']={'ctr':'0.6-1.0%','cpc':'2.70-4.50'}; $mut"
  echo '{"campaign":"C","adset":"S","ads":{"a-1":"AD1"}}' > "$TMP/created.json"
  echo "$ins" > "$TMP/insights.json"
  out="$(META_MARKETING_TOKEN=SECRETTOKEN node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --report --insights "$TMP/insights.json" "$@" 2>&1)"; rc=$?
  if echo "$out" | grep -q "$want"; then ok "report: $name"; else no "report: $name (rc=$rc)"; echo "$out" | head -6; fi
  echo "$out" | grep -q SECRETTOKEN && no "report prints the token ($name)"
}
GATE='p["ads"][0]["killGate"]="Stop this ad if it has spent CAD 12 with fewer than 2 link clicks."'
FIX_NONE='{"adset":{"effective_status":"ACTIVE","lifetime_budget":"10000","budget_remaining":"10000"},"ads":{"AD1":{"effective_status":"ACTIVE"}},"insights":[]}'
FIX_DEAD='{"currency":"CAD","adset":{"effective_status":"ACTIVE","lifetime_budget":"10000","budget_remaining":"9000"},"ads":{"AD1":{"effective_status":"ACTIVE"}},"insights":[{"ad_id":"AD1","spend":"13.00","impressions":"2000","inline_link_clicks":"1","inline_link_click_ctr":"0.05","cost_per_inline_link_click":"13.00"}]}'
FIX_EARLY='{"adset":{"effective_status":"ACTIVE","lifetime_budget":"10000","budget_remaining":"9990"},"ads":{"AD1":{"effective_status":"ACTIVE"}},"insights":[{"ad_id":"AD1","spend":"1.00","impressions":"300","inline_link_clicks":"0","inline_link_click_ctr":"0","cost_per_inline_link_click":"0"}]}'
FIX_GOOD='{"adset":{"effective_status":"ACTIVE","lifetime_budget":"10000","budget_remaining":"9000"},"ads":{"AD1":{"effective_status":"ACTIVE"}},"insights":[{"ad_id":"AD1","spend":"6.00","impressions":"1500","inline_link_clicks":"20","inline_link_click_ctr":"1.33","cost_per_inline_link_click":"0.30"}]}'

rm -f "$TMP/created.json"
plan 'pass'
out="$(META_MARKETING_TOKEN=SECRETTOKEN node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --report 2>&1)"; rc=$?
[ $rc -ne 0 ] && echo "$out" | grep -q "created.json" && ok "report refuses with no created.json" || no "report refuses with no created.json"

report "an ad with no insights row is WAIT, not a crash"  "pass" "$FIX_NONE"  "WAIT"
report "spend at the gate with too few clicks is KILL"     "$GATE" "$FIX_DEAD"  "KILL"
report "an unreadable kill gate is flagged, never KILL"    "pass"  "$FIX_DEAD"  "gate unreadable"
report "low CTR on 300 impressions is WAIT, not WATCH"     "$GATE" "$FIX_EARLY" "WAIT"
report "CTR above the expected range is LEADING"           "$GATE" "$FIX_GOOD"  "LEADING"
report "the hypothesis is printed with each ad"            "$GATE" "$FIX_GOOD"  "hypothesis: h"

# A gate is acted on only in its exact form, with a currency. A guess pauses the wrong ad.
GATE_NEG='p["ads"][0]["killGate"]="Do not stop this ad if it has spent CAD 12 with fewer than 2 link clicks."'
GATE_NOCUR='p["ads"][0]["killGate"]="Stop this ad if it has spent 12 with fewer than 2 link clicks."'
GATE_EXTRA='p["ads"][0]["killGate"]="Stop this ad if it has spent CAD 12 with fewer than 2 link clicks and a bad week."'
report "a negated gate is flagged, never KILL"            "$GATE_NEG"   "$FIX_DEAD" "gate unreadable"
report "a gate with no currency is flagged, never KILL"   "$GATE_NOCUR" "$FIX_DEAD" "gate unreadable"
report "a gate with extra conditions is flagged"          "$GATE_EXTRA" "$FIX_DEAD" "gate unreadable"
report "a gate in the wrong currency is flagged"          "p['ads'][0]['killGate']='Stop this ad if it has spent USD 12 with fewer than 2 link clicks.'" '{"currency":"CAD","adset":{"effective_status":"ACTIVE"},"ads":{"AD1":{"effective_status":"ACTIVE"}},"insights":[{"ad_id":"AD1","spend":"13.00","impressions":"2000","inline_link_clicks":"1","inline_link_click_ctr":"0.05","cost_per_inline_link_click":"13.00"}]}' "gate unreadable"
# The markdown file must not carry a token even when the plan text does.
plan "p['ads'][0]['hypothesis']='leaks SECRETTOKEN'; $GATE"
echo '{"campaign":"C","adset":"S","ads":{"a-1":"AD1"}}' > "$TMP/created.json"; echo "$FIX_GOOD" > "$TMP/insights.json"
META_MARKETING_TOKEN=SECRETTOKEN node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --report --insights "$TMP/insights.json" --md "$TMP/r.md" >/dev/null 2>&1
grep -q SECRETTOKEN "$TMP/r.md" && no "markdown report leaks the token" || ok "markdown report never carries the token"

plan "p['ads'][0]['expected']={'ctr':'0.6-1.0%'}; $GATE"
echo '{"campaign":"C","adset":"S","ads":{"a-1":"AD1"}}' > "$TMP/created.json"; echo "$FIX_DEAD" > "$TMP/insights.json"
out="$(META_MARKETING_TOKEN=SECRETTOKEN META_ADS_AD_ACCOUNT_ID=1 node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --report --insights "$TMP/insights.json" --apply-kill-gate 2>&1)"; rc=$?
[ $rc -ne 0 ] && echo "$out" | grep -qi "saved fixture" && ok "apply-kill-gate refuses to act on a saved fixture" || no "apply-kill-gate refuses to act on a saved fixture"

# --add and --retire. Adding an ad spends money and retiring one stops a live ad, so every refusal comes before any network call.
addrun() { # addrun <name> <want> <extra env...> -- <flags...>
  name="$1"; want="$2"; shift 2
  out="$(env META_MARKETING_TOKEN=SECRETTOKEN META_ADS_AD_ACCOUNT_ID=1 "$@" 2>&1)"; rc=$?
  if echo "$out" | grep -qi -- "$want"; then ok "$name"; else no "$name (rc=$rc)"; echo "$out" | head -4; fi
  echo "$out" | grep -q SECRETTOKEN && no "$name prints the token"
}
plan 'pass'
rm -f "$TMP/created.json"
addrun "add refuses with no created.json" "created.json" I_APPROVE_SPEND=yes node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --add
echo '{"campaign":"C","adset":"S","ads":{"a-1":"AD1"}}' > "$TMP/created.json"
plan "p['ads'].append(dict(p['ads'][0], id='a-2', creative='missing.png'))"
addrun "add refuses without the spend approval" "I_APPROVE_SPEND" node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --add
addrun "add refuses a missing creative file, before any call" "creative file" I_APPROVE_SPEND=yes node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --add
plan 'pass'
addrun "add with nothing new says so and sends nothing" "nothing to add" I_APPROVE_SPEND=yes node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --add
addrun "retire refuses an unknown ad id" "unknown ad id" node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --retire nope --after a-1
addrun "retire refuses with no replacement named" "--after" node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --retire a-1

echo '{"campaign":"C","adset":"S","ads":{"a-1":"AD1"},"retired":{"a-0":"AD0"}}' > "$TMP/created.json"
addrun "retire refuses an ad that is also its own replacement" "both" node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --retire a-1 --after a-1
plan "p['ads'].append(dict(p['ads'][0], id='a-0'))"
addrun "add refuses to bring back a retired ad" "retired" I_APPROVE_SPEND=yes node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --add

# Audience settings that Meta quietly ignores must be refused or made visible.
refused "an age max of 65 (Meta reads it as 65 and older)" 'p["campaign"]["age"]=[25,65]' "65 and older"
refused "job-title hints with the automatic audience off" 'p["campaign"]["targetingSuggestions"]={"1":"Lawyer"}' "targetingSuggestions"
plan 'pass'
out="$(META_MARKETING_TOKEN=SECRETTOKEN node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" 2>&1)"
echo "$out" | grep -q '"advantage_audience":0' && ok "the automatic audience is off unless the plan turns it on" || no "the automatic audience is off unless the plan turns it on"
plan 'p["campaign"]["advantageAudience"]=True; p["campaign"]["targetingSuggestions"]={"1":"Lawyer"}'
out="$(META_MARKETING_TOKEN=SECRETTOKEN node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" 2>&1)"
echo "$out" | grep -q '"advantage_audience":1' && ok "advantageAudience true turns it on, and hints are then allowed" || no "advantageAudience true turns it on, and hints are then allowed"

# The report must show delivery outside the plan's ages, and stay quiet when there is none.
AGES_BAD='"ages":[{"age":"65+","impressions":"750","spend":"8.00","inline_link_clicks":"19"},{"age":"25-34","impressions":"100","spend":"1.00","inline_link_clicks":"1"},{"age":"35-44","impressions":"150","spend":"1.50","inline_link_clicks":"2"}]'
AGES_OK='"ages":[{"age":"65+","impressions":"50","spend":"0.50","inline_link_clicks":"1"},{"age":"25-34","impressions":"450","spend":"4.50","inline_link_clicks":"5"},{"age":"45-54","impressions":"500","spend":"5.00","inline_link_clicks":"6"}]'
report "the report warns when most delivery is outside the plan ages" "$GATE" "{\"currency\":\"CAD\",\"adset\":{\"effective_status\":\"ACTIVE\"},\"ads\":{\"AD1\":{\"effective_status\":\"ACTIVE\"}},\"insights\":[],$AGES_BAD}" "WARNING.*outside the plan's age range"
report "the report shows the share outside the plan ages" "$GATE" "{\"currency\":\"CAD\",\"adset\":{\"effective_status\":\"ACTIVE\"},\"ads\":{\"AD1\":{\"effective_status\":\"ACTIVE\"}},\"insights\":[],$AGES_BAD}" "75%"
plan "$GATE"
echo '{"campaign":"C","adset":"S","ads":{"a-1":"AD1"}}' > "$TMP/created.json"
echo "{\"currency\":\"CAD\",\"adset\":{\"effective_status\":\"ACTIVE\"},\"ads\":{\"AD1\":{\"effective_status\":\"ACTIVE\"}},\"insights\":[],$AGES_OK}" > "$TMP/insights.json"
out="$(META_MARKETING_TOKEN=SECRETTOKEN node "$HERE/meta-ad-test.mjs" "$TMP/plan.json" --report --insights "$TMP/insights.json" 2>&1)"
echo "$out" | grep -q "WARNING" && no "the report stays quiet when delivery is inside the plan ages" || ok "the report stays quiet when delivery is inside the plan ages"
echo "$out" | grep -q "age check" && ok "the report still prints the age check line" || no "the report still prints the age check line"

# The renderer needs a browser library. Check the spec guards only when it is present.
if node -e "require.resolve('playwright')" 2>/dev/null; then
  echo '{"brand":{"name":"B","url":"b.test"},"ads":[]}' > "$TMP/spec.json"
  node "$HERE/ad-creatives-render.mjs" "$TMP/spec.json" "$TMP/out" >/dev/null 2>&1 && no "render refuses a brand with no cta" || ok "render refuses a brand with no cta"
else
  echo "  skip renderer checks (playwright not installed)"
fi

echo "$PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
