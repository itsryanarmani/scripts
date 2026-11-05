#!/usr/bin/env bash
# E2E test for cf-cost-scan. Three fixture repos: `bad` has one known violation
# per check, `clean` has the safe form of each, `none` has no wrangler config
# and no Next app.
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
  "name": "x", "main": ".open-next/worker.js", "minify": true,
  "observability": { "enabled": true, "logs": { "invocation_logs": true } },
  "triggers": { "crons": ["* * * * *"] },
  "placement": { "region": "aws:us-east-1" }
}
EOF
put bad/app/page.tsx <<'EOF'
import Link from 'next/link';
export default function P() { return <Link href="/a">a</Link>; }
EOF
echo 'export const list = unstable_cache(async (q) => q, [JSON.stringify(params)], { revalidate: 300 });' | put bad/lib/data.ts
echo 'export async function GET() { return Response.json(await env.DB.prepare("SELECT id FROM l").all()); }' | put bad/app/sitemap.xml/route.ts
echo 'export const GET = () => new Response("User-agent: *");' | put bad/app/robots.txt/route.ts
echo 'export async function GET() { return Response.json(await db.prepare("SELECT COUNT(*) FROM l").first()); }' | put bad/app/api/stats/route.ts

put clean/wrangler.jsonc <<'EOF'
{ "name": "x", "main": ".open-next/worker.js", "observability": { "logs": { "invocation_logs": false } },
  "triggers": { "crons": ["0 3 * * *"] }, "placement": { "mode": "smart" } }
EOF
echo 'import Link from "next/link"; export const P = () => <Link href="/a" prefetch={false}>a</Link>;' | put clean/app/page.tsx
echo 'export const guard = (u: URL) => u.searchParams.has("_rsc");' | put clean/middleware.ts
echo 'export const list = unstable_cache(async (q) => q, ["list", slug], { revalidate: 86400 });' | put clean/lib/data.ts
printf 'export const revalidate = 86400;\nexport const GET = async () => env.DB.prepare("SELECT id FROM l");\n' | put clean/app/sitemap.xml/route.ts
echo 'User-agent: *' | put clean/public/robots.txt
echo 'export async function GET() { return Response.json({ ok: true }); }' | put clean/app/api/stats/route.ts

run "$W/bad"
code "exit 0 even when violations exist" 0
row "header"                 "repo | check | status | file:line | why it costs"
row "1 link prefetch"        "bad | link-prefetch | found | app/page.tsx:2 |"
row "2 rsc guard"            "bad | rsc-guard | found |"
row "3 json cache key"       "bad | json-cache-key | found | lib/data.ts:1 |"
row "4 short revalidate"     "bad | short-revalidate | found | lib/data.ts:1 |"
row "5 sitemap uncached"     "bad | sitemap-d1-uncached | found | app/sitemap.xml/route.ts:1 |"
row "6 invocation logs"      "bad | invocation-logs | found | wrangler.jsonc:3 |"
row "7 minify opennext"      "bad | minify-opennext | review | wrangler.jsonc:2 |"
row "8 cron every minute"    "bad | cron-every-minute | found | wrangler.jsonc:4 |"
row "9 txt from route"       "bad | static-txt-route | found | app/robots.txt/route.ts:1 |"
row "10 placement region"    "bad | placement-region | warning | wrangler.jsonc:5 |"
row "11 D1 full scan"        "bad | d1-full-scan | review | app/api/stats/route.ts:1 |"
run "$W/clean"
for c in link-prefetch rsc-guard json-cache-key short-revalidate sitemap-d1-uncached invocation-logs \
         minify-opennext cron-every-minute static-txt-route placement-region d1-full-scan; do
  row "clean: $c" "clean | $c | clear |"
done
run "$W/none"
row "no wrangler: n-a"       "none | invocation-logs | n-a |"
row "no Next app: n-a"       "none | link-prefetch | n-a |"
run "$W/bad" "$W/clean";           row "two repos in one table" "clean | link-prefetch | clear |"
run --fail-on found "$W/bad";      code "--fail-on found, bad repo" 1
run --fail-on found "$W/clean";    code "--fail-on found, clean repo" 0
run --fail-on nope "$W/bad";       code "bad usage" 2
(cd "$W/clean" && python3 "$SCRIPT" | grep -qF "clean | link-prefetch | clear |") && ok "default path is cwd" || no "default path"
echo "$pass passed, $fail failed"; [ $fail -eq 0 ]
