interface Env { APP_ID: string; APP_INSTALLATION_ID: string; APP_PRIVATE_KEY: string; WEBHOOK_SECRET: string; POOL_TOKEN: string; BROKER: DurableObjectNamespace }
const poolLabels = ['boat', 'boat-8'];
const labels = [...poolLabels, 'boat-deploy'];
const json = (body: unknown, status = 200) => Response.json(body, { status });
const b64url = (bytes: ArrayBuffer | Uint8Array) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const pause = (ms: number) => new Promise(r => setTimeout(r, ms));
const repoPattern = /^itsryanarmani\/[A-Za-z0-9_.-]+$/;
// Remove old-owner lease acceptance after 2026-11-21; running runners hold old lease files.
const savedLeaseRepoPattern = /^(?:itsryanarmani|pooriaarab)\/[A-Za-z0-9_.-]+$/;
async function signature(raw: string, header: string | null, secret: string) {
  if (!secret || !/^sha256=[a-f0-9]{64}$/.test(header ?? '')) return false;
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']);
  const bytes = Uint8Array.from(header!.slice(7).match(/../g)!, x => parseInt(x, 16));
  return crypto.subtle.verify('HMAC', key, bytes, new TextEncoder().encode(raw));
}
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const path = new URL(req.url).pathname;
    const broker = env.BROKER.get(env.BROKER.idFromName('broker'));
    try {
      if (path === '/webhook' && req.method === 'POST') {
        const raw = await req.text();
        if (!await signature(raw, req.headers.get('x-hub-signature-256'), env.WEBHOOK_SECRET)) return json({ error: 'Bad signature' }, 401);
        if (req.headers.get('x-github-event') !== 'workflow_job') return json({ ignored: true });
        const p = JSON.parse(raw);
        if (p.repository?.private !== true) return json({ ignored: 'not-private' });
        if (!repoPattern.test(p.repository.full_name) || !Number.isSafeInteger(p.workflow_job?.id)) return json({ error: 'Bad payload' }, 400);
        return broker.fetch('https://broker/ingest', { method: 'POST', body: JSON.stringify(p) });
      }
      if (!['/lease', '/done', '/status'].includes(path)) return json({ error: 'Not found' }, 404);
      if (!env.POOL_TOKEN || req.headers.get('authorization') !== `Bearer ${env.POOL_TOKEN}`) return json({ error: 'Unauthorized' }, 401);
      return await broker.fetch(req);
    } catch (error) {
      return json({ error: error instanceof SyntaxError ? 'Bad JSON' : 'Broker unavailable' }, error instanceof SyntaxError ? 400 : 503);
    }
  },
  async scheduled(_event: ScheduledEvent, env: Env) {
    const response = await env.BROKER.get(env.BROKER.idFromName('broker')).fetch('https://broker/sweep', { method: 'POST' });
    if (!response.ok) throw new Error('Reconciliation failed');
  },
};
type Row = Record<string, any>;
export class BrokerDO {
  sql: SqlStorage;
  constructor(private ctx: DurableObjectState, private env: Env) {
    this.sql = ctx.storage.sql;
    this.sql.exec('CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, repo TEXT, label TEXT, run_id INTEGER, queued INTEGER, lease TEXT)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS leases(id TEXT PRIMARY KEY, job INTEGER, repo TEXT, name TEXT, runner INTEGER, created INTEGER, closing INTEGER DEFAULT 0, pending INTEGER DEFAULT 1)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS ended(id INTEGER PRIMARY KEY, seen INTEGER)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS repos(repo TEXT PRIMARY KEY, seen INTEGER)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v INTEGER)');
    // Backoff for jobs whose mint failed. Without it every Box retried the same
    // job every few seconds and drained the API budget in minutes. A job is
    // never dropped for failing: GitHub would keep it queued with no runner.
    for (const col of ['tries INTEGER DEFAULT 0', 'next INTEGER DEFAULT 0']) {
      try { this.sql.exec(`ALTER TABLE jobs ADD COLUMN ${col}`); } catch { /* column exists */ }
    }
    this.sql.exec('CREATE TABLE IF NOT EXISTS boxes(box TEXT PRIMARY KEY, label TEXT, seen INTEGER)');
  }
  rows(query: string, ...args: any[]): Row[] { return this.sql.exec(query, ...args).toArray(); }
  // GitHub App installation token. It has its own rate budget, so the owner's
  // personal token budget running dry no longer stops runner minting.
  app?: { token: string; expires: number };
  minting?: Promise<string>;
  token(): Promise<string> {
    if (this.app && this.app.expires - Date.now() > 300_000) return Promise.resolve(this.app.token);
    // Concurrent requests share one exchange instead of minting a token each.
    this.minting ??= this.newToken().finally(() => { this.minting = undefined; });
    return this.minting;
  }
  async newToken(): Promise<string> {
    const der = Uint8Array.from(atob(this.env.APP_PRIVATE_KEY.replace(/-----[^-]+-----|\s/g, '')), c => c.charCodeAt(0));
    const key = await crypto.subtle.importKey('pkcs8', der, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['sign']);
    const now = Math.floor(Date.now() / 1000), enc = new TextEncoder();
    const unsigned = b64url(enc.encode(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))) + '.' + b64url(enc.encode(JSON.stringify({ iat: now - 60, exp: now + 540, iss: this.env.APP_ID })));
    const jwt = unsigned + '.' + b64url(await crypto.subtle.sign('RSASSA-PKCS1-v1_5', key, enc.encode(unsigned)));
    const r = await fetch(`https://api.github.com/app/installations/${this.env.APP_INSTALLATION_ID}/access_tokens`, { method: 'POST', headers: { Authorization: `Bearer ${jwt}`, Accept: 'application/vnd.github+json', 'User-Agent': 'boat-runners' }, signal: AbortSignal.timeout(20_000) });
    if (!r.ok) throw new Error(`App token ${r.status}`);
    const t: any = await r.json();
    this.app = { token: t.token, expires: Date.parse(t.expires_at) };
    return t.token;
  }
  async gh(path: string, method = 'GET', body?: unknown) {
    return fetch(`https://api.github.com${path}`, { method, headers: { Authorization: `Bearer ${await this.token()}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'boat-runners', 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(20_000) });
  }
  async data(path: string) {
    const r = await this.gh(path);
    if (!r.ok) throw new Error(`GitHub ${r.status}`);
    return r.json() as Promise<any>;
  }
  async runEnded(repo: string, id: number): Promise<boolean> {
    if (!Number.isSafeInteger(id) || id <= 0) throw new Error('Invalid workflow run');
    const response = await this.gh(`/repos/${repo}/actions/runs/${id}`);
    if (response.status === 404) return true;
    if (!response.ok) throw new Error(`Workflow run lookup ${response.status}`);
    const run = await response.json() as { status?: unknown };
    if (typeof run.status !== 'string' || !['queued', 'in_progress', 'waiting', 'pending', 'requested', 'completed'].includes(run.status)) throw new Error('Invalid workflow run status');
    return run.status === 'completed';
  }
  async list(path: string, key: string) {
    const all: Row[] = [];
    for (let page = 1; ; page++) {
      const p = await this.data(`${path}${path.includes('?') ? '&' : '?'}per_page=100&page=${page}`);
      all.push(...p[key]);
      if (p[key].length < 100) return all;
    }
  }
  add(repo: string, job: Row) {
    // A deployment JIT runner has one exclusive label. A conjunction with
    // another label cannot match it and must not consume pool capacity.
    if (job.labels?.includes('boat-deploy') && job.labels.length !== 1) return;
    const label = job.labels?.find((l: string) => labels.includes(l));
    if (!label || this.rows('SELECT id FROM ended WHERE id=?', job.id).length) return;
    this.rows('INSERT OR IGNORE INTO jobs(id,repo,label,run_id,queued,lease) VALUES(?,?,?,?,?,NULL)', job.id, repo, label, job.run_id, Date.now());
  }
  async end(id: number, completed: boolean) {
    this.ctx.storage.transactionSync(() => {
      this.rows('INSERT OR REPLACE INTO ended VALUES(?,?)', id, Date.now());
      this.rows('DELETE FROM jobs WHERE id=?', id);
      if (completed) this.rows('UPDATE leases SET closing=1 WHERE job=?', id);
    });
    if (completed) for (const lease of this.rows('SELECT * FROM leases WHERE job=?', id)) await this.cleanup(lease);
  }
  async cleanup(lease: Row): Promise<boolean> {
    if (lease.pending && lease.created > Date.now() - 180_000) return false;
    try {
      let runner = lease.runner;
      if (!runner) runner = (await this.list(`/repos/${lease.repo}/actions/runners`, 'runners')).find(r => r.name === lease.name)?.id;
      if (runner) {
        const r = await this.gh(`/repos/${lease.repo}/actions/runners/${runner}`, 'DELETE');
        if (!r.ok && r.status !== 404) return false;
      }
      this.ctx.storage.transactionSync(() => {
        this.rows('UPDATE jobs SET lease=NULL WHERE lease=?', lease.id);
        this.rows('DELETE FROM leases WHERE id=?', lease.id);
      });
      return true;
    } catch { return false; }
  }
  tries(job: number): number { return this.rows('SELECT tries FROM jobs WHERE id=?', job)[0]?.tries ?? 0; }
  async mint(label: string, box: string): Promise<Response | null> {
    let lease: Row | undefined;
    this.ctx.storage.transactionSync(() => {
      const ordinary = this.rows('SELECT * FROM jobs WHERE label=? AND lease IS NULL AND next<=? ORDER BY queued,id LIMIT 1', label, Date.now())[0];
      const urgent = label === 'boat-8' ? this.rows('SELECT * FROM jobs WHERE label=? AND lease IS NULL AND next<=? ORDER BY queued,id LIMIT 1', 'boat-deploy', Date.now())[0] : undefined;
      const key = `priority-streak:${label}`;
      const streak = this.rows('SELECT v FROM meta WHERE k=?', key)[0]?.v ?? 0;
      // Give deploys the next free large slot, but let an ordinary claim
      // progress after two prioritized claims. Never preempt a live lease.
      const job = urgent && (!ordinary || streak < 2) ? urgent : ordinary;
      if (!job) return;
      this.rows('INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)', key, job.label === 'boat-deploy' ? Math.min(2, streak + 1) : 0);
      const id = crypto.randomUUID();
      lease = { id, job: job.id, repo: job.repo.replace(/^pooriaarab\//, 'itsryanarmani/'), label: job.label, name: `boat-${box.slice(0, 16)}-${id}`, created: Date.now(), pending: 1 };
      this.rows('INSERT INTO leases(id,job,repo,name,created) VALUES(?,?,?,?,?)', id, job.id, lease.repo, lease.name, lease.created);
      this.rows('UPDATE jobs SET lease=? WHERE id=?', id, job.id);
    });
    if (!lease) return null;
    const l = lease;
    try {
      // The sweep no longer re-checks privacy, so this is the gate: a repo that
      // went public after its job was queued must never get a runner.
      const repo = await this.data(`/repos/${l.repo}`);
      const jr = await this.gh(`/repos/${l.repo}/actions/jobs/${l.job}`);
      // A deleted run or job never comes back: end it instead of retrying.
      const job: any = jr.status === 404 ? { status: 'gone' } : jr.ok ? await jr.json() : null;
      if (!job) throw new Error(`GitHub ${jr.status}`);
      if (repo.private !== true || job.status !== 'queued') {
        await this.end(l.job, job.status !== 'in_progress');
        this.rows('UPDATE leases SET closing=1 WHERE id=?', l.id);
        await this.cleanup(l);
        return null;
      }
      // GitHub can leave a child queued after its workflow run completes.
      if (await this.runEnded(l.repo, job.run_id)) {
        await this.end(l.job, false);
        // This lease has not issued a runner. Older leases remain independent.
        this.rows('DELETE FROM leases WHERE id=?', l.id);
        console.info(JSON.stringify({ event: 'boat.queue.retired', job: l.job, run: job.run_id, reason: 'run-ended' }));
        return null;
      }
      const r = await this.gh(`/repos/${l.repo}/actions/runners/generate-jitconfig`, 'POST', { name: l.name, runner_group_id: 1, labels: [l.label], work_folder: '_work' });
      if (!r.ok) { this.rows('UPDATE leases SET pending=0 WHERE id=?', l.id); l.pending = 0; throw new Error(`Mint ${r.status}`); }
      const cfg: any = await r.json();
      l.runner = cfg.runner.id; l.pending = 0;
      this.rows('UPDATE leases SET runner=?, pending=0 WHERE id=?', l.runner, l.id);
      if (!this.rows('SELECT id FROM jobs WHERE lease=?', l.id).length || !this.rows('SELECT id FROM leases WHERE id=? AND closing=0', l.id).length) {
        await this.cleanup(l);
        return null;
      }
      return json({ lease_id: l.id, job_id: l.job, repo: l.repo, label: l.label, runner_id: l.runner, encoded_jit_config: cfg.encoded_jit_config });
    } catch {
      this.ctx.storage.transactionSync(() => {
        this.rows('UPDATE leases SET closing=1 WHERE id=?', l.id);
        this.rows('UPDATE jobs SET lease=NULL, tries=tries+1, next=? WHERE lease=?', Date.now() + Math.min(600_000, 30_000 * 2 ** this.tries(l.job)), l.id);
      });
      await this.cleanup(l);
      return json({ error: 'Mint failed; claim released' }, 502);
    }
  }
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url), path = url.pathname;
    if (path === '/ingest' && req.method === 'POST') {
      const p: any = await req.json(), repo = p.repository.full_name, job = p.workflow_job;
      this.rows('INSERT OR REPLACE INTO repos VALUES(?,?)', repo, Date.now());
      if (p.action === 'queued') this.add(repo, job);
      if (['in_progress', 'completed'].includes(p.action)) await this.end(job.id, p.action === 'completed');
      return json({ ok: true });
    }
    if (path === '/lease' && req.method === 'GET') {
      const label = url.searchParams.get('label') ?? '', box = url.searchParams.get('box') ?? '';
      if (!poolLabels.includes(label) || !/^[\w.-]{1,80}$/.test(box)) return json({ error: 'Invalid label or box' }, 400);
      this.rows('INSERT OR REPLACE INTO boxes VALUES(?,?,?)', box, label, Date.now());
      const deadline = Date.now() + 25_000;
      do {
        const r = await this.mint(label, box);
        if (r) return r;
        await pause(Math.min(1000, Math.max(0, deadline - Date.now())));
      } while (Date.now() < deadline);
      return new Response(null, { status: 204 });
    }
    if (path === '/done' && req.method === 'POST') {
      const b: any = await req.json();
      if (typeof b.lease_id !== 'string' || !Number.isSafeInteger(b.runner_id) || !savedLeaseRepoPattern.test(b.repo)) return json({ error: 'Invalid lease' }, 400);
      const lease = this.rows('SELECT * FROM leases WHERE id=? AND repo=? AND runner=?', b.lease_id, b.repo, b.runner_id)[0];
      if (!lease) return json({ deleted: true });
      this.rows('UPDATE leases SET closing=1 WHERE id=?', lease.id);
      const deleted = await this.cleanup(lease);
      return json({ deleted }, deleted ? 200 : 502);
    }
    if (path === '/status' && req.method === 'GET') {
      const open: Row = {}, claimed: Row = {}, boxes: Row = {};
      for (const label of labels) {
        open[label] = this.rows('SELECT COUNT(*) n FROM jobs WHERE label=? AND lease IS NULL', label)[0].n;
        claimed[label] = this.rows('SELECT COUNT(*) n FROM jobs WHERE label=? AND lease IS NOT NULL', label)[0].n;
        boxes[label] = this.rows('SELECT box,seen FROM boxes WHERE label=? AND seen>?', label, Date.now() - 600_000);
      }
      return json({ open, claimed, boxes });
    }
    if (path === '/sweep' && req.method === 'POST') return json(await this.sweep());
    return json({ error: 'Not found' }, 404);
  }
  async sweep() {
    let errors = 0;
    for (const l of this.rows('SELECT * FROM leases WHERE closing=1 OR created<?', Date.now() - 180_000)) {
      try {
        const r = await this.gh(`/repos/${l.repo}/actions/jobs/${l.job}`);
        if (!r.ok && r.status !== 404) throw new Error('Job lookup failed');
        const job: any = r.ok ? await r.json() : { status: 'completed' };
        if (!l.closing && job.status === 'in_progress') { await this.end(l.job, false); continue; }
        if (job.status !== 'queued') await this.end(l.job, false);
        this.rows('UPDATE leases SET closing=1 WHERE id=?', l.id);
        if (!await this.cleanup(l)) errors++;
      } catch { errors++; }
    }
    // The reconcile costs several API calls per repo, so it runs every 10
    // minutes and only for repos active in the last 24 hours. Lease expiry
    // above still runs on every 2-minute tick. Privacy is re-checked in mint()
    // before any runner is issued.
    const now = Date.now();
    const last = this.rows("SELECT v FROM meta WHERE k='reconciled'")[0]?.v ?? 0;
    const due = now - last >= 600_000;
    if (due) this.rows("INSERT OR REPLACE INTO meta VALUES('reconciled',?)", now);
    const repos = due ? this.rows('SELECT repo FROM repos WHERE seen>?', now - 86_400_000) : [];
    for (const { repo } of repos) {
      try {
        for (const status of ['queued', 'in_progress']) {
          for (const run of await this.list(`/repos/${repo}/actions/runs?status=${status}`, 'workflow_runs')) {
            for (const job of await this.list(`/repos/${repo}/actions/runs/${run.id}/jobs`, 'jobs')) {
              if (job.status === 'queued') this.add(repo, job);
              else await this.end(job.id, job.status === 'completed');
            }
          }
        }
        for (const job of this.rows('SELECT id FROM jobs WHERE repo=?', repo)) {
          const response = await this.gh(`/repos/${repo}/actions/jobs/${job.id}`);
          if (!response.ok && response.status !== 404) throw new Error('Job lookup failed');
          const current: Row = response.status === 404 ? { status: 'gone' } : await response.json();
          const ended = current.status === 'queued' && await this.runEnded(repo, current.run_id);
          if (current.status !== 'queued' || ended) {
            await this.end(job.id, current.status === 'completed');
            if (ended) console.info(JSON.stringify({ event: 'boat.queue.retired', job: job.id, run: current.run_id, reason: 'run-ended' }));
          }
        }
      } catch { errors++; }
    }
    this.rows('DELETE FROM ended WHERE seen<?', Date.now() - 172_800_000);
    this.rows('DELETE FROM boxes WHERE seen<?', Date.now() - 172_800_000);
    if (errors) throw new Error(`${errors} reconciliation failures`);
    return { ok: true };
  }
}
