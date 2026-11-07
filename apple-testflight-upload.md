# Upload a tested archive to internal TestFlight

This local command signs and uploads through Xcode using existing private credentials.
It never submits App Review or releases an App Store version.
It does not create keys, certificates, apps, testers or paid runners.

Use Python 3, Git and an authenticated Xcode distribution workflow.
First run `apple-build-evidence --execute` and retain its successful summary and archive.
Use the real summary.json, not console output from an unchanged run.
The command trusts its source metadata; it is not a signed attestation of tested archive bytes.
Use an unchanged archive from the trusted local build workflow.

Create a private signing config with absolute paths:

```json
{
  "keyId": "YOURKEYID",
  "issuerId": "00000000-0000-0000-0000-000000000000",
  "privateKeyPath": "/private/path/AuthKey.p8"
}
```

The config and key must deny group and other access, such as mode0600.
Keep both outside Git. The command passes the key path to Xcode without reading key material.
Cloud signing requires appropriate certificate access; an upload-only role may be insufficient.
Do not silently broaden an API key's role to fix a permission failure.
See [Apple cloud signing](https://developer.apple.com/help/account/certificates/cloud-managed-certificates/).

Provide a trusted export plist with method `app-store-connect` and valid signing settings.
Use only the signing keys your workflow needs, such as `signingStyle` and `teamID`.
Other supplied plist keys pass through to Xcode.
The command forces destination `upload` and `testFlightInternalTestingOnly=true`.
It rejects an explicit false internal-only flag.
[Apple limits these builds to internal testing](https://developer.apple.com/help/app-store-connect/test-a-beta-version/add-internal-testers/).
Use a new candidate for later external testing or public review.

```sh
./apple-testflight-upload /private/evidence/summary.json \
  --bundle-id com.example.app \
  --signing-config /private/signing.json \
  --export-options /private/ExportOptions.plist \
  --state /private/upload-state/receipt.json \
  --known-build-floor 1
```

The default is a plan. It writes nothing and contacts no Apple service.
A plan does not enforce the Apple build floor; execute checks that floor under the state lock.
A plan does not prove account access, processing readiness or a successful upload.
Add `--execute` only when internal testing is authorized.
Use a private state directory outside Git, such as mode0700.
The command checks bundle identity, passed evidence and increasing integer build numbers.
Set the floor to the highest build confirmed in App Store Connect before the first upload.
The command does not discover Apple's current highest build automatically.
The candidate must exceed both that floor and the local successful build record.
Repeated successful candidate bytes return unchanged without another upload.
Reusing the same bundle/version/build with different archive bytes is rejected.
Symlinked archives are unsupported.

A pending receipt is persisted before Xcode starts. Any ambiguous failure blocks later uploads for that app.
Never delete pending state to force a retry. First verify the build in App Store Connect.
If accepted, reconcile the record as uploaded with the matching identity and archive hash.
If Apple confirms no upload, preserve the evidence and remove only that pending record.
Reconciliation is manual in this version; automatic server reconciliation and push watching are not implemented.

Exit0 means planned, unchanged or uploaded; inspect the JSON status.
Exit1 means rejected or upload-unknown. Exit2 means blocked-pending.
Uploaded means Xcode accepted the upload, not that processing or tester installation completed.
Keep private Xcode logs and receipts outside public PR attachments.

## Verify orchestration

`APPLE_UPLOAD_TEST_PROOF=/private/proof.json python3 apple-testflight-upload.test.py`

The eleven CLI scenarios use fake Xcode subprocesses. They perform no real Apple upload.
