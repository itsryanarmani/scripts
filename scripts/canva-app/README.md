# canva-app — build, run, and submit a Canva app

A Canva app is a React app on the **Canva Apps SDK** running in an iframe inside the Canva
editor. There is no push CLI for submission — you upload a built bundle in the Developer
Portal and fill the listing there. This is the playbook: the command sequence from
`integrations/<app>/` to submitted-for-review, plus the traps that each cost a round-trip.
The concept-level skill is `canva-app` in `itsryanarmani/skills`.

## Flow

```bash
export PATH="/opt/homebrew/opt/node@20/bin:$PATH"   # see the Node note below
cd integrations/<app>
npm install
npx @canva/cli apps link            # writes CANVA_APP_ID into .env from the portal
npx @canva/app-scripts dev          # dev server
npx @canva/cli apps preview         # opens the running app in a new Canva design

# before every submit, in this order:
npx tsc --noEmit                    # the bundler does NOT typecheck -- run it yourself
npx eslint src                      # Canva's own rules; see the plugin setup below
npx @canva/app-scripts build        # -> dist/app.js  (cleans dist/ first!)
npx @canva/app-scripts extract-translations   # -> dist/messages_en.json  (AFTER build)
npx @canva/cli@latest apps doctor   # pre-submission check
```

**Order matters on the last two.** `build` cleans `dist/`, so generating the translation
file first silently deletes it. If the upload page says the JSON is missing, this is why.

**`@canva/cli` has no `build` and no `start`.** Its whole surface is
`create/list/link/preview/doctor/migrate/config`; both build and dev live in
`@canva/app-scripts`. A `package.json` with `"build": "@canva/cli apps build"` looks
plausible, fails, and — because the build never runs — hides every type error in the app.

**Node:** `@canva/app-scripts` declares `node>=22` but builds fine on 20, and the sibling
marketplace CLIs (`vsce`, `ovsx`, Coda `packs`) segfault on 22+. Pin 20 for all of them and
ignore the EBADENGINE warning.

## Set up Canva's lint before you need it

`apps doctor` runs your `lint` and `format:check` scripts and **skips them silently if they
are not defined**, so an unconfigured project passes doctor while failing review.

```bash
npm i -D @canva/app-eslint-plugin "eslint@^9.23.0" prettier
```

`eslint` must be `^9` — the plugin peers on `^9.23` and will not resolve against 10.

```js
// eslint.config.mjs
import canva from "@canva/app-eslint-plugin";

export default [
  ...canva.configs.apps,
  {
    rules: {
      // Canva's shared config assumes the starter kit's Jest setup. Without a jest
      // install this rule cannot read a version and fails to LOAD, taking the whole
      // run with it. The other jest/* rules just never match a file.
      "jest/no-deprecated-functions": "off",
    },
  },
];
```

```json
"scripts": {
  "lint": "eslint src",
  "format:check": "prettier --check src",
  "format": "prettier --write src"
}
```

Two rules map onto rejection reasons: `formatjs/no-literal-string-in-jsx` (strings missing
from the translation file) and `react/forbid-elements` (raw `<img>` / `<input>`; use
`ImageCard`, `DateInput mode="datetime"`, `Avatar photo`).

## Listing assets

`make-listing-assets.mjs` (next to this README) renders both portal rasters from SVG
sources and strips the alpha channel:

```bash
node make-listing-assets.mjs ./listing "#7857ed"
# -> listing/icon-512.png            512x512,   RGB
# -> listing/featured-2400x1800.png  2400x1800, RGB
```

Alpha-stripping needs a real rasteriser. `sips` renders SVG to PNG but always keeps an
alpha channel, and a JPEG round-trip adds visible artifacts to flat brand colour — hence
sharp's `.flatten({ background })`. Render the icon from a **square, unclipped** source:
the rounded-corner variant most brand kits ship as the app/PWA icon is exactly what Canva
rejects.

The featured image guideline asks for the app's **features, outputs or UI**. A wordmark on
a brand field meets the dimensions and misses the requirement; a faithful mock of the app's
own panel does not.

## Portal sequence (developer.canva.com)

1. **Code upload** — "JavaScript bundle", upload `dist/app.js` (5 MB cap), then upload
   `dist/messages_en.json` under Translations.
2. **Scopes** — leave every scope off unless you call it. `requestExport`,
   `requestOpenExternalUrl` and `prepareDesignEditor` are user-mediated and need none.
3. **Authentication** — empty, unless you genuinely use third-party OAuth.
4. **Compatibility** — `Public`; Desktop-only is the lower-risk first submission (mobile is
   reviewed against separate guidelines).
5. **App listing details → Text** — name ≤18 chars, short description ≤50, description ≤200.
6. **→ Media** — icon + featured image from `listing/`.
7. **→ Links** — site, terms, privacy, support. `curl` all four first.
8. **Testing instructions** — overview, steps, and a **sandbox** credential.
9. **App status → Submit.** Cap: 5 submissions per day.

