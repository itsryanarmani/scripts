// Failure cases written before the broker change: terminal/deleted parent with
// queued child, failed parent lookup, live queue, rerun, and stale reconciliation.
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { DatabaseSync } from 'node:sqlite';
import ts from 'typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = process.argv.indexOf('--artifacts');
const artifacts = output < 0 ? mkdtempSync(join(tmpdir(), 'boat-terminal-runs-')) : resolve(process.argv[output + 1]);
mkdirSync(artifacts, { recursive: true });
const compiled = join(artifacts, 'broker.mjs');
writeFileSync(compiled, ts.transpileModule(readFileSync(join(root, 'src/index.ts'), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText);
const { default: worker, BrokerDO } = await import(pathToFileURL(compiled));
const secret = 'fixture-secret-must-not-appear-in-receipt';
const nativeNow = Date.now;
let clock = nativeNow();
Date.now = () => clock;

function fixture(parent = 'completed', lookupStatus = 200, jobLookupStatus = 200) {
  let parentState = parent;
  const db = new DatabaseSync(':memory:');
  const storage = {
    sql: { exec(sql, ...args) { const rows = db.prepare(sql).all(...args); return { toArray: () => rows }; } },
    transactionSync(fn) {
      db.exec('BEGIN');
      try { const result = fn(); db.exec('COMMIT'); return result; }
      catch (error) { db.exec('ROLLBACK'); throw error; }
    },
  };
  let mints = 0;
  const mintedLabels = [];
  const knownJobs = new Map();
  const env = { WEBHOOK_SECRET: secret, POOL_TOKEN: secret };
  const broker = new BrokerDO({ storage }, env);
  env.BROKER = { idFromName: () => 'broker', get: () => ({ fetch: (req, init) => broker.fetch(req instanceof Request ? req : new Request(req, init)) }) };
  // Only GitHub transport is replaced. Router, signatures, SQL, claims, cleanup,
  // and reconciliation execute the real broker code.
  broker.gh = async (path, method = 'GET', body) => {
    clock += 30_000; // Advance long-poll time without sleeping in the scenarios.
    if (method === 'DELETE') return new Response(null, { status: 204 });
    if (path.endsWith('/generate-jitconfig')) {
      mints++;
      mintedLabels.push(body.labels);
      return Response.json({ runner: { id: 7 }, encoded_jit_config: 'dummy-jit-secret' });
    }
    if (path === '/repos/itsryanarmani/fixture') return Response.json({ private: true });
    if (path.includes('/actions/jobs/')) return jobLookupStatus === 200 ? Response.json(knownJobs.get(Number(path.split('/').at(-1))) ?? { id: 101, run_id: 100, status: 'queued', labels: ['boat'] }) : Response.json({}, { status: jobLookupStatus });
    if (path === '/repos/itsryanarmani/fixture/actions/runs/100') {
      return lookupStatus === 200 ? Response.json({ id: 100, status: parentState }) : Response.json({ error: 'lookup refused' }, { status: lookupStatus });
    }
    if (path.includes('/actions/runs?')) {
      return Response.json({ workflow_runs: parentState !== 'completed' && path.includes(`status=${parentState}`) ? [{ id: 100 }] : [] });
    }
    if (path.includes('/actions/runs/100/jobs')) return Response.json({ jobs: [...knownJobs.values()] });
    if (path.includes('/actions/runners')) return Response.json({ runners: [] });
    throw new Error('Unexpected fake GitHub route');
  };
  const request = (path, init = {}) => worker.fetch(new Request(`https://fixture.invalid${path}`, {
    ...init, headers: { authorization: `Bearer ${secret}`, ...init.headers },
  }), env);
  async function seed(extra = {}, retained = true) {
    const job = { id: 101, run_id: 100, status: 'queued', labels: ['boat'], ...extra };
    knownJobs.set(job.id, job);
    const body = JSON.stringify({ action: 'queued', repository: { private: true, full_name: 'itsryanarmani/fixture' }, workflow_job: job });
    const signature = 'sha256=' + createHmac('sha256', secret).update(body).digest('hex');
    const response = await request('/webhook', { method: 'POST', body, headers: { 'x-github-event': 'workflow_job', 'x-hub-signature-256': signature } });
    assert.equal(response.status, 200);
    assert.equal(broker.rows('SELECT id FROM jobs WHERE id=?', job.id).length, retained ? 1 : 0);
  }
  return { db, broker, env, request, seed, setParent: value => { parentState = value; }, mints: () => mints, mintedLabels, jobs: () => broker.rows('SELECT * FROM jobs') };
}

const results = [];
async function scenario(name, check) {
  const started = performance.now();
  try { const observed = await check(); results.push({ name, passed: true, durationMs: Math.round(performance.now() - started), ...observed }); }
  catch (error) { results.push({ name, passed: false, durationMs: Math.round(performance.now() - started), error: error.message }); }
}
try {
  // Migration failures: saved leases must complete twice, foreign owners stay
  // blocked, and jobs queued before the rename must mint under the new owner.
  for (const owner of ['pooriaarab', 'itsryanarmani']) {
    await scenario(`${owner} saved lease completes and retries after removal`, async () => {
      const f = fixture('in_progress');
      try {
        const lease = { lease_id: 'saved-lease', repo: `${owner}/fixture`, runner_id: 7 };
        f.broker.rows('INSERT INTO leases(id,job,repo,name,runner,created,pending) VALUES(?,?,?,?,?,?,0)',
          lease.lease_id, 101, lease.repo, 'saved-runner', lease.runner_id, Date.now());
        const statuses = [];
        for (let attempt = 0; attempt < 2; attempt++) {
          const response = await f.request('/done', { method: 'POST', body: JSON.stringify(lease) });
          statuses.push(response.status);
          assert.equal(response.status, 200);
          assert.deepEqual(await response.json(), { deleted: true });
          assert.equal(f.broker.rows('SELECT * FROM leases').length, 0);
        }
        return { statuses, leasesRemaining: 0 };
      } finally { f.db.close(); }
    });
  }
  await scenario('saved old-owner job mints only for the new owner', async () => {
    const f = fixture('in_progress');
    try {
      await f.seed();
      f.broker.rows('UPDATE jobs SET repo=?', 'pooriaarab/fixture');
      const response = await f.request('/lease?label=boat&box=fixture');
      assert.equal(response.status, 200);
      const lease = await response.json();
      assert.equal(lease.repo, 'itsryanarmani/fixture');
      assert.equal(f.broker.rows('SELECT repo FROM leases')[0].repo, lease.repo);
      return { status: response.status, repo: lease.repo };
    } finally { f.db.close(); }
  });
  await scenario('saved-lease exception does not admit other owners or old webhooks', async () => {
    const f = fixture();
    try {
      const done = await f.request('/done', { method: 'POST', body: JSON.stringify({ lease_id: 'saved', repo: 'other/fixture', runner_id: 7 }) });
      assert.equal(done.status, 400);
      const body = JSON.stringify({ repository: { private: true, full_name: 'pooriaarab/fixture' }, workflow_job: { id: 101 } });
      const signature = 'sha256=' + createHmac('sha256', secret).update(body).digest('hex');
      const webhook = await f.request('/webhook', { method: 'POST', body, headers: { 'x-github-event': 'workflow_job', 'x-hub-signature-256': signature } });
      assert.equal(webhook.status, 400);
      return { foreignDone: done.status, oldWebhook: webhook.status };
    } finally { f.db.close(); }
  });
  async function claim(f, label = 'boat-8') {
    const response = await f.request(`/lease?label=${label}&box=fixture`);
    assert.equal(response.status, 200);
    return (await response.json()).job_id;
  }
  await scenario('large deployment passes older ordinary jobs', async () => {
    const f = fixture('in_progress');
    try {
      await f.seed({ id: 101, name: 'E2E smoke shard 1', labels: ['boat-8'] });
      await f.seed({ id: 102, name: 'Deploy canary / Deploy site (production)', labels: ['boat-deploy'] });
      const first = await claim(f);
      assert.equal(first, 102);
      assert.deepEqual(f.mintedLabels, [['boat-deploy']]);
      return { firstClaim: first };
    } finally { f.db.close(); }
  });
  await scenario('two prioritized claims preserve ordinary FIFO progress', async () => {
    const f = fixture('in_progress');
    try {
      for (const id of [101, 102]) await f.seed({ id, name: 'E2E smoke', labels: ['boat-8'] });
      for (const id of [201, 202, 203, 204]) await f.seed({ id, name: 'Deploy site', labels: ['boat-deploy'] });
      const order = [];
      for (let i = 0; i < 6; i++) order.push(await claim(f));
      assert.deepEqual(order, [201, 202, 101, 203, 204, 102]);
      assert.equal(f.mints(), 6);
      return { order, runnerMints: f.mints() };
    } finally { f.db.close(); }
  });
  await scenario('standard label keeps FIFO order', async () => {
    const f = fixture('in_progress');
    try {
      await f.seed({ id: 101, name: 'Ordinary check' });
      await f.seed({ id: 102, name: 'Deploy metadata' });
      assert.deepEqual([await claim(f, 'boat'), await claim(f, 'boat')], [101, 102]);
      return { order: [101, 102] };
    } finally { f.db.close(); }
  });
  await scenario('reconciliation preserves deployment labels, queue age, and leases', async () => {
    const f = fixture('in_progress');
    try {
      await f.seed({ id: 101, name: 'E2E smoke', labels: ['boat-8'] });
      await f.seed({ id: 102, name: 'Deploy site', labels: ['boat-deploy'] });
      const before = f.jobs().find(j => j.id === 102);
      // Simulate an existing record without changing its original queue age.
      await worker.scheduled({}, f.env);
      const after = f.jobs().find(j => j.id === 102);
      assert.equal(after.queued, before.queued);
      assert.equal(await claim(f), 102);
      const lease = f.jobs().find(j => j.id === 102).lease;
      await f.seed({ id: 102, name: 'Deploy site', labels: ['boat-deploy'] });
      assert.equal(f.jobs().find(j => j.id === 102).lease, lease);
      assert.equal(await claim(f), 101);
      return { queueTimestampPreserved: true, leasePreserved: true };
    } finally { f.db.close(); }
  });
  await scenario('deployment label cannot request pool capacity directly', async () => {
    const f = fixture('in_progress');
    try {
      await f.seed({ id: 101, name: 'E2E smoke', labels: ['boat-8'] });
      await f.seed({ id: 102, name: 'Deploy site', labels: ['boat-deploy'] });
      const response = await f.request('/lease?label=boat-deploy&box=fixture');
      assert.equal(response.status, 400);
      assert.equal(f.mints(), 0);
      return { status: response.status, runnerMints: f.mints() };
    } finally { f.db.close(); }
  });
  await scenario('mixed deployment labels never enter the queue', async () => {
    const f = fixture('in_progress');
    try {
      for (const labels of [['boat-deploy', 'boat-8'], ['boat-8', 'boat-deploy'], ['boat-deploy', 'self-hosted']]) {
        await f.seed({ id: 102, name: 'Deploy site', labels }, false);
        assert.equal(f.jobs().length, 0);
      }
      return { jobsRemaining: f.jobs().length, runnerMints: f.mints() };
    } finally { f.db.close(); }
  });
  await scenario('job names cannot grant deployment isolation', async () => {
    const f = fixture('in_progress');
    try {
      await f.seed({ id: 101, name: 'E2E smoke', labels: ['boat-8'] });
      await f.seed({ id: 102, name: 'Deploy site', labels: ['boat-8'] });
      assert.equal(await claim(f), 101);
      assert.deepEqual(f.mintedLabels, [['boat-8']]);
      return { firstClaim: 101, runnerLabels: f.mintedLabels };
    } finally { f.db.close(); }
  });
  await scenario('deployment backoff is respected', async () => {
    const f = fixture('in_progress');
    try {
      await f.seed({ id: 101, name: 'E2E smoke', labels: ['boat-8'] });
      await f.seed({ id: 102, name: 'Deploy site', labels: ['boat-deploy'] });
      f.broker.rows('UPDATE jobs SET next=? WHERE id=102', Date.now() + 600_000);
      assert.equal(await claim(f), 101);
      return { firstClaim: 101 };
    } finally { f.db.close(); }
  });
  for (const [name, status] of [['completed parent', 200], ['deleted parent', 404]]) {
    await scenario(`${name} refuses queued child before runner creation`, async () => {
      const f = fixture('completed', status);
      try {
        await f.seed();
        const response = await f.request('/lease?label=boat&box=fixture');
        assert.equal(response.status, 204);
        assert.equal(f.mints(), 0);
        assert.equal(f.jobs().length, 0);
        return { status: response.status, runnerMints: f.mints(), jobsRemaining: f.jobs().length };
      } finally { f.db.close(); }
    });
  }
  for (const lookupStatus of [403, 503]) {
    await scenario(`parent lookup ${lookupStatus} preserves queued work`, async () => {
      const f = fixture('in_progress', lookupStatus);
      try {
        await f.seed();
        const response = await f.request('/lease?label=boat&box=fixture');
        assert.equal(response.status, 502);
        assert.equal(f.mints(), 0);
        assert.equal(f.jobs().length, 1);
        return { status: response.status, runnerMints: f.mints(), jobsRemaining: f.jobs().length };
      } finally { f.db.close(); }
    });
  }
  for (const parent of ['queued', 'in_progress']) {
    await scenario(`live ${parent} parent allocates a runner`, async () => {
      const f = fixture(parent);
      try {
        await f.seed();
        const response = await f.request('/lease?label=boat&box=fixture');
        assert.equal(response.status, 200);
        assert.equal(f.mints(), 1); // Positive control proves the mint counter works.
        return { status: response.status, runnerMints: f.mints() };
      } finally { f.db.close(); }
    });
  }
  for (const [parent, lookupStatus, remaining] of [['completed', 200, 0], ['completed', 404, 0], ['in_progress', 503, 1]]) {
    await scenario(`reconcile parent ${parent}/${lookupStatus} leaves ${remaining} jobs`, async () => {
      const f = fixture(parent, lookupStatus);
      try {
        await f.seed();
        let failed = false;
        try { await worker.scheduled({}, f.env); } catch { failed = true; }
        assert.equal(f.jobs().length, remaining);
        assert.equal(f.mints(), 0);
        assert.equal(failed, lookupStatus === 503);
        return { jobsRemaining: f.jobs().length, runnerMints: f.mints(), retryRequired: failed };
      } finally { f.db.close(); }
    });
  }
  await scenario('reconcile retires stale queue but keeps independent runner lease', async () => {
    const f = fixture('in_progress');
    try {
      await f.seed();
      assert.equal((await f.request('/lease?label=boat&box=fixture')).status, 200);
      f.setParent('completed');
      await worker.scheduled({}, f.env);
      assert.equal(f.jobs().length, 0);
      assert.equal(f.broker.rows('SELECT * FROM leases WHERE closing=0').length, 1);
      return { jobsRemaining: 0, independentLeases: 1 };
    } finally { f.db.close(); }
  });
  await scenario('reconcile removes a job deleted with its run', async () => {
    const f = fixture('completed', 404, 404);
    try {
      await f.seed();
      await worker.scheduled({}, f.env);
      assert.equal(f.jobs().length, 0);
      return { jobsRemaining: 0, runnerMints: f.mints() };
    } finally { f.db.close(); }
  });
} finally { Date.now = nativeNow; }
const receipt = { scenarios: results, secretExcluded: !JSON.stringify(results).includes(secret) && !JSON.stringify(results).includes('dummy-jit-secret') };
writeFileSync(join(artifacts, 'receipt.json'), JSON.stringify(receipt, null, 2));
console.log(JSON.stringify(receipt, null, 2));
if (results.some(row => !row.passed) || !receipt.secretExcluded) process.exitCode = 1;
