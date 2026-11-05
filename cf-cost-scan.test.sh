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
  "triggers": { "crons": ["* * * * *"] },
  "minify": true
}
EOF
put bad/app/page.tsx <<'EOF'
import Link from 'next/link';
export default function P() { return <><Link href="/a">a</Link><Link href="/b">b</Link></>; }
EOF
echo 'export const list = unstable_cache(async (q) => q, [JSON.stringify(params)], { revalidate: 300 });' | put bad/lib/data.ts
echo 'export async function GET() { return Response.json(await env.DB.prepare("SELECT id FROM l LIMIT 5").all()); }' | put bad/app/sitemap.xml/route.ts
echo 'export const c = unstable_cache(f, ["city", city], { revalidate: 86400 });' | put bad/lib/keys.ts
echo 'for (const id of ids) { const r = await env.DB.prepare("SELECT 1 WHERE a = ?").bind(id).first(); }' | put bad/lib/loop.ts
echo 'export const GET = async () => Response.json(await env.DB.prepare("SELECT * FROM listings").all());' | put bad/app/api/list/route.ts
echo 'export const q = "WITH t AS MATERIALIZED (SELECT value FROM json_each(?)) SELECT 1 FROM t";' | put bad/lib/tree.ts
echo 'export const GET = async () => env.DB.prepare("SELECT COUNT(*) AS n FROM listings WHERE active = 1").first();' | put bad/app/api/count/route.ts
echo 'export const GET = () => { console.log("hit"); return new Response("ok"); };' | put bad/app/api/hello/route.ts
echo 'export const GET = () => new Response("User-agent: *");' | put bad/app/robots.txt/route.ts

echo '{"dependencies":{"next":"15.0.0"}}' | put obs/package.json
echo '{ "triggers": { "crons": ["*/1  * * * *"] } }' | put obs/wrangler.jsonc
echo 'export const revalidate = 60 * 59;' | put obs/src/r.ts
echo 'export const l = unstable_cache(f, [JSON.stringify(p)]);' | put obs/lib/x.mts

put clean/wrangler.jsonc <<'EOF'
{ "name": "x", "main": ".open-next/worker.js", "observability": { "logs": { "invocation_logs": false } },
  "triggers": { "crons": ["0 3 * * *"] }, "minify": false }
