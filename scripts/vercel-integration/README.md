# vercel-integration — build + submit a Vercel integration

OAuth app + config UI + deploy-webhook handler. Concept skill: `vercel-integration` in
`itsryanarmani/skills`.

## Flow
```bash
cd integrations/<app>
npm install
npm run build             # tsc / your bundler
```
Register in the Vercel integration console (OAuth scopes, redirect, config URL, webhook URL)
→ submit for marketplace review.

## Traps
- **Verify the deploy webhook signature before acting**; only fire on the ready/succeeded
  event; dedupe by deployment id.
- Vercel OAuth authorizes Vercel; your API needs its own key (per-installation).
- NodeNext ESM server → `.js` on relative imports (TS2835). Developer audience — narrow fit.

## One call (deploy webhook handler)
```ts
import { createClient } from "@contentrabbit/sdk";
const cr = createClient({ apiKey });
await cr.posts.create({ platformType: "twitter", content: `Shipped ${deployment.name}` });
```
