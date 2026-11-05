#!/usr/bin/env bash
# E2E test for cf-usage-report. No network: it reads fixture answers through
# --fixtures. Variants (fx-*) cover a missing day, truncated answers, a secret
# in an error and a wrong shape.
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
def billing(d31=True, cpu11=True, cpu12=False):
    cpu = lambda on, v: [('Workers CPU ms', v)] if on else []
    return {'result': (day('2026-10-31', '2026-10-01', [('D1 Rows Read', 10.0), ('D1 Rows Read', 2.5), ('Workers CPU ms', 4.0), ('KV Write Operations', 3.0),
        ('Workers Requests', 1.5), ('Containers vCPU', 0.5), ('Workers Logs events', 0.2), ('Queues operations', 0.1), ('R2 Class A', 0.05)]) if d31 else [])
    + day('2026-11-01', '2026-11-01', [('D1 Rows Read', 0.8), ('KV Write Operations', 0.2), ('Workers Requests', 0.1)] + cpu(cpu11, 0.3))
    + day('2026-11-02', '2026-11-01', [('D1 Rows Read', 1.1), ('KV Write Operations', 0.2), ('Containers vCPU', 0.1)] + cpu(cpu12, 0.3))}
put('billing', billing())
put('d1-databases', {'result': [{'uuid': f'db{i}', 'name': n} for i, n in enumerate(['alpha-prod', 'b', 'c', 'd', 'e', 'f', 'tiny-eta'])]})
put('graphql-d1-daily', gql(d1AnalyticsAdaptiveGroups=[{'dimensions': {'date': '2026-11-02'}, 'sum': {'rowsRead': 7000000, 'rowsWritten': 3000}}]))
put('graphql-d1-dbs', gql(d1AnalyticsAdaptiveGroups=[{'dimensions': {'databaseId': f'db{i}'}, 'sum': {'rowsRead': (7 - i) * 10**6, 'rowsWritten': 1}} for i in range(7)]))
# A: 10000 ms CPU, p50 2 ms x 1000 req -> tail 8000. B: 1000 ms, p50 1.5 ms x 500 req -> tail 250. Share 8250/11000.
w = lambda s, r, c, p50, p99: {'dimensions': {'scriptName': s}, 'sum': {'requests': r, 'cpuTimeUs': c}, 'quantiles': {'cpuTimeP50': p50, 'cpuTimeP99': p99}}
put('graphql-workers', gql(workersInvocationsAdaptive=[w('heavy-site', 1000, 10**7, 2000, 90000), w('calm-api', 500, 10**6, 1500, 4000)]))
import shutil
def variant(name, file, v):
    shutil.copytree(d, f'{d}-{name}'); json.dump(v, open(f'{d}-{name}/{file}.json', 'w'))
variant('gap', 'billing', billing(d31=False)); variant('mid', 'billing', billing(cpu11=False, cpu12=True))
variant('pages', 'billing', {'result': [], 'result_info': {'total_pages': 2}}); variant('cursor', 'billing', {'result': [], 'result_info': {'cursor': 'abc'}})
variant('trunc', 'graphql-workers', gql(workersInvocationsAdaptive=[w('s', 1, 1, 1, 1)] * 10000))
variant('err', 'graphql-workers', {'errors': [{'message': 'bad token tok-FILE456 for acct9'}]})
variant('list', 'graphql-workers', [])
PY
cp -r "$W/fx" "$W/fx-nokv"; rm "$W/fx-nokv/graphql-d1-daily.json"

run python3 "$SCRIPT" --fixtures "$W/fx" --date 2026-11-02 --days 3
code "exit 0 on fixtures" 0
has "day 1 total sums split rows"     "2026-10-31  total 21.8500"
has "day 2 is a new period"           "2026-11-01  total 1.4000  [new period]"
has "newest day is maybe partial (vCPU is not CPU)" "2026-11-02  total 1.4000  [maybe partial]"
has "range total adds days"           "range total 24.6500"
hasnt "a full range is not incomplete" "incomplete"
has "D1 lines merge to 12.5"          "12.5000  D1 Rows Read"
hasnt "top 6 only"                    "Queues operations"
has "D1 daily rows read"              "2026-11-02  rows read 7000000"
has "biggest db first, by name"       "7000000  alpha-prod"
has "fleet CPU total"                 "fleet CPU ms 11000"
has "heavy-tail share"                "HEAVY-TAIL SHARE at least 75.0%  (high: usually cold starts)"

