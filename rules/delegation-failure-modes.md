# Delegation failure modes

These failures came from one day of parallel work. Each brief line prevents a repeat.

## Shared Git identity

Symptom: Every worker commits with a placeholder author. A squash merge would add
an unwanted `Co-authored-by` trailer.
Cause: A test runs `git config user.name` in a worktree. Worktrees share `.git/config`.
Brief: “Test in a temporary repository. Pass identity per command with `git -c`.
Never write Git configuration in a worktree.”

## Shared hooks

Symptom: An unmerged hook installer blocks every other worker’s push.
Cause: The installer puts symlinks in the shared hooks folder.
Brief: “Test hook installers only in a throwaway clone with a temporary HOME.”

## Local file dependencies

Symptom: A fresh worktree cannot build, or it builds against stale sibling code.
Cause: The sibling dependency is missing, symlinked, or checked out on an old branch.
The bundler rejects a symlink outside its root.
Brief: “Use a clean clone of the sibling’s default branch. Make a real copy of
any required `file:` dependency. Never commit that copy.”

## Claim identity mismatch

Symptom: The branch guard rejects a worker’s own claim.
Cause: The worker overrides its identity with a shell environment variable.
The guard runs in the harness process and cannot see that variable.
Brief: “Claim with the identity that the guard detects. Do not override it
with an environment variable set in your own shell.”

## Dead worker claims

Symptom: A dead worker’s claim blocks its replacement.
Cause: The claim remains active. Editing a lock file leaves the GitHub claim behind.
Brief: “Confirm the worker stopped. Use the presence tool’s `release` command
with the dead worker’s identity. Never edit lock files.”

## Missing review verdict

Symptom: A review child ends its turn without a verdict.
Cause: It waits for a background command, then never returns to write the result.
Brief: “Run review commands in the foreground. Write the verdict in the same turn.”

## Merge approval drift

Symptom: An automation account labels its own PR and merges a newer head than it approved.
Cause: The account clears its own gate and uses approval from an older commit.
Brief: “Never label your own PR to clear a gate. Re-read the head immediately
before every merge. Confirm approval covers it. Pass `--match-head-commit`.”

## Usage limits

Symptom: A worker stops mid-task when it reaches a usage limit.
Cause: The task depends on one live session and has no handoff state.
Brief: “Keep the issue, branch, and claim recoverable. Record the last completed
step and next command so another worker can resume through another route.”

## Projected savings

Symptom: A claimed CI saving later becomes a net loss.
Cause: Estimates omit restore cost, queue time, or the real runner’s behaviour.
One projected saving was revised downward twice and then measured as a loss.
Brief: “Quote only measured numbers. Keep projections separate from results.”
