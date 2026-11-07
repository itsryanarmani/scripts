# Record Apple build evidence locally

Run simulator tests and create an unsigned device archive on an existing Mac.
This command never exports, signs, uploads, submits or releases an app.
It does not install tools or provision runners.

## Inputs

Use Python 3, Git, Xcode and an existing generated Xcode project.
Generate the project with the repository's normal command first.
Keep the source checkout clean and store evidence outside that checkout.

Create a private JSON config:

```json
{
  "repository": "/absolute/path/to/repo",
  "project": "apps/example/Example.xcodeproj",
  "scheme": "Example",
  "inputs": ["apps/example/Sources", "apps/example/Resources", "apps/example/UITests", "apps/example/project.yml"],
  "destinations": ["platform=iOS Simulator,id=YOUR-SIMULATOR-ID"]
}
```

Include every source, data, test and build configuration input.
Use one explicit destination per tested configuration.
Check simulator runtime compatibility before choosing destinations.

```sh
./apple-build-evidence /private/path/config.json --output /private/path/evidence
./apple-build-evidence /private/path/config.json --output /private/path/evidence --execute
```

The first command plans without writing files or running Xcode.
The second locks the output directory, tests each destination, then archives.
A failed test prevents the archive phase.
A clean exit requires result bundles, an archive and stable source inputs.

Each run stores private logs, result bundles, an archive and summary.json.
The summary includes source commit, fingerprint, phase results and durations.
success.json records the last successful evidence run.
An unchanged fingerprint skips later execution only while its archive and test bundles remain.
Use a new output directory when toolchains, runtimes or external dependencies change.
The fingerprint does not model those external changes.

Exit 0 means planned, unchanged, or passed; inspect the JSON status.
Exit 1 means rejected or failed. Keep failure artifacts for diagnosis.
An unchanged result is not a new test run.
Do not delete artifacts referenced by success.json.

Xcode logs can include private project information. Do not attach them publicly without inspection.
An unsigned archive is not TestFlight-ready. Signing and authorized upload remain separate steps.

## Verify the command

```sh
APPLE_BUILD_TEST_PROOF=/private/path/cli-proof.json python3 apple-build-evidence.test.py
```

These CLI scenarios use fake Xcode tools and real subprocesses in a temporary Git repository.
They prove orchestration behavior; they do not prove an Apple build or App Review approval.
