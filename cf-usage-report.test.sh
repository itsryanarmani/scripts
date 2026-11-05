#!/usr/bin/env bash
# E2E test for cf-usage-report. No network: the tool reads fixture answers
# through --fixtures. Billing fixture: a normal day, the first day of a new
# billing period, and a partial day with no Workers CPU line.
set -uo pipefail
SCRIPT="$(cd "$(dirname "$0")" && pwd)/cf-usage-report"
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
d = sys.argv[1] + '/fx'; os.makedirs(d)
def put(name, v): json.dump(v, open(f'{d}/{name}.json', 'w'))
def gql(**k): return {'data': {'viewer': {'accounts': [k]}}}
def day(date, bps, items):
    return [{'ChargePeriodStart': date + 'T00:00:00Z', 'BillingPeriodStart': bps, 'ChargeDescription': n, 'BilledCost': c} for n, c in items]
put('billing', {'result':
    day('2026-10-31', '2026-10-01', [('D1 Rows Read', 10.0), ('D1 Rows Read', 2.5), ('Workers CPU ms', 4.0), ('KV Write Operations', 3.0),
        ('Workers Requests', 1.5), ('Containers vCPU', 0.5), ('Workers Logs events', 0.2), ('Queues operations', 0.1), ('R2 Class A', 0.05)])
    + day('2026-11-01', '2026-11-01', [('D1 Rows Read', 0.8), ('Workers CPU ms', 0.3), ('KV Write Operations', 0.2), ('Workers Requests', 0.1)])
    + day('2026-11-02', '2026-11-01', [('D1 Rows Read', 1.1), ('KV Write Operations', 0.2)])})
put('d1-databases', {'result': [{'uuid': f'db{i}', 'name': n} for i, n in enumerate(['alpha-prod', 'b', 'c', 'd', 'e', 'f', 'tiny-eta'])]})
put('graphql-d1-daily', gql(d1AnalyticsAdaptiveGroups=[{'dimensions': {'date': '2026-11-02'}, 'sum': {'rowsRead': 7000000, 'rowsWritten': 3000}}]))
put('graphql-d1-dbs', gql(d1AnalyticsAdaptiveGroups=[{'dimensions': {'databaseId': f'db{i}'}, 'sum': {'rowsRead': (7 - i) * 10**6, 'rowsWritten': 1}} for i in range(7)]))
put('kv-namespaces', {'result': [{'id': 'ns1', 'title': 'cache-ns'}, {'id': 'ns2', 'title': 'sessions-ns'}]})
h = lambda ns, t, n: {'dimensions': {'namespaceId': ns, 'datetimeHour': t}, 'sum': {'requests': n}}
put('graphql-kv', gql(kvOperationsAdaptiveGroups=[h('ns1', '2026-11-02T01:00:00Z', 600), h('ns1', '2026-11-02T02:00:00Z', 400), h('ns2', '2026-11-02T01:00:00Z', 50)]))
# A: 10000 ms CPU, p50 2 ms x 1000 req -> tail 8000. B: 1000 ms, p50 1.5 ms x 500 req -> tail 250. Share 8250/11000.
w = lambda s, r, c, p50, p99: {'dimensions': {'scriptName': s}, 'sum': {'requests': r, 'cpuTimeUs': c}, 'quantiles': {'cpuTimeP50': p50, 'cpuTimeP99': p99}}
put('graphql-workers', gql(workersInvocationsAdaptive=[w('heavy-site', 1000, 10**7, 2000, 90000), w('calm-api', 500, 10**6, 1500, 4000)]))
hr = lambda t, r, c: {'dimensions': {'datetimeHour': t}, 'sum': {'requests': r, 'cpuTimeUs': c}}
put('graphql-hourly', gql(workersInvocationsAdaptive=[hr('2026-11-02T01:00:00Z', 100, 500000), hr('2026-11-02T02:00:00Z', 900, 9000000)]))
PY
cp -r "$W/fx" "$W/fx-nokv"; rm "$W/fx-nokv/graphql-kv.json"

run python3 "$SCRIPT" --fixtures "$W/fx" --date 2026-11-02 --days 3 --hourly
code "exit 0 on fixtures" 0
has "day 1 total sums split rows"     "2026-10-31  total 21.8500"
has "day 2 is a new period"           "2026-11-01  total 1.4000  [new period]"
has "day 3 is partial"                "2026-11-02  total 1.3000  [partial]"
has "range total adds days"           "range total 24.5500"
has "D1 lines merge to 12.5"          "12.5000  D1 Rows Read"
hasnt "top 6 only"                    "R2 Class A"
has "late-publish note"               "newest day is published late"
has "free allowance note"             "free allowance"
has "D1 daily rows read"              "2026-11-02  rows read 7000000"
has "biggest db first, by name"       "7000000  alpha-prod"
hasnt "6 databases only"              "tiny-eta"
has "fleet CPU total"                 "fleet CPU ms 11000"
has "heavy-tail share"                "HEAVY-TAIL SHARE 75.0%  (high: usually cold starts)"
has "KV namespace writes"             "1000  cache-ns"
has "KV hour total"                   "2026-11-02T01:00 650"
has "hourly step change"              "2026-11-02T02:00  requests 900"

run python3 "$SCRIPT" --fixtures "$W/fx-nokv" --date 2026-11-02 --days 3
code "exit 0 when a section is unavailable" 0
has "unavailable is named"            "unavailable: fixture missing: graphql-kv.json"
has "later sections still run"        "HEAVY-TAIL SHARE"
run python3 "$SCRIPT" --fixtures "$W/fx" --date 2026-11-02 --days 3 --json
python3 -c 'import json,sys; assert json.load(sys.stdin)["billing"]["days"][0]["total"]==21.85' <<<"$OUT" && ok "--json holds day totals" || no "--json"
run python3 "$SCRIPT" --section nope --fixtures "$W/fx";            code "bad --section" 2
run python3 "$SCRIPT" --date 11-02-2026 --fixtures "$W/fx";          code "bad date" 2
run python3 "$SCRIPT";                                               code "no credentials" 3
printf 'CLOUDFLARE_API_TOKEN=tok-FILE456\nCLOUDFLARE_ACCOUNT_ID=acct9\n' > "$W/env"
run python3 "$SCRIPT" --env-file "$W/env" --fixtures "$W/fx" --date 2026-11-02 --hourly; code "--env-file works" 0
hasnt "token never printed"           "tok-FILE456"
# The billing feed returns rows of ONE billing period when the range starts inside the old period: ask wide, keep only the asked days.
run python3 "$SCRIPT" --fixtures "$W/fx" --date 2026-11-02 --days 3 --section billing --show-range
has "asks a wide range, to is exclusive"  "from=2026-09-28 to=2026-11-03"
run python3 "$SCRIPT" --fixtures "$W/fx" --date 2026-11-01 --days 1 --section billing
has "keeps the asked day"             "2026-11-01  total 1.4000"
hasnt "drops an earlier day"          "2026-10-31  total"
hasnt "drops a later day"             "2026-11-02  total"
echo "$pass passed, $fail failed"; [ $fail -eq 0 ]
