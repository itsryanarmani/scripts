// Measures how long BrokerDO stays busy while boxes long-poll, in real
// workerd (Miniflare), for the code at a Git ref and for the working tree.
// Busy time is the union of intervals with a fetch, WebSocket message or alarm
// handler in flight. Cloudflare bills Durable Object duration for that time,
// plus idle time the object cannot hibernate. GitHub is a local fake.
// Usage: node e2e/hibernation-proof.mjs [--base origin/main] [--seconds 60] [--artifacts dir]
import assert from 'node:assert/strict';
import { createHmac, generateKeyPairSync } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import ts from 'typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const arg = (name, fallback) => { const i = process.argv.indexOf(name); return i < 0 ? fallback : process.argv[i + 1]; };
const base = arg('--base', 'origin/main');
const seconds = Number(arg('--seconds', '60'));
const artifacts = resolve(arg('--artifacts', mkdtempSync(join(tmpdir(), 'boat-hibernation-'))));
mkdirSync(artifacts, { recursive: true });
const BOXES = 4, secret = 'proof-secret-not-in-receipt';
const { privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
const pem = privateKey.export({ type: 'pkcs8', format: 'pem' });

// Wrap the real class. Only timing is added; the broker code is unchanged.
const wrapper = `
import worker, { BrokerDO as Base } from './broker.mjs';
let inflight = 0, t0 = 0;
export class BrokerDO extends Base {
  constructor(ctx, env) { super(ctx, env); ctx.storage.sql.exec('CREATE TABLE IF NOT EXISTS proof(k TEXT PRIMARY KEY, v REAL)'); }
  track(fn) {
    if (inflight++ === 0) t0 = Date.now();
    return Promise.resolve().then(fn).finally(() => {
      if (--inflight === 0) this.ctx.storage.sql.exec("INSERT INTO proof VALUES('busy', ?) ON CONFLICT(k) DO UPDATE SET v = v + excluded.v", Date.now() - t0);
    });
  }
  fetch(req) {
    if (new URL(req.url).pathname === '/proof-busy') return Response.json({ busyMs: this.ctx.storage.sql.exec("SELECT v FROM proof WHERE k='busy'").toArray()[0]?.v ?? 0 });
    return this.track(() => super.fetch(req));
  }
  webSocketMessage(ws, m) { return this.track(() => super.webSocketMessage(ws, m)); }
  alarm() { return this.track(() => super.alarm()); }
}
export default {
  fetch(req, env) {
    if (new URL(req.url).pathname === '/proof-busy') return env.BROKER.get(env.BROKER.idFromName('broker')).fetch(req);
    return worker.fetch(req, env);
  },
};`;

function fakeGitHub(req) {
  const path = new URL(req.url).pathname;
  if (path.endsWith('/access_tokens')) return Response.json({ token: 'fake', expires_at: new Date(Date.now() + 3600_000).toISOString() });
  if (path.endsWith('/generate-jitconfig')) return Response.json({ runner: { id: 7 }, encoded_jit_config: 'dummy-jit' });
  if (/\/actions\/runners\/\d+$/.test(path)) return new Response(null, { status: 204 });
  if (/\/actions\/jobs\/\d+$/.test(path)) return Response.json({ id: Number(path.split('/').at(-1)), run_id: 100, status: 'queued' });
  if (/\/actions\/runs\/\d+$/.test(path)) return Response.json({ id: 100, status: 'in_progress' });
  if (path === '/repos/itsryanarmani/fixture') return Response.json({ private: true });
  return Response.json({ message: 'unexpected' }, { status: 404 });
}

async function measure(variant, source) {
  const dir = join(artifacts, variant);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'broker.mjs'), ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText);
  writeFileSync(join(dir, 'entry.mjs'), wrapper);
  // Miniflare 5 takes a new option shape; convert the documented v4 shape.
  const mf = new Miniflare(convertV4MiniflareOptions({
    modules: [{ type: 'ESModule', path: join(dir, 'entry.mjs') }, { type: 'ESModule', path: join(dir, 'broker.mjs') }],
    modulesRoot: dir,
    compatibilityDate: '2025-08-01',
    durableObjects: { BROKER: { className: 'BrokerDO', useSQLite: true } },
    bindings: { APP_ID: '1', APP_INSTALLATION_ID: '1', APP_PRIVATE_KEY: pem, WEBHOOK_SECRET: secret, POOL_TOKEN: secret },
    outboundService: fakeGitHub,
  }));
  try {
    const auth = { authorization: `Bearer ${secret}` };
    const end = Date.now() + seconds * 1000;
    const statuses = {}, leases = [];
    let queuedAt = 0;
    const box = async n => {
      while (Date.now() < end) {
        const r = await mf.dispatchFetch(`https://broker.test/lease?label=boat&box=box${n}`, { headers: auth });
        statuses[r.status] = (statuses[r.status] ?? 0) + 1;
        if (r.status === 200) {
          const lease = await r.json();
          leases.push({ box: n, latencyMs: Date.now() - queuedAt });
          await hook('in_progress'); // GitHub reports the job picked up.
          await mf.dispatchFetch('https://broker.test/done', { method: 'POST', headers: auth, body: JSON.stringify({ lease_id: lease.lease_id, runner_id: lease.runner_id, repo: lease.repo }) });
        } else await r.arrayBuffer();
      }
    };
    const hook = async action => {
      const body = JSON.stringify({ action, repository: { private: true, full_name: 'itsryanarmani/fixture' }, workflow_job: { id: 101, run_id: 100, labels: ['boat'] } });
      const r = await mf.dispatchFetch('https://broker.test/webhook', { method: 'POST', body, headers: { 'x-github-event': 'workflow_job', 'x-hub-signature-256': 'sha256=' + createHmac('sha256', secret).update(body).digest('hex') } });
      assert.equal(r.status, 200);
    };
    const job = async () => {
      await new Promise(r => setTimeout(r, Math.min(20_000, seconds * 400)));
      queuedAt = Date.now();
      await hook('queued');
    };
    const started = Date.now();
    await Promise.all([job(), ...Array.from({ length: BOXES }, (_, n) => box(n))]);
    const wallMs = Date.now() - started;
    const { busyMs } = await (await mf.dispatchFetch('https://broker.test/proof-busy')).json();
    const busyFraction = busyMs / wallMs;
    return { variant, boxes: BOXES, wallMs, busyMs: Math.round(busyMs), busyPercent: +(100 * busyFraction).toFixed(2),
      projectedGBsPerMonth: Math.round(busyFraction * 30 * 86400 * 0.125), statuses, leases };
  } finally { await mf.dispose(); }
}

const before = await measure(`before-${base.replace(/\W+/g, '-')}`, execFileSync('git', ['show', `${base}:workers/boat-runners/src/index.ts`], { cwd: root, encoding: 'utf8' }));
const after = await measure('after-working-tree', readFileSync(join(root, 'src/index.ts'), 'utf8'));
const receipt = { base, seconds, before, after, secretExcluded: !JSON.stringify({ before, after }).includes(secret) };
writeFileSync(join(artifacts, 'receipt.json'), JSON.stringify(receipt, null, 2));
console.log(JSON.stringify(receipt, null, 2));
const ok = after.leases.length === 1 && after.leases[0].latencyMs < 2000 && after.busyMs < before.busyMs / 10 && receipt.secretExcluded;
if (!ok) { console.error('Proof failed: the job must be claimed within 2 s and busy time must drop by 10x.'); process.exitCode = 1; }
