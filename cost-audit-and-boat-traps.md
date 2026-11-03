# Cost audit and Boat traps

Rules from a Cloudflare cost audit and a Boat worker fan-out on 2026-11-03.
Each item says what went wrong, why, and the rule that stops a repeat.

## A. Cost audit method

1. Do not add up daily rows from the billable-usage feed. The feed holds
   cumulative rows, and those rows overlap. A per-day sum looked like $20 to
   $180 a day and meant nothing. Use the latest cumulative row for each
   service, subscription, zone, and billing period. Report a dollar figure
   only from that reduction.
2. Keep measured and target apart. A plan estimate is not a saving. Show two
   columns. Never call a target a measured saving.
3. Price the meter before the fix. One KV write costs about as much as 5,000
   D1 rows read. A cache that writes once per long-tail key can cost more
   than the query it saves. Compute dollars per unit first. Then pick the fix.
4. Facet count scans, per-request server render, and visitor cache writes
   drive the bill. Fix in this order: pause the costly search, stop staging,
   precompute the counts, serve static pages, then add one budget guard in
   front of HTTP, the CLI, and MCP.
5. Put the guard at the shared entry point. Every interface reaches it, so
   one limit covers every path.
6. The billing feed lags. It had no data after the change. Wait for new data
   before you claim a saving.

## B. Boat boxes

1. `boat env list` prints secret values. Never run it raw in an agent
   session. Select names only. Pipe the output to a script that prints the
   `name` fields.
2. `boat env add-repo` changes the environment. A probe that adds a repo
   leaves it there. Probe in a throwaway environment, then delete it.
3. The connected-repo list can be stale. Boat showed 130 of 338 repos and
   rejected newer ones with "not found in your connected GitHub repos".
   Open the dashboard, then Environment, then GitHub repositories, then Add
   Repository, then Refresh. A new login and a change to GitHub app
   permissions did not help.
4. A box made with `--from <snapshot>` skipped environment injection. It had
   no GitHub login and no repo clone. A box made without `--from` had both.
   Test a snapshot path with a canary box before you rely on it.
5. `boat-hub warm` hid the clone error (`|| true`, output sent to
   `/dev/null`) and then waited five minutes. Capture the error and print it.
   Check `gh auth status` in the box before that wait. Stop on failure.
6. Agent logins inside a box expire. One agent was at its usage limit,
   another token had expired, and a third agent could not refresh. A queued
   prompt stays "queued" with no process and no error. Run a one-word canary
   prompt first. Check that an agent process exists. Then fan out.
7. Check the trial limits and the wallet (`boat onboard --json`) before you
   make several boxes.
8. Delete idle boxes. They bill the wallet.

## C. Shell and delegation traps

1. `set -- $var` does not split in zsh. Pass explicit arguments, or use
   `${=var}`.
2. `PATH` differs in background shells. `gh` and `boat` were not found.
   Export `PATH` in the command.
3. A delegate task runs in the thread's own project. From a scratch folder
   with no repo it cannot make a worktree. Make the worktrees yourself. Run
   the worker CLI there.
4. Judge a worker on its diff and its pull request, not on its exit code.