run python3 "$SCRIPT" --fixtures "$W/fx-nokv" --date 2026-11-02 --days 3
code "exit 0 when a section is unavailable" 0
has "unavailable is named"            "unavailable: fixture missing: graphql-d1-daily.json"
has "later sections still run"        "HEAVY-TAIL SHARE"
run python3 "$SCRIPT" --fixtures "$W/fx" --date 2026-11-02 --days 3 --json
python3 -c 'import json,sys; assert json.load(sys.stdin)["billing"]["days"][0]["total"]==21.85' <<<"$OUT" && ok "--json holds day totals" || no "--json"
run python3 "$SCRIPT" --section nope --fixtures "$W/fx";            code "bad --section" 2
run python3 "$SCRIPT" --date 11-02-2026 --fixtures "$W/fx";          code "bad date" 2
run python3 "$SCRIPT";                                               code "no credentials" 3
printf 'CLOUDFLARE_API_TOKEN=tok-FILE456\nCLOUDFLARE_ACCOUNT_ID=acct9\n' > "$W/env"
printf 'CLOUDFLARE_API_TOKEN=tok-FILE456\nCLOUDFLARE_ACCOUNT_ID=bad-id\n' > "$W/env2"
run python3 "$SCRIPT" --env-file "$W/env2" --date 2026-11-02
code "--env-file is read: a bad id gets exit 2" 2
has "bad id message"                  "account id must be letters and digits"
# A secret in a GraphQL error is redacted only when it is set. An empty token must not add *** between letters.
run python3 "$SCRIPT" --env-file "$W/env" --fixtures "$W/fx-err" --date 2026-11-02 --section workers
has "token and account redacted"      "GraphQL: bad token *** for ***"
hasnt "token not printed"             "tok-FILE456"
hasnt "account not printed"           "acct9"
run python3 "$SCRIPT" --fixtures "$W/fx-err" --date 2026-11-02 --section workers
has "no secret set: text stays whole" "GraphQL: bad token tok-FILE456 for acct9"
run python3 "$SCRIPT" --fixtures "$W/fx-trunc" --date 2026-11-02 --section workers
has "a full GraphQL page is an error" "hit the 10000 row limit"
run python3 "$SCRIPT" --fixtures "$W/fx-pages" --date 2026-11-02 --section billing
has "REST total_pages above 1 is flagged" "unavailable: answer has more than one page"
run python3 "$SCRIPT" --fixtures "$W/fx-cursor" --date 2026-11-02 --section billing
has "REST cursor is flagged"          "unavailable: answer has more than one page"
run python3 "$SCRIPT" --fixtures "$W/fx-list" --date 2026-11-02 --section workers
has "wrong answer shape is named"     "unavailable: unexpected answer shape"
mkdir "$W/empty"; run python3 "$SCRIPT" --fixtures "$W/empty" --date 2026-11-02
code "exit 4 when every section fails" 4
# The billing feed returns rows of ONE billing period when the range starts inside the old period: ask wide, keep only the asked days.
run python3 "$SCRIPT" --fixtures "$W/fx" --date 2026-11-02 --days 3 --section billing --show-range
has "asks a wide range, to is exclusive"  "from=2026-09-28 to=2026-11-03"
run python3 "$SCRIPT" --fixtures "$W/fx" --date 2026-11-01 --days 1 --section billing
has "keeps the asked day"             "2026-11-01  total 1.4000"
hasnt "drops an earlier day"          "2026-10-31  total"
run python3 "$SCRIPT" --fixtures "$W/fx-gap" --date 2026-11-02 --days 3 --section billing
has "an absent day is listed"         "2026-10-31  missing"
has "the range is marked incomplete"  "range total 2.8000  [incomplete: 1 missing]"
run python3 "$SCRIPT" --fixtures "$W/fx-mid" --date 2026-11-02 --days 3 --section billing
hasnt "only the newest day can be partial" "partial]"
run python3 "$SCRIPT" --fixtures "$W/fx" --date 2026-11-02 --days 1 --section billing
has "--days 1 still judges the newest day" "2026-11-02  total 1.4000  [maybe partial]"
echo "$pass passed, $fail failed"; [ $fail -eq 0 ]
