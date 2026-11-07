# whop-app — build + submit a Whop app

React app embedded as an iframe view inside a Whop (Whop SDK). Concept skill:
`whop-app` in `itsryanarmani/skills`.

## Flow
```bash
cd integrations/<app>
npm install
npx whop-proxy            # dev proxy: loads the local app inside a real Whop
npm run build             # bundle served at your hosted app URL
```
Submission is **scriptable (API + CLI)**. Dashboard: `whop.com/dashboard/developer`.
REST: `POST https://api.whop.com/api/v1/apps`, `PATCH /apps/{id}`, `POST /files`
then `POST /app_builds`, `POST /app_builds/{id}/promote`. CLI: `whop apps deploy`
(`--preview` uploads without going live). Public HTTPS `base_url` required.
1. Create the app (dashboard or `POST /apps`); set HTTPS `base_url`/`route` +
   OAuth redirects + Hosting paths (`/experiences/[experienceId]`, `/dashboard/[companyId]`).
2. Fill store metadata: name, icon, short description, longer `app_store_description`.
   Screenshots / 10–20 s demo if the listing UI asks `(verify)`.
3. Test inside a real Whop via `whop-proxy` / `whop apps dev`.
4. Upload a versioned web build (`POST /app_builds` or `whop apps deploy`).
5. Promote (`POST /app_builds/{id}/promote` or `whop apps builds promote <id>`).
   Draft builds enter review first; an approved build becomes the App Store version.

Revenue: often quoted as 10–30% dev rev-share plus a platform cut `(verify)`.
Icon px spec and review SLA are not pinned in the docs `(verify)`.

## Traps
- **Whop OAuth ≠ your API's auth.** "Sign in with Whop" identifies the user; your own API
  still needs its own key (stored per-installation).
- App ID + redirects are dashboard-owned (placeholders break on install).
- Cast web-only CSS props to a real `CSSProperties` value, not `as unknown as string` (tsc fails).

## One call every app makes
```ts
import { createClient } from "@contentrabbit/sdk";
const cr = createClient({ apiKey });                 // your key, NOT the Whop token
await cr.posts.create({ platformType: "twitter", content: "Shipped!" }); // platformType is a STRING
```
