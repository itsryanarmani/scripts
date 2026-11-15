# adsense-check

Verifies the two AdSense ownership proofs — an `ads.txt` publisher line and
a `google-adsense-account` meta tag on the home page — by GETting
`https://<domain>/ads.txt` and `https://<domain>/`. Stdlib only; stores nothing.

```sh
./adsense-check example.com ca-pub-0000000000000000
./adsense-check example.com pub-0000000000000000 --json
python3 -I adsense-check.test.py   # local http.server fixture
```

`<publisher-id>` is `ca-pub-` + 16 ASCII digits (`pub-` normalized); else
exit 2 before any request. Exit codes: 0 pass, 1 a check failed, 2 usage.

GETs only, UA `adsense-check/1.0 (+ownership check)`, 15 s socket timeout,
30 s run deadline enforced between 8 KB body chunks (a trickle cannot
stall), ≤3 redirects on http/https within the site host or its `www.`/apex
pair, no cookies, bodies never printed. `ADSENSE_CHECK_TEST_BASE_URL` and
`ADSENSE_CHECK_TEST_DEADLINE` are test-only.

`ads.txt` must be a 200 `text/plain` body with no `<html` and the line
`google.com, pub-<digits>, DIRECT, f08c47fec0942fa0` (fields space-trimmed,
`#` comment and UTF-8 BOM ok, `google.com`/`DIRECT` any case, cert id
exact). The `meta tag` must be exactly one in `<head>` parsed as HTML —
`<noscript>`, comments, `<script>` ignored; a tag after `<body>` or body
text is outside head and fails — with `content` `ca-pub-<digits>`; attribute
order and quotes free. `ad script` is INFO only. `--json` prints `ok`,
`publisher_id`, `domain`, `checks`, `fetches` (status + hops).

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `FAIL ads.txt: status 404` | No ads.txt or a catch-all 404. | Publish it at `/ads.txt`. |
| `FAIL ads.txt: content-type text/html` | Server labels it HTML. | Serve `text/plain`. |
| `FAIL ads.txt: body contains HTML` | Soft-404 returns 200 HTML. | Fix the `/ads.txt` route. |
| `FAIL ads.txt: no line ...` | Missing line, stray space, wrong cert id or `pub-`. | Add `google.com, pub-<digits>, DIRECT, f08c47fec0942fa0`. |
| `FAIL ...: redirect left the site domain` | Hop leaves the host, even a sibling subdomain. | Stay on the host or its `www.`/apex pair. |
| `FAIL ...: redirect to unsupported URL` | Non-http(s) scheme like `ftp:`. | Redirect to https. |
| `FAIL ...: deadline exceeded` | Fetch or body trickles past 30 s. | Check response time for both URLs. |
| `FAIL meta tag: no ... meta tag` | Absent, sub-page only, `<noscript>`, or outside head. | Put it in the home `<head>`. |
| `FAIL meta tag: N ... meta tags` | Duplicated; the message lists the ids. | Keep exactly one. |
| `FAIL meta tag: meta tag has ...` | Wrong id or missing `ca-` prefix. | Paste `ca-pub-<digits>` from AdSense. |
| `FAIL ...: home page status ...` / `exit 2` | Home not 200 / bad publisher id. | Fix the site / copy the id from AdSense. |

The full setup flow lives in the `adsense-site-setup` skill.
