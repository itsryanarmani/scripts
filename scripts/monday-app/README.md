# monday-app — build + submit a monday.com app

React board/item view on the monday apps SDK (`monday-sdk-js`). Concept skill:
`monday-app` in `itsryanarmani/skills`.

## Flow
```bash
cd integrations/<app>
npm install
npm run build             # tsc --noEmit && vite build
```
## Pre-submission checks

Run the two cheap checks that caught real problems before opening the ~25-field
submission form (see the `monday-app-submission` skill for the full Developer
Center playbook):

```bash
./check-app.mjs --client-id <clientId>                    # install link is live
./check-app.mjs --api-base <url> --api-key <key>          # reviewer key works
./check-app.mjs --client-id <id> --api-base <url> --api-key <key>   # both

MONDAY_API_KEY=<key> ./check-app.mjs --api-base <url>      # key via env, not argv
```

The client-id check follows `auth.monday.com/oauth2/authorize?...response_type=install`
and asserts the 302's `oauth_payload_token` JWT decodes to that client id. The
api-key check asserts `GET /posts` and `GET /accounts` both return 200 — a key
that worked in a previous session had expired silently by submission time, so
test immediately before submitting. Exit 0 = pass, 1 = a check failed,
2 = usage error.

Submit via the monday Developer Center (**portal-review** — no listing API; the
`@mondaydotcomorg/apps-cli` deploys code, not the listing). No-code / "vibe code"
apps are not eligible. Public hosting URL required (your host or monday code).
1. `apps.developer.monday.com` → Create app → build the view, set OAuth scopes +
   HTTPS hosting URL.
2. Listing assets: app + developer icon **192×192**, card image **592×348**,
   **3–5 gallery images 1920×960**, promo video ≤120 s / 50 MB (guidelines prefer
   30–60 s HD MP4 — verify). Copy limits: name ≤30 (do not start with "monday"),
   short desc ≤60, long desc 200–2,000. **Privacy-policy + ToS URLs** required;
   support email on a domain you prove you own.
3. **Share** tab → publish (produces the `auth.monday.com` install link) → complete
   the marketplace **submission form** (`forms.monday.com`; exact form id: verify).
   First reply ~72 business hours on a shared review board. Review includes a
   **Burp scan** of every domain.

Paid apps bill through monday; rev-share often quoted 0% until $200k lifetime,
then 85/15 `(verify)`. SOC2/ISO is optional (Shield Badge only).

## Traps
- **monday's session token ≠ your API's auth** — carry your own key (per-installation).
- **`import.meta.env` untyped** → add `src/vite-env.d.ts` (`vite/client` reference).
- Board context arrives via `monday.listen("context")`; the view is a sandboxed iframe.

## One call
```ts
import { createClient } from "@contentrabbit/sdk";
const cr = createClient({ apiKey });
await cr.posts.create({ platformType: item.platform, content: item.text });
```
