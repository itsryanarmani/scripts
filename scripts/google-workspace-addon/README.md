# google-workspace-addon — build, deploy, and publish a Workspace add-on

A Google Workspace add-on is server-side **Apps Script + CardService** running in the
Docs/Sheets sidebar — no push-CLI submission either; you point the Marketplace SDK at a
versioned deployment ID in the Google Cloud console. This is the playbook: the command
sequence from `integrations/<addon>/` to published, plus the traps that each cost a
round-trip. The concept-level skill is `google-workspace-addon` in `itsryanarmani/skills`.

## Flow

```bash
npm install -g @google/clasp
clasp login
cd integrations/<addon>                 # .gs sources + appsscript.json
clasp create --type standalone --title "<App name>"
# or bind an existing script: .clasp.json with {"scriptId": "...", "rootDir": "."}
clasp push                              # uploads appsscript.json + all .gs files
clasp open                              # opens the Apps Script editor
```

Test it in the Apps Script editor:
1. **Deploy → Test deployments** → Google Workspace Add-on → pick Docs/Sheets → **Install**.
2. Open a Doc or Sheet — the add-on icon appears in the right sidebar.

Prepare the production deployment:
3. **Project Settings → Google Cloud Platform (GCP) Project → Change project** — switch
   from the default (hidden) project to a standard GCP project you own.
4. **Deploy → New deployment → Add-on** → copy the **deployment ID**.

Then in `console.cloud.google.com` (the standard project):
1. **OAuth consent screen** (External) — add the exact scopes from `appsscript.json`.
2. **Enable the Google Workspace Marketplace SDK.**
3. **App Configuration tab:** check Google Workspace Add-on + hosts, paste the deployment
   ID, fill developer name/website/support email, visibility **Public**.
4. **Store Listing tab:** name, descriptions, 128×128 icon, 220×140 tile card, 1280×800
   (or 640×400) screenshots, category, pricing, ToS + privacy-policy URLs.
5. **OAuth verification** (public + sensitive scopes): submit from the consent-screen page
   with a demo video of the add-on flow — the heavy gate, days to weeks.
6. **Publish.** Review takes days. Visibility **Private** skips verification + review.

## Traps (each = one round-trip)

- **No `fetch`** — `UrlFetchApp.fetch` only, synchronous, no async/await. Needs the
  `script.external_request` scope, your origin in `urlFetchWhitelist`, and
  `muteHttpExceptions: true` (or non-2xx throws and you lose the error body).
- **oauthScopes must match** manifest ↔ OAuth consent screen ↔ code. Prefer
  `.currentonly` host scopes; full `documents`/`drive` scopes trigger restricted-scope
  verification.
- **Triggers return Cards, handlers return ActionResponses** — `homepageTrigger` →
  `newCardBuilder()…build()`; button handlers → `newActionResponseBuilder()…build()`.
  The wrong type fails the sidebar silently.
- **Keys in `PropertiesService.getUserProperties()`** (per-user) — never script
  properties, which are shared across all users.
- **The Marketplace points at a versioned deployment ID** — `clasp push` alone doesn't
  reach users; create a new deployment version.
- **The default GCP project can't be fully configured** — switch to a standard project
  before touching the consent screen or Marketplace SDK.

## Files

`example.gs` (next to this README) — the smallest real wiring: a homepage card with an
API-key settings form, and a save handler that validates the key against your API with
`UrlFetchApp` and stores it in user properties. Copy it as a starting point.
