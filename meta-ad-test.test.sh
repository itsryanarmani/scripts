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
 "geo":{"countries":["CA"]},"age":[25,65],"placements":{"facebook":["feed"]}},
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

# The renderer needs a browser library. Check the spec guards only when it is present.
if node -e "require.resolve('playwright')" 2>/dev/null; then
  echo '{"brand":{"name":"B","url":"b.test"},"ads":[]}' > "$TMP/spec.json"
  node "$HERE/ad-creatives-render.mjs" "$TMP/spec.json" "$TMP/out" >/dev/null 2>&1 && no "render refuses a brand with no cta" || ok "render refuses a brand with no cta"
else
  echo "  skip renderer checks (playwright not installed)"
fi

echo "$PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
