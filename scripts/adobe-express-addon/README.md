# adobe-express-addon — build, run, and submit an Adobe Express add-on

An Express add-on is a React panel on the **Adobe Add-on SDK** running in a sandboxed
iframe inside Adobe Express. Submission is a package upload in the **Adobe Developer
Distribution** portal (no push CLI). This is the playbook: the command sequence from
`integrations/<app>/` to submitted, plus the traps that each cost a round-trip. The
concept-level skill is `adobe-express-addon` in `itsryanarmani/skills`.

## Flow

```bash
cd integrations/<app>                 # add-on source (src/, manifest.json, assets/)
npm install
npx @adobe/ccweb-add-on-scripts start # HTTPS local preview; load it inside Express (add-on dev mode)
# ... build the React panel against addOnUISdk ...
npm run build                         # produces the bundle
npm run package                       # dist.zip — manifest.json must be at the zip root, ≤50 MB
```

Then **inside Adobe Express** (Add-ons → **Manage add-ons**; enable Add-on
Development first) — **portal-review**, no submit API. Adobe hosts the zip.
1. Create a new add-on listing (name ≤25 chars, unique).
2. **Public listing** tab → upload `dist.zip`. Required: 50-char summary, 1000-char
   description, **help URL**, **support email**, **144×144** icon (auto-resized to
   36/64/144), **≥1 screenshot at 1360×800** (up to 5). Optional privacy-notice +
   EULA URLs. First-time: **250×250** publisher logo + EU trader info.
3. Declare generative-AI usage + monetization model (checkout is outside Express).
   Give review test credentials (with credits) if the add-on gates features.
4. Submit. Private-link path skips review: zip + 144×144 icon + release notes →
   copy the link; promote to public later. Target review ~10 business days.
   Contact: `ccintrev@adobe.com`.

## Traps (each = one round-trip)

- **Iframe blocks un-allow-listed fetch** — declare every external origin (incl. `localhost`) in the manifest allow-list, or the request dies at runtime with a vague network error.
- **Export is async, multi-part** — `addOnUISdk.app.document.createRenditions(...)` returns a Promise of blobs; handle multi-page output.
- **Manifest permissions must match usage** — under-declare and it breaks at runtime; over-declare and review slows.
- **A fresh reviewer must authenticate from a clean state** — self-service auth in the panel.

## Files

`example.ts` (next to this README) — the smallest real wiring: export the current
design, upload the rendition, create the downstream action.
