# email-send-gate

Per-person outbound send API on Cloudflare Email Sending. Each caller holds an
opaque key; `KEYS_JSON` maps key -> {binding, from, name?}. Each `send_email`
binding is pinned with `allowed_sender_addresses`, so a leaked key cannot send
as any other address — the restriction is enforced by Cloudflare, not by code.

Use this instead of handing teammates a Cloudflare API token: `Email Sending
Write` tokens are account-wide and can send as any onboarded domain.

## Add a person

1. `wrangler.jsonc`: copy a `send_email` entry, set `allowed_sender_addresses`
   to their address.
2. Add their key to `KEYS_JSON`:

```sh
wrangler secret put KEYS_JSON   # {"<key>":{"binding":"EMAIL_<N>","from":"<a@d>","name":"<n>"}}
```

## Deploy / call

```sh
wrangler deploy
curl -X POST https://email-send-gate.<acct>.workers.dev/send \
  -H "Authorization: Bearer <key>" -H "content-type: application/json" \
  -d '{"to":"x@y.com","subject":"hi","text":"body"}'
```

`GET /health` -> `{"ok":true}`. Errors: 401 no/bad key, 400 missing
`to`/`subject`/`text`, 502 upstream send failure.