## Traps (each = one round-trip)

- **Translations block submission and an empty file is rejected.** Every user-facing string
  must go through react-intl (`FormattedMessage` in JSX; `intl.formatMessage` for `Button`
  children, `placeholder`, `label`, `alt`, and error-state strings, which the kit types as
  `string`). `extract-translations` printing `0 messages` means the app only *looks*
  internationalised — scaffolds ship `@canva/app-i18n-kit` and `AppI18nProvider` unused.
- **The portal's forms save on blur, not on input.** Fill a field, move focus off it, wait
  for "All changes saved". Filling the last field in a form and navigating away reverts it
  to the placeholder, which then reads as "Provide a Description" on App status even though
  you typed one. Re-read every form after filling it.
- **File inputs clear after a successful read.** `input.files.length` goes back to 0 when
  the upload *worked*, so assert on the filename and "Saved" label instead. Reading 0 as
  failure sends you debugging a working upload.
- **There is no allow-listed-fetch-domains field** in the current portal, despite older
  guidance calling it the #1 trap. Security is read-only identifiers (App ID, app origin —
  the latter is what your backend's CORS policy needs). Debug a failing request as runtime
  CSP, not a missing portal toggle.
- **`requestExport` is user-facing and async.** It opens Canva's export dialog and resolves
  to `{ status, exportBlobs }`. Handle the non-`"completed"` status (the user cancelled) and
  fetch each blob's `url`. A multi-page design returns several. `createRenditions` is the
  *Adobe Express* API, not this one.
- **The final three gates need the account owner**: legal entity details plus identity
  documents, a compliance attestation checkbox, and a public walkthrough video link that
  plays without sign-in. Plan them as a handoff.
- **`apps config pull` needs `canva login`** (interactive browser), so `canva-app.json`
  cannot be fetched unattended.
- **oxlint's autofix can outrun your `lib`.** If the repo lints on commit, its `prefer-*`
  autofixes may rewrite `.sort()` to `.toSorted()`; on `lib: ES2022` that does not compile,
  so the file can never be committed. Raise `lib` to ES2023 rather than fighting the fixer.

## Files

- `example.ts` — the smallest real wiring: export the open design, upload the rendition,
  create the downstream action.
- `make-listing-assets.mjs` — renders and flattens the icon + featured image.
- `eslint.config.mjs.example` — the working Canva lint config, jest rule disabled.

## Pre-submission gate: run Canva's own doctor

```bash
npx @canva/cli@latest apps doctor      # 21 checks: SDK versions, lint, format, config
```

It flags outdated `@canva/*` packages (reviewers look at this), a missing `test` script,
and a missing `canva-app.json`. Pulling that config needs an **interactive** login:

```bash
npx @canva/cli apps config pull        # requires `canva login` first
```

`canva login` mints a CLI token against the account, so it cannot be automated
unattended — run it once by hand.

## Upload BOTH artefacts, every time

```bash
npx @canva/app-scripts build                  # -> dist/app.js
npx @canva/app-scripts extract-translations   # -> dist/messages_en.json
```

The portal's Code upload page has two separate file inputs. Uploading only `app.js`
leaves stale strings live once the app is localised. Selectors, if you are driving it:
`input[type=file][accept*="text/javascript"]` and `input[type=file][accept="application/json"]`.

## Verify-by-reload, because the portal's "saved" indicator lies

Every settings page autosaves and there is no Save button. "All changes saved" is a
page-global banner and does **not** mean the field you just set persisted. After each
edit: reload, re-read, then assert. Specifically:

- The address input is an autocomplete; typed text is discarded unless you click the
  **Add Manually** link (a link, not a button) and fill the structured subfields —
  including the post code, or the identity block stays invalid with no visible error.
- The compliance checkbox fires **zero** network requests on click; it only persists
  inside the identity payload. Don't burn attempts automating it.
- Scope checkboxes are visually hidden custom controls: a normal click reports "element
  is outside of the viewport". Click the element directly instead
  (`el.click()` inside `page.evaluate`), then reload to confirm.

## Declare the minimum scope, with evidence

Grep what the app actually imports before ticking scopes — over-declaring is a
documented rejection cause:

```bash
grep -rhoE 'from "@canva/[a-z]+"|requestExport|createRenditions|brandkit|brandTemplate' src/ | sort | uniq -c
```

An app whose whole surface is `requestExport` + `requestOpenExternalUrl` needs
`design:content:read` and nothing else. No `@canva/asset` dependency means the
`asset:private:*` scopes are dead weight.

## Driving the portal over CDP

A real-profile Chrome clone loads every extension, and each one opens an onboarding tab
— 30+ CDP targets makes `connectOverCDP` time out. Close the non-target tabs first
(`/json/close/<id>`) and pass a generous `{ timeout }`. The portal is also an SPA whose
client-side routing races `page.goto`: always wait for a **page-specific marker element**
before trusting the DOM, or you will read and edit the previous page's fields.
