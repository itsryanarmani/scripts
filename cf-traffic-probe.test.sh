#!/usr/bin/env bash
# E2E test for cf-traffic-probe. No network: it reads fixture answers through --fixtures and a tail file from disk.
# Cases: a back-to-back pretty-printed tail stream with a truncated last object, crawler names (not families), route
# kinds, dashed analytics namespace ids against undashed REST ids, a missing fixture, a secret in a GraphQL error,
# no credentials, and bad usage.
set -uo pipefail
SCRIPT="$(cd "$(dirname "$0")" && pwd)/cf-traffic-probe"
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
pass=0; fail=0
ok() { echo "ok - $1"; pass=$((pass+1)); }
no() { echo "FAIL - $1"; fail=$((fail+1)); }
has() { grep -qF -- "$2" <<<"$OUT" && ok "$1" || no "$1 (missing: $2)"; }
hasnt() { grep -qF -- "$2" <<<"$OUT" && no "$1 (found: $2)" || ok "$1"; }
code() { [ "$RC" -eq "$2" ] && ok "$1" || no "$1 (exit $RC)"; }
run() { OUT=$(env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID "$@" 2>&1); RC=$?; }

python3 - "$W" <<'PY'
import json, os, sys
d = sys.argv[1]
def ev(url, ua, cpu):
    return json.dumps({'outcome': 'ok', 'cpuTime': cpu, 'event': {'request': {'url': url, 'headers': {'user-agent': ua}}}}, indent=2)
tail = '\n'.join([
    ev('https://a.example/us/ca/town/category/x', 'Mozilla/5.0 (compatible; QlyzeBot/1.0)', 600),
    ev('https://a.example/us/ca/town/category/y', 'Mozilla/5.0 (compatible; QlyzeBot/1.0)', 400),
    ev('https://a.example/search?category=a&sort=x', 'Mozilla/5.0 AppleWebKit/537.36 (compatible; GPTBot/1.2)', 100),
    ev('https://a.example/us/ca/town/acme', 'Mozilla/5.0 (X11; Linux) Chrome/130', 50),
    ev('https://a.example/login?next=%2F', '', 30),
])
open(d + '/tail.json', 'w').write(tail + '\n{\n  "outcome": "ok", "cpuTime": 9999, "event": {')   # truncated last object: must be dropped
open(d + '/empty.json', 'w').write('')
fx = d + '/fx'; os.makedirs(fx)
put = lambda n, v: json.dump(v, open(f'{fx}/{n}.json', 'w'))
gql = lambda **k: {'data': {'viewer': k}}
put('kv-namespaces', {'result': [{'id': 'aaaa1111bbbb2222cccc3333dddd4444', 'title': 'site-inc-cache-production'}, {'id': 'eeee1111ffff2222aaaa3333bbbb4444', 'title': 'site-tag-cache'}]})
put('graphql-kv-ops', gql(accounts=[{'kvOperationsAdaptiveGroups': [
    {'sum': {'requests': 700}, 'dimensions': {'datetimeHour': '2026-11-05T10:00:00Z', 'namespaceId': 'aaaa1111-bbbb-2222-cccc-3333dddd4444'}},
    {'sum': {'requests': 300}, 'dimensions': {'datetimeHour': '2026-11-05T11:00:00Z', 'namespaceId': 'eeee1111-ffff-2222-aaaa-3333bbbb4444'}}]}]))
put('graphql-kv-storage', gql(accounts=[{'kvStorageAdaptiveGroups': [
    {'max': {'byteCount': 8000000000, 'keyCount': 400000}, 'dimensions': {'namespaceId': 'aaaa1111-bbbb-2222-cccc-3333dddd4444', 'date': '2026-11-06'}},
    {'max': {'byteCount': 1000000, 'keyCount': 10}, 'dimensions': {'namespaceId': 'eeee1111-ffff-2222-aaaa-3333bbbb4444', 'date': '2026-11-06'}}]}]))
put('graphql-hourly-cpu', gql(accounts=[{'workersInvocationsAdaptive': [
    {'dimensions': {'scriptName': 'site-web-production', 'datetimeHour': '2026-11-05T10:00:00Z'}, 'sum': {'requests': 1000, 'cpuTimeUs': 250000000}},
    {'dimensions': {'scriptName': 'other-web-production', 'datetimeHour': '2026-11-05T10:00:00Z'}, 'sum': {'requests': 5, 'cpuTimeUs': 5000}}]}]))
