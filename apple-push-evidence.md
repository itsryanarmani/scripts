# Check Apple pushes on a local Mac

Use an existing Mac to check a remote branch without a paid CI runner.
The command runs once. A local scheduler can call it again.
It invokes Git, XcodeGen, and `apple-build-evidence`.
It does not invoke signing, upload, submission, or release tools.

Use this only with trusted source repositories and project hooks.
XcodeGen and Xcode execute code from the selected repository.

## Prepare a dedicated clone

Keep this clone separate from interactive development.
Use an existing Git login. Do not put credentials in the remote URL.

```sh
git clone --branch main git@github.com:example-owner/example-repo.git /private/path/apple-source
printf 'apple-push-evidence\n' > /private/path/apple-source/.git/apple-push-evidence-owned
```

The marker gives this command permission to move the clone to a detached commit.
The command rejects linked worktrees and dirty checkouts.
It does not reset, clean, or force checkout files.
Use a clone that can generate its project without changing tracked source.

Install `apple-push-evidence` beside `apple-build-evidence`.
Prepare the external evidence config described in `apple-build-evidence.md`.
Include every source, test, generator, configuration, and catalog input.
Do not include mutable build output in the source inputs.
Select explicit simulator destinations that exist on this Mac.

Create another private config:

```json
{
  "repository": "/private/path/apple-source",
  "branch": "main",
  "projectSpec": "apps/example/project.yml",
  "evidenceConfig": "/private/path/apple-evidence.json",
  "output": "/private/path/apple-push-results"
}
```

Keep both configs and the output outside the clone.
The output directory must permit access by its owner only.

```sh
mkdir -p /private/path/apple-push-results
chmod 700 /private/path/apple-push-results
apple-push-evidence /private/path/apple-push.json
apple-push-evidence /private/path/apple-push.json --execute
```

Plan mode checks local configuration and Git state.
It does not fetch, generate, build, or write artifacts.
Execute mode fetches the branch and selects the fetched commit.
It generates the project, then runs the existing evidence command.
Failed generation prevents tests and archive creation.

The evidence runner checks its input fingerprint and retained artifacts.
An unchanged result reuses valid evidence; it is not a new test pass.
No build number is allocated. Configure build identity through the evidence config.

Each execution keeps private phase logs and a JSON summary.
Exit 0 means planned, passed, or unchanged. Inspect the JSON status.
Exit 1 means rejected or failed. Keep the failure artifacts.

## Local scheduling

A LaunchAgent can call the execute command with a `StartInterval` of 300 seconds.
Use absolute command and config paths in `ProgramArguments`.
Set its `PATH` to include XcodeGen and the required local tools.
Check existing agents before adding one. Do not install a second watcher for the same clone.

This command does not install or change a scheduler.
A logged-out or sleeping Mac does not provide continuous build service.
Do not add wake settings or paid runners to compensate without authorization.

## Verify orchestration

```sh
APPLE_PUSH_TEST_PROOF=/private/path/proof.json python3 apple-push-evidence.test.py
```

The test makes real Git commits and pushes to a temporary bare remote.
It uses fake XcodeGen and evidence commands.
It verifies orchestration and rejection paths, not an actual Apple build.
Run `apple-build-evidence` with real simulator tests before relying on a release candidate.
