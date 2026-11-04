# vm-orchestrate failure modes

`vm-orchestrate` hands long work to a headless agent on a VM that you reach over
SSH, so the work goes on after the laptop goes offline. `start` copies a bundle
(`BRIEF.md`, helper files, a mode-600 `secrets.env`) to `~/orch` on the VM and
starts a detached runner. The runner restarts the agent each round until
`~/orch/DONE` exists or the round cap is hit. Every round tells the agent to read
`BRIEF.md`, then `STATUS.md`, and continue.

This file lists every way the tool can fail. The tests in
`vm-orchestrate.test.sh` cover each row marked "tested".

| # | Failure | Wanted behavior | Tested |
|---|---|---|---|
| 1 | No SSH command is given (no `--ssh`, no `VM_ORCHESTRATE_SSH`). | Exit 2 before any remote call. | yes |
| 2 | The subcommand is missing or unknown. | Print usage, exit 2. | yes |
| 3 | The bundle has no `BRIEF.md`. | Exit 2 before any remote call. | yes |
| 4 | The bundle has no `secrets.env`, or its mode is not 600. | Exit 2 before any remote call. A readable secrets file on the laptop is already a leak. | yes |
| 5 | A runner is already alive on the VM. | Exit 1 and upload nothing, so two runners never race on one `STATUS.md`. | yes |
| 6 | macOS tar adds `._*` AppleDouble files and extended-attribute headers. | Tar with `COPYFILE_DISABLE=1` and `--no-xattrs` when tar has it, then delete `._*` on the VM. | yes |
| 7 | A secret value ends up in a command line, where `ps` and shell history can read it. | Upload every file through SSH stdin. No file content is ever an argument. | yes |
| 8 | The SSH session that started the runner ends, and the runner dies with it. | Start the runner with `setsid nohup`, with every file descriptor redirected, and return at once. | yes |
| 9 | The runner dies at once, for example because `secrets.env` has a bad line. | `start` checks the runner after a few seconds. If it is gone and its `result` file says failed, print that result and exit 3. The result names the line number, never its content. | yes |
| 10 | The agent stops early, crashes, or exits non-zero. | Log the exit code and start the next round. The next agent resumes from `STATUS.md`. | yes |
| 11 | The agent finishes the goal. | It writes `~/orch/DONE`. The runner checks before each round and stops. | yes |
| 12 | The agent never finishes. | Stop after `--rounds` rounds (default 40). | yes |
| 13 | SSH fails because the laptop's public IP changed and the VM firewall only allows the old one. | Exit 4 and say to check the allowlist for the current public IP. Detached runners keep working meanwhile. | yes |
| 14 | `status` shows the secrets file. | `status` prints the runner state, `runner.log`, the tail of `STATUS.md` and the `DONE` state. Nothing else. | yes |
| 15 | `add-goal` pipes the goal into an interpreter that reads its program from a heredoc, so stdin carries the program and the goal text is lost. | Upload the goal as a file, then insert it with awk reading that file by path. | yes |
| 16 | The goal text holds quotes, `$`, or backticks. | It lands in `BRIEF.md` byte for byte, before the `## Rules` heading. | yes |
| 17 | `BRIEF.md` has no `## Rules` heading. | Append the goal at the end. | yes |
| 18 | The goal file is missing or empty. | Exit 2 before any remote call. | yes |
| 19 | `stop` kills by process name and takes out other agents on the VM, or the SSH session itself. | Kill only the PIDs in `runner.pid` and `agent.pid`. | yes |
| 20 | `gh` is not installed on the VM, so an agent that must open PRs fails late. | `start` prints a warning when `gh` is missing. | yes |
| 21 | The VM's TTL or idle timeout is shorter than the job, and the provider reaps it mid-run. | Not detectable through SSH alone. `start` prints a reminder to give the VM a lifetime longer than the job. | no, by design |
| 22 | Two `start` calls race: both see no live runner and both launch. | `start` creates `.lock` with shell noclobber (`O_EXCL`) before it uploads anything. The runner holds the lock for its life. The loser exits 1. | yes |
| 23 | A lock is left without a runner (a start that died mid-upload, or a killed VM). | `start` exits 1 and says to run `stop`, which clears the lock. Nothing guesses that a lock is stale. | yes |
| 24 | A finished job leaves `DONE`, so the next job in the same folder stops before its first round. | After it takes the lock, `start` removes `DONE` and `result` before it unpacks the new bundle. `STATUS.md` carries over; ship an empty one in the bundle to start fresh. | yes |
| 25 | A short job finishes inside the start check, so a missing runner reads as a crash. | The runner writes `result` (`finished` or `failed: ...`) before it exits. `start` exits 0 on `finished`. | yes |
| 26 | `--dir` holds shell syntax and runs commands on the VM, because it is spliced into remote command strings. | Accept only a relative path of letters, digits, `.`, `_` and `-`, with no `..`. Exit 2 before any remote call. | yes |
| 27 | The VM's umask is permissive, so other users can read the brief, logs and status. | Every remote write runs under `umask 077`, and so does the runner. | yes |
| 28 | The agent writes a credential into `STATUS.md` or a log, and `status` prints it. | `status` hides any line that holds a `secrets.env` value or looks like a credential (`token:`, `api_key=`, key prefixes, PEM headers). | yes |
| 29 | `secrets.env` holds commands, and sourcing it runs them on the VM. | The runner reads it as data: `KEY=VALUE` lines, optional `export `, values taken literally with one pair of quotes stripped. Any other line stops the runner with its line number. | yes |
