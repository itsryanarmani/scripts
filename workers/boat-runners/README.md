# Boat runner broker

Run `npm ci && npm run typecheck` here. Set `APP_ID`, `APP_INSTALLATION_ID`, `APP_PRIVATE_KEY` (PKCS#8 PEM of the
`pooriaarab-boat-runners` GitHub App), `WEBHOOK_SECRET`
and `POOL_TOKEN` in an ignored `.dev.vars` for `npm run dev`. Production secrets
use `wrangler secret put`; deployment is an operator action.

Register a `workflow_job` hook to `/webhook` on private `itsryanarmani` repositories.
Only `boat`, `boat-8`, and `boat-deploy` jobs enter the queue. Public repositories are ignored.
Use `Authorization: Bearer <POOL_TOKEN>` for these endpoints:

- `GET /lease?label=boat&box=<id>`: waits up to 25 seconds; 204 means empty.
  A 200 contains `lease_id`, `job_id`, `repo`, `label`, `runner_id` and
  `encoded_jit_config`. Run `run.sh --jitconfig <encoded_jit_config>` once.
- `POST /done`: send the lease response, including `lease_id`, `runner_id`,
  and `repo`. Repeat on 502; 200 also covers an already removed runner.
- `GET /status`: open/claimed counts and recently seen boxes for each label.

Deployment jobs can use the exclusive `boat-deploy` label. Large pool agents
still request `boat-8`; the broker serves at most two `boat-deploy` claims
before an eligible ordinary `boat-8` claim. Each class keeps FIFO order.
The issued JIT runner receives only the selected job's label. An E2E job
cannot take a deployment runner. Standard-tier jobs keep FIFO order.
Running jobs continue. This policy adds no machines and removes no checks.
Deploy job names alone do not grant priority. Use the exclusive label.

One SQLite Durable Object stores atomic claims, independent runner leases and
terminal event tombstones. Cron every two minutes expires queued claims after
three minutes, retries runner deletion and recovers missed jobs for repositories
seen within 48 hours. It paginates queued and in-progress runs and rechecks privacy.
A missed event from a repository never seen by the broker cannot be recovered;
register hooks before starting jobs. A GitHub outage delays cleanup and recovery.
Interrupted mint requests retain their unique runner name for orphan cleanup.
