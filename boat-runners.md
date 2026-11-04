# Boat runner pool

For cost audits, safe drains, and development versus production scheduling,
read [Reduce CI cost without blocking delivery](ci-cost-controls.md).
GitHub Actions can schedule this pool without the native Boat CI integration.

Run `boat-pool` on the owner's Mac with `gh` authenticated and the Box CLI at
`~/.ascii/bin/box`. Install the broker from #508 first. Set `BROKER_URL`,
`POOL_TOKEN` and (for hooks) `WEBHOOK_SECRET` in the operator shell; never commit
those values. The service needs only the pool token, not the GitHub token.

- `./boat-pool up boat 1 --dry-run` shows provisioning without creating a Box.
- `./boat-pool up boat 1` creates a default 4-vCPU Box; `boat-8` uses large.
  Creation is serial. The named environment injects no account credentials,
  and each Box uses `--no-env --no-auto-stop`. Non-null or missing
  `archiveAfter` stops provisioning. A failed install reports the Box ID for
  inspection or deletion; it never silently creates another Box.
- `./boat-pool status` reads pool Boxes, agent state and broker counts.
- `./boat-pool heal --dry-run` inspects existing Boxes and plans replacements
  for inactive agents. Omit dry-run to replace them, then remove the old Boxes.
- `./boat-pool down bx_<id>` stops and deletes only a named pool Box.
- `./boat-pool hooks --dry-run` lists private, non-archived owner repos.
  Omit dry-run to create/update matching webhook URLs; this affects all listed
  repositories. Repo privacy is checked again immediately before mutation.

Provisioning downloads runner v2.338.0 onto the standard Boat image and installs
`boat-runner-agent` at `/usr/local/bin`. `/etc/boat-runner.env` has mode 0600,
transferred through SSH stdin. The service runs as `user` with `Restart=always`.
Inspect it with `systemctl status boat-runner-agent` and
`journalctl -u boat-runner-agent`. Runner output is in
`/home/user/actions-runner/boat-runner.log`.

The agent persists each lease before launch. After a runner exits or a service
restart it reports done before taking another lease. Failed reports retry every
five seconds. An idle runner stops after 180 seconds; a job-start hook disables
that idle timer. Cleanup removes `_work/<repo>`, force-removes containers created
after the lease start, and uses noninteractive sudo to remove new `/tmp` entries
with modification times after that start, owned by `user` or root. A persisted
snapshot preserves pre-existing `/tmp` entries even when a job modifies them;
symlinks are removed without following their targets. On these dedicated pool
Boxes, new temporary entries and containers from the same users during a lease
are treated as job resources. Cleanup errors are logged without blocking the
next lease. Older lease files without cleanup metadata skip temporary/container
cleanup. Cleanup retains `_work/_tool`, Bun, Playwright and Docker images.
Docker image pruning runs once a day.
Broker/GitHub outages delay work until lease cleanup is acknowledged.

## Switch the runner in one place

Workflows should not hard-code a provider. Use a repository variable with a default:

- `runs-on: ${{ vars.CI_RUNNER || 'boat' }}` for ordinary jobs.
- `runs-on: ${{ vars.CI_RUNNER_LARGE || 'boat-8' }}` for heavy builds.

To move a repository to another provider, set `CI_RUNNER` (and `CI_RUNNER_LARGE`).
No workflow edit is needed. An unset variable falls back to the Boat label.

`./ci-runner-indirect [--write] <repo-dir>...` rewrites literal `boat`, `boat-8` and
`ubuntu-*` labels. It prints one `name<TAB>count` line per repo. Without `--write` it only counts.

The script skips these on purpose:

- macOS and Windows labels, `matrix` values, list values and existing expressions.
- Lines inside `run: |` block scalars.
- `-arm` labels such as `ubuntu-24.04-arm`.
- JSON-style `"runs-on": "boat"` keys. Fix those by hand.

A job that must stay hosted (a secret-heavy deploy, an alert, a `gitleaks-action` scan) needs
`ubuntu-latest` put back after the rewrite. Tests that assert the literal label need the
expression instead. Edits under `.github/workflows` may need a human-applied policy label.
Run `actionlint` on each changed workflow before you push.