EOF
echo 'import Link from "next/link"; export const P = () => <><Link href="/a" prefetch={false}>a</Link><Link onClick={() => go()} prefetch={false}>b</Link></>;' | put clean/app/page.tsx
printf 'export const h = { revalidate: 60 * 60 };\nexport const u = uncached(async () => JSON.stringify(x));\n' | put clean/lib/u.ts
echo 'export const L = 1;' | put clean/lib/ai.ts
echo 'export default () => ({ rules: {} });' | put clean/app/robots.ts
echo '{ "triggers": { "crons": ["* * * * *"] } }' | put clean/node_modules/x/wrangler.jsonc
echo 'export const guard = (u: URL) => u.searchParams.has("_rsc");' | put clean/middleware.ts
printf '// cache-key: bounded\nexport const list = unstable_cache(async (q) => q, ["list", slug], { revalidate: 86400 });\n' | put clean/lib/data.ts
printf 'export const revalidate = 86400;\nexport const GET = async () => env.DB.prepare("SELECT id FROM l LIMIT 50000");\n' | put clean/app/sitemap.xml/route.ts
echo 'for (const id of ids) { total += id; } export const b = env.DB.batch(ids.map((id) => stmt.bind(id)));' | put clean/lib/loop.ts
echo 'export const GET = async () => env.DB.prepare("SELECT id FROM l WHERE id = ? LIMIT 1").first();' | put clean/app/api/item/route.ts
echo 'export const q = "SELECT id FROM l WHERE id IN (SELECT value FROM json_each(?))";' | put clean/lib/tree.ts
printf 'export const revalidate = 86400;\nexport const GET = async () => env.DB.prepare("SELECT COUNT(*) AS n FROM l WHERE a = 1").first();\n' | put clean/app/api/count/route.ts
echo 'export const GET = () => { try { run(); } catch (e) { console.info("failed", e); } return new Response("ok"); };' | put clean/app/api/hello/route.ts
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
row "10 cache key unbounded" "bad | cache-key-unbounded | review | lib/keys.ts:1 |"
row "11 d1 in a loop"        "bad | d1-n-plus-one | review | lib/loop.ts:1 |"
row "12 select unbounded"    "bad | select-unbounded | review | app/api/list/route.ts:1 |"
row "13 json_each materialized" "bad | json-each-materialized | review | lib/tree.ts:1 |"
row "14 count uncached"      "bad | count-star-uncached | review | app/api/count/route.ts:1 |"
row "15 request path log"    "bad | request-path-logs | review | app/api/hello/route.ts:1 |"
row "16 minify true"         "bad | minify-true | review | wrangler.jsonc:5 |"
run "$W/clean"
for c in link-prefetch rsc-guard json-cache-key short-revalidate sitemap-d1-uncached invocation-logs cron-every-minute static-txt-route \
         cache-key-unbounded d1-n-plus-one select-unbounded json-each-materialized count-star-uncached request-path-logs minify-true; do
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
# Review fixes: one small repo per case, since a check reports only its first hit.
nx() { echo '{"dependencies":{"next":"15.0.0"}}' | put $1/package.json; }
for r in c1 c2 c3 c4 k1 k2 k3 s1 s2 jr1 jr2 l1 l2; do nx $r; done
for r in l1 l2; do echo '{ "name": "x" }' | put $r/wrangler.jsonc; done
CNT='env.DB.prepare("SELECT COUNT(*) AS n FROM l").first()'
echo "export const n = () => $CNT;" | put c1/lib/facets.ts
echo "export const n = cached(() => $CNT, [\"n\"]);" | put c2/lib/facets.ts
for f in scripts/c.ts lib/a.test.ts migrations/1.ts; do echo "export const n = () => $CNT;" | put c2/$f; done
printf 'export const revalidate = 0;\nexport const n = () => %s;\n' "$CNT" | put c3/lib/f.ts
printf 'import { revalidatePath } from "next/cache";\nexport const n = () => %s;\n' "$CNT" | put c4/lib/f.ts
printf '// cache-key: bounded\nexport const a = unstable_cache(f, ["list", slug]);\n\n\n\nexport const b = unstable_cache(g, ["city", city]);\n' | put k1/lib/d.ts
printf 'export const a = cachedIf(head, f, ["listing", slug]);\nexport const b = unstable_cache(g, ["cats", site.id]);\n' | put k2/lib/d.ts
echo 'export const a = unstable_cache(g, ["one", params.id]);' | put k3/lib/d.ts
echo 'export const q = env.DB.prepare("SELECT * FROM l");' | put s1/lib/q.ts
echo 'export const q = env.DB.prepare("SELECT * FROM l LIMIT 10");' | put s2/lib/a.ts
echo 'export const q = env.DB.prepare("SELECT * FROM l WHERE slug = ?");' | put s2/lib/b.ts
printf 'export const k = unstable_cache(f, ["k"]);\nexport const q = env.DB.prepare("SELECT * FROM l");\n' | put s2/lib/c.ts
printf 'export const a = env.DB.prepare("WITH RECURSIVE t(n) AS (SELECT 1) SELECT n FROM t");\nexport const b = "SELECT value FROM json_each(?)";\n' | put jr1/lib/t.ts
echo 'export const a = env.DB.prepare("WITH RECURSIVE t AS (SELECT value FROM json_each(?)) SELECT 1 FROM t");' | put jr2/lib/t.ts
echo 'export const GET = () => { try { run(); } catch (e) { } console.log("x"); return 1; };' | put l1/app/api/a/route.ts
echo 'console.log("cli");' | put l2/scripts/index.ts
echo 'export const GET = () => { if (process.env.NODE_ENV !== "production") console.log("d"); return 1; };' | put l2/app/api/g/route.ts
echo 'export const GET = () => { try { run(); } catch (e) { if (e) { fix(); } console.info("f", e); } return 1; };' | put l2/app/api/n/route.ts
PAD=$(printf 'x%.0s' $(seq 1 250))
echo "export const GET = () => { try { run(); } catch (e) { /* $PAD */ console.info(\"f\", e); } return 1; };" | put l2/app/api/o/route.ts
run "$W/c1"; row "fix1: COUNT in lib/ fires"           "c1 | count-star-uncached | review | lib/facets.ts:1 |"
run "$W/c2"; row "fix1: cached() and non-app files clear" "c2 | count-star-uncached | clear |"
run "$W/c3"; row "fix1: revalidate = 0 fires"           "c3 | count-star-uncached | review | lib/f.ts:2 |"
run "$W/c4"; row "fix1: revalidatePath fires"           "c4 | count-star-uncached | review | lib/f.ts:2 |"
run "$W/k1"; row "fix2: bound comment is per call"      "k1 | cache-key-unbounded | review | lib/d.ts:6 |"
run "$W/k2"; row "fix3: cachedIf(head) and site.id clear" "k2 | cache-key-unbounded | clear |"
run "$W/k3"; row "fix3: params.id fires"                "k3 | cache-key-unbounded | review | lib/d.ts:1 |"
run "$W/s1"; row "fix5: select in lib/ fires"           "s1 | select-unbounded | review | lib/q.ts:1 |"
run "$W/s2"; row "fix5: LIMIT, key lookup, cache clear" "s2 | select-unbounded | clear |"
run "$W/jr1"; row "fix8: split RECURSIVE/json_each clear" "jr1 | json-each-materialized | clear |"
run "$W/jr2"; row "fix8: same-query RECURSIVE fires"    "jr2 | json-each-materialized | review | lib/t.ts:1 |"
run "$W/l1"; row "fix6: log after a closed catch fires" "l1 | request-path-logs | review | app/api/a/route.ts:1 |"
run "$W/l2"; row "fix6: scripts, NODE_ENV, nested and long catch clear" "l2 | request-path-logs | clear |"
run "$W/bad"
row "fix7: log text says may bill"    "may bill a log event on every request when Workers observability is on"
row "fix7: log text says what was measured" "Only invocation logs were measured"
grep -qF "scans the whole list" <<<"$OUT" && no "fix8: unmeasured cause removed" || ok "fix8: unmeasured cause removed"
echo "$pass passed, $fail failed"; [ $fail -eq 0 ]
