# marketplace-app-hosting — host iframe apps on one Cloudflare Worker

The deploy half of the app 0→1: serve every iframe marketplace app's built bundle at
`apps.<domain>/<app>/` from one standalone Worker, with per-store framing headers.
Concept skill: `marketplace-app-hosting` in `itsryanarmani/skills`. A working reference
lives in the product repo at `apps/website/cloudflare/embeds/`.

## Layout
```
embeds/
  wrangler.toml        # name, [assets] directory+binding + run_worker_first, env.staging/production custom_domain routes
  src/index.ts         # per-request: ASSETS.fetch + SPA fallback + set frame-ancestors CSP + drop X-Frame-Options
  src/csp.ts           # { app: "frame-ancestors <store domains>" }
  build.sh             # build each app + copy dist/ -> public/<app>/
  public/              # build output (gitignored)
```

## Deploy
```bash
cd apps/website/cloudflare/embeds
bash build.sh                       # assemble public/<app>/ from each integrations/<app>/dist
npx wrangler deploy --env staging   # -> apps.staging.<domain> (custom_domain auto-creates DNS + cert)
# verify EVERY app: 200 AND carries the frame-ancestors header
curl -sD - -o /dev/null https://apps.staging.<domain>/<app>/ | grep -i content-security-policy
npx wrangler deploy --env production # -> apps.<domain>
```

## Traps (each cost real time)
- **`run_worker_first = true` is mandatory** — without it Static Assets serve 200s
  directly and your CSP never applies; the marketplace iframe stays blank. Verify CSP on
  a 200, not just a 404.
- **`custom_domain = true`** auto-creates the DNS + edge cert on deploy. A Workers-only
  API token deploys the script but may fail the route creation → a human adds the custom
  domain once in the Cloudflare dashboard. New hostname → SSL handshake fails for a few
  minutes while the cert provisions (not a bug).
- **Build the local SDK first** if apps use `file:../../packages/sdk` (needs its `dist`).
- **A non-existent pinned dep version** 404s the whole `npm install` — fix the version.
- **Interactive build CLIs** (Adobe analytics prompt) can't be scripted; **Remix apps**
  (Shopify) aren't static — handle both outside this static flow.
- **Only host apps that embed a URL** (dashboard/OAuth). Design-tool apps
  (Canva/Figma/Adobe) upload a bundle — never host them.

## Credentials
Store per-app OAuth client id/secret + any store tokens in the product's `.env.local`
(never commit), and push runtime secrets to the Worker with
`wrangler secret put <NAME> --env <staging|production>`. The Worker reads them from `env`.
OAuth redirect URI to register in each store = `https://apps.<domain>/<app>/oauth/callback`.
