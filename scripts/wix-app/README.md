# wix-app — build + submit a Wix app

React dashboard page on the Wix SDK (`@wix/sdk`, `@wix/dashboard`). Concept skill:
`wix-app` in `itsryanarmani/skills`.

## Flow
```bash
cd integrations/<app>
npm install
npm run build             # tsc --noEmit && vite build
```
Submit at `dev.wix.com` (**portal-review** — no listing API; `@wix/cli` deploys
code, not the listing). Paid apps must use Wix Billing + a payout account.
1. Configure extensions, OAuth scopes, redirect URLs; host over HTTPS (valid SSL).
2. **App Info**: name (no "Wix"), teaser, **1000×1000** 24-bit sRGB PNG icon, ≥3
   feature bullets + description, **terms URL**. **Media**: 5–6 images ≥1200×900
   (4:3) JPG/PNG; optional YouTube promo + 540×360 banner. **Company Info**:
   logo, address, website, **privacy-policy URL**.
3. Supply a **live demo account + credentials** and install notes; keep the demo
   active for as long as the app is listed.
4. Clear all dashboard **blockers** → **Submit & Publish**. An AI review runs on
   submit; leftover blockers only clear on **resubmit**. Appeals go through Wix support.
5. Human-review fallback SLA `(verify)`.

## Traps
- **`import.meta.env` untyped** → add `src/vite-env.d.ts` with `/// <reference types="vite/client" />`
  or tsc errors TS2339.
- If `vite.config.ts` is in both the app tsconfig and a composite node tsconfig → **TS6305**;
  keep it only in the node project, `include: ["src"]` for the app.
- Wix OAuth authorizes Wix data; your API needs its own key (per-installation).

## One call
```ts
import { createClient } from "@contentrabbit/sdk";
const cr = createClient({ apiKey });
await cr.posts.create({ platformType: "twitter", content: "Hello from Wix" });
```
