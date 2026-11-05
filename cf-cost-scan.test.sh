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
# REVERSE_WALK=1 hands the scan every directory listing in reverse order, so no result may depend on it.
REV='import os,sys,runpy
w=os.walk
def r(*a,**k):
    for b,d,f in w(*a,**k):
        d.reverse(); f.reverse(); yield b,d,f
os.walk=r
s=sys.argv[1]; sys.argv=[s]+sys.argv[2:]
runpy.run_path(s,run_name="__main__")'
run() { if [ -n "${REVERSE_WALK:-}" ]; then OUT=$(python3 -c "$REV" "$SCRIPT" "$@" 2>&1); else OUT=$(python3 "$SCRIPT" "$@" 2>&1); fi; RC=$?; }
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
for r in c1 c2 c3 c4 c5 c6 c7 c8 c9 k1 k2 k3 k4 k5 k6 k7 k8 k9 i1 i2 i3 i4 i5 s1 s2 s3 jr1 jr2 l1 l2 l3 p1; do nx $r; done
for r in l1 l2 l3; do echo '{ "name": "x" }' | put $r/wrangler.jsonc; done
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
printf 'export const a = env.DB.prepare("WITH RECURSIVE t(n) AS (SELECT 1) SELECT n FROM t");\nexport const b = "SELECT value FROM json_each(?)";\n' | put jr1/lib/t.ts
echo 'export const a = env.DB.prepare("WITH RECURSIVE t AS (SELECT value FROM json_each(?)) SELECT 1 FROM t");' | put jr2/lib/t.ts
echo 'export const GET = () => { try { run(); } catch (e) { } console.log("x"); return 1; };' | put l1/app/api/a/route.ts
echo 'console.log("cli");' | put l2/scripts/index.ts
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
# Round 2: the reviewer's shapes. Calls on adjacent lines, no blank padding.
echo 'export const GET = () => { run().catch((e) => { console.log("x", e); }); return 1; };' | put l2/app/api/c/route.ts
printf 'export const GET = () => {\n  if (process.env.NODE_ENV !== "production") { dbg(); }\n  console.log("x");\n  return 1;\n};\n' | put l3/app/api/a/route.ts
printf 'const d = env.DB;\nfor (const id of ids) { await Promise.all(c.map(post)); }\n' | put p1/lib/p.ts
printf '// cache-key: bounded\nexport const a = unstable_cache(f, ["list", slug]);\nexport const b = unstable_cache(g, ["city", city]);\n' | put k4/lib/d.ts
printf '// cache-key: bounded\n\nexport const a = unstable_cache(f, ["list", slug]);\n' | put k5/lib/d.ts
printf 'export const a = unstable_cache(f, ["list", slug]); // cache-key: bounded\n// cache-key: bounded\nexport const b = unstable_cache(g, ["city", city]);\n' | put k6/lib/d.ts
printf 'export const a = unstable_cache(f, ["list", slug]); // cache-key: bounded\nexport const b = unstable_cache(g, ["city", city]);\n' | put k7/lib/d.ts
echo 'export const a = cachedIf(isHead, f, ["x", slug, city, id]);' | put k8/lib/d.ts
printf 'export const a = unstable_cache(g, ["a", site.id]);\nexport const b = unstable_cache(g, ["b", config.id]);\nexport const c = unstable_cache(g, ["c", cfg.id]);\nexport const d = unstable_cache(g, ["d", brand.id]);\nexport const e = unstable_cache(g, ["e", tenant.id]);\n' | put k9/lib/d.ts
echo 'export const a = unstable_cache(g, ["x", listing.id]);' | put i1/lib/d.ts
echo 'export const a = unstable_cache(g, ["x", request.id]);' | put i2/lib/d.ts
echo 'export const a = unstable_cache(g, ["x", id]);' | put i3/lib/d.ts
echo 'export const a = unstable_cache(g, ["x", searchParams.id]);' | put i4/lib/d.ts
echo 'export const a = unstable_cache(g, ["x", a.listing.id]);' | put i5/lib/d.ts
printf 'const r = await fetch(u, { next: { revalidate: 0 } });\nexport const n = () => %s;\n' "$CNT" | put c7/lib/f.ts
run "$W/l2"; row "r2: .catch callback and nested catch clear" "l2 | request-path-logs | clear |"
run "$W/l3"; row "r2: NODE_ENV block does not guard a later log" "l3 | request-path-logs | review | app/api/a/route.ts:3 |"
run "$W/p1"; row "r2: Promise.all in a loop is batching" "p1 | d1-n-plus-one | clear |"
run "$W/k4"; row "r2: adjacent loaders, comment covers one" "k4 | cache-key-unbounded | review | lib/d.ts:3 |"
run "$W/k5"; row "r2: blank line between comment and call" "k5 | cache-key-unbounded | review | lib/d.ts:3 |"
run "$W/k6"; row "r2: same-line and line-above comments clear" "k6 | cache-key-unbounded | clear |"
run "$W/k7"; row "r2: trailing comment does not cover next line" "k7 | cache-key-unbounded | review | lib/d.ts:2 |"
run "$W/k8"; row "r2: cachedIf is never reported" "k8 | cache-key-unbounded | clear |"
run "$W/k9"; row "r2: site config cfg brand tenant ids clear" "k9 | cache-key-unbounded | clear |"
for r in i1 i2 i3 i4 i5; do run "$W/$r"; row "r2: $r id key fires" "$r | cache-key-unbounded | review | lib/d.ts:1 |"; done
run "$W/c7"; row "r2: next revalidate 0 fires" "c7 | count-star-uncached | review | lib/f.ts:2 |"
# Round 3: a hint covers a statement only when the statement sits inside the hint call.
put h1/lib/f.ts <<EOF
export const k = unstable_cache(loadCats, ["cats"]);
export const n = () => $CNT;
EOF
printf 'export const k = unstable_cache(loadCats, ["cats"]);\nexport const q = env.DB.prepare("SELECT * FROM licences");\n' | put h2/lib/q.ts
printf 'export const all = () => env.DB.prepare("SELECT * FROM licences").all();\nexport const x = unstable_cache(f, ["x"]);\n' | put h3/lib/q.ts
{ echo 'export const getCounts = unstable_cache(async () => {'; for i in $(seq 1 14); do echo "  const v$i = 1;"; done
  echo "  return $CNT;"; echo '}, ["counts"]);'; } | put h4/lib/f.ts