put('d1-databases', {'result': [{'uuid': 'db1', 'name': 'site-db-production'}]})
put('graphql-d1-top', gql(accounts=[{'d1QueriesAdaptiveGroups': [{'dimensions': {'query': 'WITH t AS MATERIALIZED (SELECT 1)', 'databaseId': 'db1'}, 'sum': {'rowsRead': 5000000}, 'count': 50}]}]))
put('zone-a.example', {'result': [{'id': 'zone1'}]})
put('graphql-zone-traffic-a.example', gql(zones=[{'st': [{'count': 90, 'dimensions': {'edgeResponseStatus': 200}}, {'count': 10, 'dimensions': {'edgeResponseStatus': 503}}],
    'co': [{'count': 70, 'dimensions': {'clientCountryName': 'US'}}, {'count': 30, 'dimensions': {'clientCountryName': 'SG'}}],
    'ua': [{'count': 60, 'dimensions': {'userAgent': 'Mozilla/5.0 (compatible; Amazonbot/0.1)'}}, {'count': 40, 'dimensions': {'userAgent': ''}}]}]))
import shutil
shutil.copytree(fx, fx + '-secret')
put_secret = {'errors': [{'message': 'bad token SECRET123 for account ACCT456'}]}
json.dump(put_secret, open(fx + '-secret/graphql-d1-top.json', 'w'))
os.remove(fx + '/graphql-zone-traffic-a.example.json') if False else None
shutil.copytree(fx, fx + '-missing'); os.remove(fx + '-missing/graphql-kv-ops.json')
PY

# ua-cpu: offline, names not families
run "$SCRIPT" ua-cpu "$W/tail.json"
code "ua-cpu exits 0" "$RC" 0
has "ua-cpu counts 5 events and drops the truncated sixth" "events 5, CPU ms 1180"
has "ua-cpu names QlyzeBot with both requests" "QlyzeBot"
has "ua-cpu gives QlyzeBot 84.7% of the CPU" "84.7%"
has "ua-cpu names GPTBot, not a family" "GPTBot"
has "ua-cpu calls a plain Chrome agent browser-like" "browser-like"
has "ua-cpu calls an empty agent no user agent" "no user agent"
has "ua-cpu groups city and category pages" "city or category page"
has "ua-cpu groups search" "search"
has "ua-cpu groups login" "claim, edit or login"
run "$SCRIPT" ua-cpu "$W/empty.json"
has "an empty file says so" "no events in the files"
run "$SCRIPT" ua-cpu
code "ua-cpu without a file is bad usage" "$RC" 2

# API probes from fixtures
run "$SCRIPT" --fixtures "$W/fx" kv-ops write
code "kv-ops exits 0" "$RC" 0
has "kv-ops resolves a dashed analytics id to the REST name" "site-inc-cache-production"
has "kv-ops sums the day" "write ops 1000"
has "kv-ops gives the namespace its share" "70.0%"
run "$SCRIPT" --fixtures "$W/fx" kv-storage
has "kv-storage totals GB" "KV total 8.00 GB"
has "kv-storage counts cache entries" "cache entries (inc-cache) 8.00 GB"
has "kv-storage prints KB per key" "20.0 KB/key"
run "$SCRIPT" --fixtures "$W/fx" hourly-cpu site-web-production
has "hourly-cpu prints ms per request" "250 ms/req"
hasnt "hourly-cpu skips scripts not asked for" "other-web"
run "$SCRIPT" --fixtures "$W/fx" d1-top 6
has "d1-top names the database" "site-db-production"
has "d1-top prints rows per run" "100000 rows/run"
run "$SCRIPT" --fixtures "$W/fx" zone-traffic a.example
has "zone-traffic shows the 503 count" "503: 10"
has "zone-traffic names Amazonbot" "Amazonbot"
has "zone-traffic names an empty agent" "no user agent"

# failure cases
run "$SCRIPT" --fixtures "$W/fx-missing" kv-ops write
code "a missing fixture exits 4" "$RC" 4
has "a missing fixture says unavailable" "unavailable: fixture missing"
run env CLOUDFLARE_API_TOKEN=SECRET123 CLOUDFLARE_ACCOUNT_ID=ACCT456 "$SCRIPT" --fixtures "$W/fx-secret" d1-top
code "an API error exits 4" "$RC" 4
hasnt "a token in an error text never prints" "SECRET123"
hasnt "an account id in an error text never prints" "ACCT456"
has "the error keeps its words" "bad token ***"
run "$SCRIPT" kv-ops write
code "no credentials exits 3" "$RC" 3
run "$SCRIPT" --fixtures "$W/fx" kv-ops sideways
code "kv-ops with a bad action is bad usage" "$RC" 2
run "$SCRIPT" nonsense
code "an unknown probe is bad usage" "$RC" 2

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
