# figma-plugin — build, run, and publish a Figma plugin

A Figma plugin is two programs over `postMessage`: `code.js` in the plugin sandbox
(no DOM, but no CORS) and `ui.html` in an iframe (full DOM, but CORS applies),
declared in `manifest.json` alongside `networkAccess.allowedDomains`. There is no
publish CLI — submission happens in the Figma desktop app / Community site. This is
the playbook: the command sequence from `integrations/<plugin>/` to published, plus
the traps that each cost a round-trip. Concept-level skills in `itsryanarmani/skills`:
`figma-plugin` (build) and `figma-plugin-submission` (Community publish).

## Flow

```bash
cd integrations/<plugin>         # plugin source (src/, manifest.json, assets/)
npm install
npm run build                    # esbuild: src/code.ts -> code.js; src/ui.ts bundled + inlined into ui.html
npm run watch                    # rebuild on change
npm run typecheck
```

Then in the Figma desktop app:
1. If `manifest.json` has no `id`: **Plugins → Development → New plugin… →
   Figma design → Empty**. Copy `id` from the scaffold manifest into yours.
   Remove both entries in **Manage plugins**. Then import yours (step 2).
2. **Plugins → Development → Import plugin from manifest…** → select `manifest.json`.
3. Run it: **Plugins → Development → \<plugin name\>**.
4. Store the API key through the plugin's own settings UI — it lands in
   `figma.clientStorage`, sandbox-side, and never enters the iframe. This
   throws `Cannot access client storage without a plugin ID` if step 1 was skipped.

## Publish

1. `npm run build` and smoke-test: select frame → export → API round trip.
2. **Plugins → Development → Manage plugins → Publish**
   (or `figma.com/community` → **Publish plugin**).
3. Confirm `"id"` is already in `manifest.json` (minted in Flow step 1). That ID
   is the published listing's ID. Publish from the re-imported plugin, not the
   New-plugin scaffold — the scaffold is empty.
4. Fill the listing: name, **128×128** icon, **1920×1080** thumbnail (not 1920×960;
   keep content inside the `1800×1080` safe area). Flatten both onto the brand
   field so neither carries alpha. Description (state that an API key is required
   + where to get one), tags, support URL.
5. **Publish** → Figma review before it appears in Community search. No published SLA; real
   waits run days to a few weeks (verify). Decision arrives by email to your Figma account.
   (portal-review, free — no publish CLI.)

## Traps (each = one round-trip)

- **Fetch in the wrong context** — the #1 "request fails" cause. The sandbox has no
  CORS; the iframe has full CORS. If your API sends no CORS headers, the fetch
  belongs in `code.js`, never in the UI.
- **`networkAccess.allowedDomains`** — every external origin (API, upload CDN,
  image/thumbnail hosts) listed exactly, with scheme; `reasoning` is required.
  Missing = runtime failure, not build failure.
- **No `FormData`/`Blob` in the sandbox** — hand-roll multipart bodies with
  `TextEncoder` + `Uint8Array` (see `example.ts`).
- **UI = one self-contained HTML file** — the build inlines the JS bundle into
  `ui.html` via a placeholder; no external scripts unless allow-listed.
- **Export is async** — `await node.exportAsync(...)` returns a `Uint8Array`.
- **`figma.clientStorage` throws without a plugin ID** — exact error:
  `Cannot access client storage without a plugin ID`. `manifest.json` has no `id`
  until you mint one. **Plugins → Development → New plugin… → Figma design →
  Empty**, copy `id` into yours. Also degrade: hold the key in sandbox memory for
  the session and tell the user it will not persist; do not hard-fail.
- **Minting an ID creates a second dev plugin** — the scaffold and your import
  are separate Manage-plugins entries. Remove both, re-import yours (now with the
  ID), publish from that one. Publishing the scaffold ships an empty plugin.
- **Thumbnail is 1920×1080, not 1920×960.** Icon is 128×128. Flatten both onto
  the brand field so neither carries alpha.
- **`editorType`** — declare only the editors the plugin supports; reviewers check.

## Files

`example.ts` (next to this README) — the smallest real wiring: sandbox-side frame
export → hand-rolled multipart upload → API call, driven by a `postMessage` intent
from the UI. Copy it as a starting point.