printf 'const raw = () => %s;\nexport const n = cached(raw, ["n"]);\n' "$CNT" | put h5/lib/f.ts
printf 'export const revalidate = DATA_CACHE_REVALIDATE_SECONDS;\nexport const n = () => %s;\n' "$CNT" | put h6/app/page.tsx
printf 'export const revalidate = false;\nexport const n = () => %s;\n' "$CNT" | put h7/lib/f.ts
printf 'export const revalidate = 0;\nexport const n = () => %s;\n' "$CNT" | put h8/app/page.tsx
printf '// TODO: wrap in unstable_cache(\nexport const n = () => %s;\n' "$CNT" | put h9/lib/f.ts
printf 'export const k = unstable_cache(async () => {\nexport const n = () => %s;\n' "$CNT" | put h10/lib/f.ts
printf 'export const k = unstable_cache(async () => { return ")"; });\nexport const n = () => %s;\n' "$CNT" | put h11/lib/f.ts
printf 'export const k = cachedIf(h, async () => `(`, ["k"]);\nexport const n = () => %s;\n' "$CNT" | put h12/lib/f.ts
printf 'export const n = cached(() => env.DB.prepare("SELECT * FROM l"), ["n"]);\n' | put h13/lib/f.ts
printf 'export const revalidate = 300;\nexport const n = () => %s;\n' "$CNT" | put h14/lib/f.ts
printf 'export const revalidate = 300;\nexport const n = () => %s;\n' "$CNT" | put h15/app/api/x/route.ts
printf 'export const revalidate = 300;\nexport const n = () => %s;\n' "$CNT" | put h16/app/layout.tsx
printf '/* cache-key: bounded */ export const a = unstable_cache(f, ["list", slug]);\nexport const b = unstable_cache(g, ["city", city]);\n' | put bm1/lib/d.ts
printf 'export const a = unstable_cache(\n  f,\n  ["region", region], // cache-key: bounded\n);\n' | put bm2/lib/d.ts
printf '// cache-key: bounded\nexport const a = unstable_cache(\n  f,\n  ["region", region],\n);\n' | put bm3/lib/d.ts
printf 'export const a = unstable_cache( // cache-key: bounded\n  f,\n  ["region", region],\n);\nexport const b = unstable_cache(g, ["city", city]);\n' | put bm4/lib/d.ts
for w in country region category place state; do echo "export const a = unstable_cache(f, [\"list\", $w]);" | put kn-$w/lib/d.ts; done
for r in o1; do nx $r; done
for f in lib/q.ts app/q.ts lib/z.ts; do echo "export const q = env.DB.prepare(\"SELECT * FROM l\"); export const c = $CNT;" | put o1/$f; done
for r in h1 h2 h3 h4 h5 h6 h7 h8 h9 h10 h11 h12 h13 h14 h15 h16 bm1 bm2 bm3 bm4 kn-country kn-region kn-category kn-place kn-state; do nx $r; done
run "$W/h1"; row "r3: hint on the line above does not cover COUNT" "h1 | count-star-uncached | review | lib/f.ts:2 |"
run "$W/h2"; row "r3: hint on the line above does not cover select" "h2 | select-unbounded | review | lib/q.ts:2 |"
run "$W/h3"; row "r3: hint on the line below does not cover select" "h3 | select-unbounded | review | lib/q.ts:1 |"
run "$W/h4"; row "r3: COUNT inside the call body is covered" "h4 | count-star-uncached | clear |"
run "$W/h5"; row "r3: cached(raw) that holds no SQL does not cover" "h5 | count-star-uncached | review | lib/f.ts:1 |"
run "$W/h6"; row "r3: page revalidate = identifier covers the file" "h6 | count-star-uncached | clear |"
run "$W/h7"; row "r3: revalidate = false in lib/ is no cover" "h7 | count-star-uncached | review | lib/f.ts:2 |"
run "$W/h8"; row "r3: page revalidate = 0 does not cover" "h8 | count-star-uncached | review | app/page.tsx:2 |"
run "$W/h9"; row "r3: hint in a comment does not cover" "h9 | count-star-uncached | review | lib/f.ts:2 |"
run "$W/h10"; row "r3: unclosed call covers nothing" "h10 | count-star-uncached | review | lib/f.ts:2 |"
run "$W/h11"; row "r3: paren in a string does not close the call" "h11 | count-star-uncached | review | lib/f.ts:2 |"
run "$W/h12"; row "r3: paren in a template does not open a call" "h12 | count-star-uncached | review | lib/f.ts:2 |"
run "$W/h13"; row "r3: select inside cached() is covered" "h13 | select-unbounded | clear |"
run "$W/h14"; row "r3: file revalidate in lib/ is no cover" "h14 | count-star-uncached | review | lib/f.ts:2 |"
run "$W/h15"; row "r3: route revalidate covers the file" "h15 | count-star-uncached | clear |"
run "$W/h16"; row "r3: layout revalidate covers the file" "h16 | count-star-uncached | clear |"
run "$W/bm1"; row "r3: block comment covers its own call only" "bm1 | cache-key-unbounded | review | lib/d.ts:2 |"
run "$W/bm2"; row "r3: comment on the key line of a call covers it" "bm2 | cache-key-unbounded | clear |"
run "$W/bm3"; row "r3: comment above a multi-line call covers it" "bm3 | cache-key-unbounded | clear |"
run "$W/bm4"; row "r3: comment on the first line of a call covers it" "bm4 | cache-key-unbounded | review | lib/d.ts:5 |"
for w in country region category place state; do run "$W/kn-$w"; row "r3: $w key fires" "kn-$w | cache-key-unbounded | review | lib/d.ts:1 |"; done
run "$W/o1"
row "r3: first select hit is the first path in order" "o1 | select-unbounded | review | app/q.ts:1 |"
row "r3: first count hit is the first path in order" "o1 | count-star-uncached | review | app/q.ts:1 |"
run "$W/bad"
grep -qF "scans the table" <<<"$OUT" && no "r2: no unmeasured scan claim" || ok "r2: no unmeasured scan claim"
grep -qF "in a route" <<<"$OUT" && no "r2: texts say app code" || ok "r2: texts say app code"
run "$W/bad"
row "fix7: log text says may bill"    "may bill a log event on every request when Workers observability is on"
row "fix7: log text says what was measured" "Only invocation logs were measured"
grep -qF "scans the whole list" <<<"$OUT" && no "fix8: unmeasured cause removed" || ok "fix8: unmeasured cause removed"
echo "$pass passed, $fail failed"; [ $fail -eq 0 ]
