# webflow-app — build + submit a Webflow app

Two programs: a Designer extension (Vite iframe UI) + a Data-client/server (OAuth +
webhooks, Node ESM). Concept skill: `webflow-app` in `itsryanarmani/skills`.

## Flow
```bash
cd integrations/<app>
npm install
npm run build             # build:designer (vite) && build:server (tsc -p tsconfig.server.json)
```
Register the app in the Webflow developer dashboard (scopes, OAuth redirect, webhook URL)
→ submit for marketplace review.

## Traps
- **NodeNext server needs `.js` on every relative import** (static AND `import()`), or tsc
  errors **TS2835**. Don't switch to bundler resolution — the ESM runs under Node.
- Two tsconfigs, two resolutions (designer=bundler, server=NodeNext). Don't cross them.
- Verify the CMS-publish webhook signature before acting. Keep Vite `outDir` inside the package.

## One call (in the webhook handler)
```ts
import { createClient } from "@contentrabbit/sdk";
const cr = createClient({ apiKey });
await cr.posts.create({ platformType: "twitter", content: `New: ${item.name}` });
```
