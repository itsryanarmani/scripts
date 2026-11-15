# adsense-check

`adsense-check` verifies the two ways AdSense proves site ownership: an
`ads.txt` publisher line and a `google-adsense-account` meta tag on the home
page. It fetches `https://<domain>/ads.txt` and `https://<domain>/` and
reports one `PASS` or `FAIL` line per check. Standard library only; it calls
no AdSense or Google API and stores nothing.

## Use

```sh
./adsense-check example.com ca-pub-0000000000000000
./adsense-check example.com pub-0000000000000000 --json
python3 adsense-check.test.py    # E2E test on a local http.server fixture
```

`<publisher-id>` is `ca-pub-` plus 16 digits. `pub-` plus 16 digits is
accepted and normalised to `ca-pub-`. Anything else exits 2 before any
request is made.

Exit codes: `0` both required checks pass, `1` a check failed, `2` bad usage.

Requests are plain `GET`s with the user agent
`adsense-check/1.0 (+ownership check)`, a 15 second timeout each, at most 3
redirects, and no cookies. Redirects are followed only while they stay on
the same registrable domain (`www.<domain>` and `<domain>` count as the
same). Response bodies are never printed.

## What each check means

| Check | Pass means |
| --- | --- |
| `ads.txt` | HTTP 200, `Content-Type` starts with `text/plain`, the body has no `<html`, and a line reads `google.com, pub-<digits>, DIRECT, f08c47fec0942fa0` (spaces trimmed; `google.com` and `DIRECT` case-insensitive; the certification id exact). |
| `meta tag` | The home page HTML has exactly one `<meta name="google-adsense-account">` tag and its `content` equals the publisher id given. Attribute order and quote style may vary; the page is parsed as HTML, not matched as text. |
| `ad script` | Informational only. Reports whether `adsbygoogle.js` appears in the home page HTML. Never fails the run. |

With `--json` the tool prints one JSON object: `ok`, `publisher_id`,
`domain`, the `checks` array, and the `fetches` map with each URL's final
status code and every redirect hop. It still prints no response bodies.

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `FAIL ads.txt: status 404` | No ads.txt at the domain root, or the host serves a catch-all 404. | Publish `ads.txt` at `https://<domain>/ads.txt`. |
| `FAIL ads.txt: content-type text/html` | The web server labels ads.txt as HTML. | Serve it as `text/plain`. |
| `FAIL ads.txt: body contains HTML` | A soft-404 page returns 200 with HTML. | Fix the route so `/ads.txt` returns the real file. |
| `FAIL ads.txt: no line ...` | The publisher line is missing, has a stray space inside a field, a wrong certification id, or a different `pub-` id. | Add `google.com, pub-<digits>, DIRECT, f08c47fec0942fa0` on its own line. |
| `FAIL ads.txt: redirect left the site domain` | `/ads.txt` redirects to another domain. | Keep the redirect on the registrable domain. |
| `FAIL meta tag: no ... meta tag` | The tag is absent, or only on a sub-page. | Put the tag in the `<head>` of the home page HTML. |
| `FAIL meta tag: N ... meta tags` | The tag was pasted more than once. | Keep exactly one. |
| `FAIL meta tag: meta tag has 'ca-pub-...', want 'ca-pub-...'` | A different publisher id is on the page (copy-paste error). | Paste the id from the correct AdSense account. |
| `FAIL ...: home page status ...` | The home page does not return 200. | Fix the site first; the tag cannot be verified. |
| `exit 2` | The publisher id is not `ca-pub-`/`pub-` plus 16 digits. | Copy the id from AdSense exactly. |

The full site setup flow (where the tag and ads.txt come from) lives in the
`adsense-site-setup` skill.
