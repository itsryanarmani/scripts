# adsense-check

`adsense-check` verifies the two AdSense ownership proofs: an `ads.txt`
publisher line and a `google-adsense-account` meta tag on the home page.
It GETs `https://<domain>/ads.txt` and `https://<domain>/`, prints one
`PASS`/`FAIL` line per check, calls no AdSense or Google API, stores nothing.

## Use

```sh
./adsense-check example.com ca-pub-0000000000000000
./adsense-check example.com pub-0000000000000000 --json
python3 -I adsense-check.test.py    # E2E test on a local http.server fixture
```

`<publisher-id>` is `ca-pub-` plus 16 ASCII digits (`pub-` is accepted and
normalised to `ca-pub-`). Anything else exits 2 before any request. Exit
codes: `0` both checks pass, `1` a check failed, `2` bad usage.

Requests are GETs only, user agent `adsense-check/1.0 (+ownership check)`,
15 s timeout each with a 30 s deadline for the whole run, at most 3
redirects, no cookies. Redirects must stay on http/https and the site host
or its `www.`/apex pair; anything else fails with "left the site domain".
Bodies are never printed. `ADSENSE_CHECK_TEST_BASE_URL` is for tests only.

## What each check means

| Check | Pass means |
| --- | --- |
| `ads.txt` | HTTP 200, `Content-Type` starts with `text/plain`, the body has no `<html`, and a line reads `google.com, pub-<digits>, DIRECT, f08c47fec0942fa0` (spaces trimmed, a trailing `#` comment allowed, a UTF-8 BOM tolerated; `google.com` and `DIRECT` case-insensitive; the certification id exact). |
| `meta tag` | The home page HTML has exactly one `<meta name="google-adsense-account">` tag inside `<head>` whose `content` is `ca-pub-<the 16 digits given>`. Tags inside `<noscript>`, comments and `<script>` do not count; a tag after `<body>` starts is reported as outside head and does not pass. Attribute order and quote style may vary; the page is parsed as HTML, not matched as text. |
| `ad script` | Informational only. Reports whether `adsbygoogle.js` appears in the home page HTML. Never fails the run. |

`--json` prints one object: `ok`, `publisher_id`, `domain`, `checks`, and
`fetches` with each URL's status and redirect hops. No response bodies.

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `FAIL ads.txt: status 404` | No ads.txt at the domain root, or the host serves a catch-all 404. | Publish `ads.txt` at `https://<domain>/ads.txt`. |
| `FAIL ads.txt: content-type text/html` | The web server labels ads.txt as HTML. | Serve it as `text/plain`. |
| `FAIL ads.txt: body contains HTML` | A soft-404 page returns 200 with HTML. | Fix the route so `/ads.txt` returns the real file. |
| `FAIL ads.txt: no line ...` | The publisher line is missing, has a stray space inside a field, a wrong or differently-cased certification id, or a different `pub-` id. | Add `google.com, pub-<digits>, DIRECT, f08c47fec0942fa0` on its own line. |
| `FAIL ...: redirect left the site domain` | A hop redirects to another host, even a sibling subdomain or another site on the same platform. | Keep redirects on the site host or its `www.`/apex pair. |
| `FAIL ...: redirect to unsupported URL` | A hop redirects to a non-http(s) scheme such as `ftp:`. | Redirect to the https URL instead. |
| `FAIL meta tag: no ... meta tag` | The tag is absent, only on a sub-page, inside `<noscript>`, or after `<body>` starts. | Put the tag in the `<head>` of the home page HTML. |
| `FAIL meta tag: N ... meta tags` | The tag was pasted more than once. | Keep exactly one. |
| `FAIL meta tag: meta tag has '...', want '...'` | A different publisher id is on the page, or the content lacks the `ca-` prefix (copy-paste error). | Paste the id from the correct AdSense account as `ca-pub-<digits>`. |
| `FAIL ...: home page status ...` | The home page does not return 200. | Fix the site first; the tag cannot be verified. |
| `exit 2` | The publisher id is not `ca-pub-`/`pub-` plus 16 ASCII digits. | Copy the id from AdSense exactly. |

The full setup flow lives in the `adsense-site-setup` skill.
