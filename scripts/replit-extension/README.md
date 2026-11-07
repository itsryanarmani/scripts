# replit-extension — build + publish a Replit Extension

React tool panel on the Replit Extensions API (`@replit/extensions`). Concept skill:
`replit-extension` in `itsryanarmani/skills`.

## Flow
```bash
cd integrations/<app>
npm install
npm run build
```
Develop against the extension dev tools → publish to the Replit Extensions store (review).

## Traps
- **Over-typed result wrappers cascade** — type a helper to the SDK's ACTUAL return
  (`{ data?: T[] }` / union), narrow at the call site (`Array.isArray(x) ? x : x.data ?? []`);
  don't assert `{ data: T[] }`.
- **`import.meta.env` untyped** → add `src/vite-env.d.ts`.
- Developer audience — keep the value crisp ("announce a shipped Repl").

## One call
```ts
import { createClient } from "@contentrabbit/sdk";
const cr = createClient({ apiKey });
await cr.posts.create({ platformType: "twitter", content: "Shipped a new Repl" });
```
