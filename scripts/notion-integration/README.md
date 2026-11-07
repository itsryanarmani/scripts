# notion-integration — build, run, and submit a Notion integration

A Notion integration is a service on the **Notion API** (`@notionhq/client`)
that moves content between a workspace and your product's SDK / public REST
API. Distribution requires a **public** integration (OAuth) — internal tokens
are one-workspace only, can never be listed, and can't be converted. This is
the playbook: the path from `integrations/<app>/` to the gallery, plus the
traps that each cost a round-trip. The concept-level skill is
`notion-integration` in `itsryanarmani/skills`.

## Flow

```bash
cd integrations/<app>          # integration source (src/, assets/, .env)
cp .env.example .env           # NOTION_CLIENT_ID / NOTION_CLIENT_SECRET / NOTION_REDIRECT_URI
npm install
npm run dev                    # serves OAuth + sync loop on localhost
# open the landing page: connect Notion (OAuth), paste your API key + database id
```

Notion side (**portal-review** — no listing API). Portal:
`app.notion.com/developers/connections`. Listings: `www.notion.so/profile/connections`.
1. Create a **public** connection with installation scope **"Any workspace"**
   (not "Selected workspaces only" — immutable, and ineligible to list) → copy
   the OAuth client id/secret into `.env`.
2. Host on public HTTPS. Register the redirect URI exactly as `NOTION_REDIRECT_URI`
   (localhost for dev, HTTPS for prod) so authorize + token-exchange match.
3. Set capabilities to only what the code calls (read/update/insert content).
4. Grant content: pick the database on the OAuth consent screen (that picker IS
   the access grant).
5. Listings → Connections → **Start a new connection listing** → attach the
   public connection → fill name/description/tags/logo + listing images (exact px:
   verify) + support contact → **Submit**. Security + content review, ~5–10
   business days by email. Listing is optional for the OAuth flow itself.

## Traps (each = one round-trip)

- **Internal ≠ public** — internal tokens can't be distributed, listed, or converted. Start public.
- **Grant the content** — `object_not_found` / empty query means the integration can't see the database. Not a bad id.
- **status vs select** — detect the property type via `databases.retrieve`; filter and write syntax differ.
- **Status options must pre-exist** — create them in Notion first; the API auto-creates select options only.
- **Typed envelopes** — join `plain_text` from `title[]`/`rich_text[]`; truncate rich text under 2000 chars; paginate with `start_cursor`.
- **Redirect URI exact match** — byte-for-byte against the registered value, at both authorize and token exchange.
- **No refresh token** — store the access token; a 401 means the workspace uninstalled → re-auth. Back off on 429.

## Files

`example.ts` (next to this README) — the smallest real wiring: OAuth exchange,
query a database for rows at a status (with status/select detection), hand
each row to your API, write the result back onto the row. Copy it as a
starting point.
