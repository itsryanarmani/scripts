#!/usr/bin/env bash
# E2E test for cf-cost-scan. Three fixture repos: `bad` has one known violation
# per check, `clean` has the safe form of each, `none` has no wrangler config
# and no Next app. `obs` has only guesses (review, never found) and odd files.
set -uo pipefail
SCRIPT="$(cd "$(dirname "$0")" && pwd)/cf-cost-scan"
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
pass=0; fail=0
ok() { echo "ok - $1"; pass=$((pass+1)); }
no() { echo "FAIL - $1"; fail=$((fail+1)); }
row() { grep -qF -- "$2" <<<"$OUT" && ok "$1" || no "$1 (missing: $2)"; }
code() { [ "$RC" -eq "$2" ] && ok "$1" || no "$1 (exit $RC)"; }
run() { OUT=$(python3 "$SCRIPT" "$@" 2>&1); RC=$?; }
put() { mkdir -p "$(dirname "$W/$1")"; cat > "$W/$1"; }

mkdir -p "$W/none"; echo 'echo hi' > "$W/none/run.sh"
for r in bad clean; do echo '{"dependencies":{"next":"15.0.0","@opennextjs/cloudflare":"1.0.0"}}' | put $r/package.json; done

put bad/wrangler.jsonc <<'EOF'
{
  "name": "x", "main": ".open-next/worker.js",
  "observability": { "enabled": true, "logs": { "invocation_logs": true } },
  "triggers": { "crons": ["* * * * *"] }
}
EOF
put bad/app/page.tsx <<'EOF'
import Link from 'next/link';
export default function P() { return <><Link href="/a">a</Link><Link href="/b">b</Link></>; }
EOF
echo 'export const list = unstable_cache(async (q) => q, [JSON.stringify(params)], { revalidate: 300 });' | put bad/lib/data.ts
echo 'export async function GET() { return Response.json(await env.DB.prepare("SELECT id FROM l").all()); }' | put bad/app/sitemap.xml/route.ts
echo 'export const GET = () => new Response("User-agent: *");' | put bad/app/robots.txt/route.ts

echo '{"dependencies":{"next":"15.0.0"}}' | put obs/package.json
echo '{ "triggers": { "crons": ["*/1  * * * *"] } }' | put obs/wrangler.jsonc
echo 'export const revalidate = 60 * 59;' | put obs/src/r.ts
echo 'export const l = unstable_cache(f, [JSON.stringify(p)]);' | put obs/lib/x.mts

put clean/wrangler.jsonc <<'EOF'
{ "name": "x", "main": ".open-next/worker.js", "observability": { "logs": { "invocation_logs": false } },
  "triggers": { "crons": ["0 3 * * *"] } }
EOF
echo 'import Link from "next/link"; export const P = () => <><Link href="/a" prefetch={false}>a</Link><Link onClick={() => go()} prefetch={false}>b</Link></>;' | put clean/app/page.tsx
printf 'export const h = { revalidate: 60 * 60 };\nexport const u = uncached(async () => JSON.stringify(x));\n' | put clean/lib/u.ts
echo 'export const L = 1;' | put clean/lib/ai.ts
echo 'export default () => ({ rules: {} });' | put clean/app/robots.ts
echo '{ "triggers": { "crons": ["* * * * *"] } }' | put clean/node_modules/x/wrangler.jsonc
echo 'export const guard = (u: URL) => u.searchParams.has("_rsc");' | put clean/middleware.ts
echo 'export const list = unstable_cache(async (q) => q, ["list", slug], { revalidate: 86400 });' | put clean/lib/data.ts
printf 'export const revalidate = 86400;\nexport const GET = async () => env.DB.prepare("SELECT id FROM l");\n' | put clean/app/sitemap.xml/route.ts
echo 'User-agent: *' | put clean/public/robots.txt

run "$W/bad"
code "exit 0 even when violations exist" 0
row "1 link prefetch"        "bad | link-prefetch | review | app/page.tsx:2 |"
row "2 rsc guard"            "bad | rsc-guard | review |"
row "3 json cache key"       "bad | json-cache-key | review | lib/data.ts:1 |"
row "4 short revalidate"     "bad | short-revalidate | review | lib/data.ts:1 |"
row "5 sitemap uncached"     "bad | sitemap-d1-uncached | review | app/sitemap.xml/route.ts:1 |"
row "6 invocation logs"      "bad | invocation-logs | found | wrangler.jsonc:3 |"
row "8 cron every minute"    "bad | cron-every-minute | review | wrangler.jsonc:4 |"
row "9 txt from route"       "bad | static-txt-route | found | app/robots.txt/route.ts:1 |"
run "$W/clean"
for c in link-prefetch rsc-guard json-cache-key short-revalidate sitemap-d1-uncached invocation-logs cron-every-minute static-txt-route; do
  row "clean: $c" "clean | $c | clear |"
done
run "$W/obs"
row "obs: */1 and extra spaces" "obs | cron-every-minute | review | wrangler.jsonc:1 |"
row "obs: 60 * 59 is short"     "obs | short-revalidate | review | src/r.ts:1 |"
row "obs: .mts is scanned"      "obs | json-cache-key | review | lib/x.mts:1 |"
run --fail-on found "$W/obs";      code "--fail-on found ignores review" 0
run "$W/none"
row "no wrangler: n-a"       "none | invocation-logs | n-a |"
run --fail-on found "$W/bad";      code "--fail-on found, bad repo" 1
run --fail-on found "$W/clean";    code "--fail-on found, clean repo" 0
run --fail-on nope "$W/bad";       code "bad usage" 2
echo "$pass passed, $fail failed"; [ $fail -eq 0 ]
