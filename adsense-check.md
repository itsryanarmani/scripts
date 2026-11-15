# adsense-check

Verifies AdSense ownership proofs — an `ads.txt` line and a
`google-adsense-account` meta tag — by GETting `/ads.txt` and `/`. Stdlib only.

```sh
./adsense-check <domain> <publisher-id> [--json]
python3 -I adsense-check.test.py   # local http.server fixture
```

`<publisher-id>` is `ca-pub-` + 16 ASCII digits (`pub-` normalized); else
exit 2 before any request. Exit codes: 0 pass, 1 a check failed, 2 usage.

GETs only, UA `adsense-check/1.0 (+ownership check)`, 15 s socket timeout,
30 s deadline via `SIGALRM`/`setitimer` watchdog (Unix; covers DNS, TLS,
headers, chunk sizes, body, redirect chain, slow parse — elsewhere the
8 KB-chunk check), ≤3 redirects on http/https within the site host or its
`www.`/apex pair, no cookies, bodies never printed. `ADSENSE_CHECK_TEST_*`
env vars are test-only and warn on stderr.

`ads.txt` must be a 200 `text/plain` body, no `<html`, with the line
`google.com, pub-<digits>, DIRECT, f08c47fec0942fa0` (fields trimmed,
`#` comment and UTF-8 BOM ok, `google.com`/`DIRECT` any case, cert id
exact). The `meta tag` must be exactly one in `<head>` parsed as HTML —
`<noscript>`, comments, `<script>` ignored; after `</head>`/`<body>`/body
text or any body-level tag it is outside head and fails — `content`
`ca-pub-<digits>`, attribute order and quotes free. `ad script` is INFO
only; `--json` prints `ok`, `publisher_id`, `domain`, `checks`, `fetches`.

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `FAIL ads.txt: status 404` | No ads.txt or a catch-all 404. | Publish it at `/ads.txt`. |
| `FAIL ads.txt: content-type text/html` | Server labels it HTML. | Serve `text/plain`. |
| `FAIL ads.txt: body contains HTML` | Soft-404 returns 200 HTML. | Fix the `/ads.txt` route. |
| `FAIL ads.txt: no line ...` | Missing line, stray space, wrong cert id or `pub-`. | Add `google.com, pub-<digits>, DIRECT, f08c47fec0942fa0`. |
| `FAIL ...: redirect left the site domain` | Hop leaves the host, even a sibling subdomain. | Stay on the host or its `www.`/apex pair. |
| `FAIL ...: redirect to unsupported URL` | Non-http(s) scheme like `ftp:`. | Redirect to https. |
| `FAIL ...: deadline exceeded` | Any phase trickles past the deadline. | Check response time for both URLs. |
| `FAIL meta tag` | Absent, sub-page, `<noscript>`, or outside head (`meta tag found outside head`). | Put exactly one in the home `<head>`. |
| `FAIL meta tag: ...` | Duplicated (ids listed) or wrong/missing `ca-`. | Keep exactly one `ca-pub-<digits>`. |
| `FAIL ...: home page status ...` / `exit 2` | Home not 200 / bad publisher id. | Fix the site / copy the id from AdSense. |

The full setup flow lives in the `adsense-site-setup` skill.
