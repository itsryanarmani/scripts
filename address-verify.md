# address-verify

Checks postal addresses with the PostGrid address verification API before you
mail anything. Each lookup is paid, so a run needs `--yes`.

```sh
gog sheets get "$SHEET" "Companies!C1:C30" --json > addr.json
python3 address-verify --sheet-json addr.json --dry-run
POSTGRID_ADDVER_LIVE_API_KEY=... python3 address-verify --sheet-json addr.json --yes --out result.json
```

| Flag | Meaning |
| --- | --- |
| `--file F` or `--sheet-json F` | One address per line, or a `gog` JSON export. |
| `--column N`, `--header` | 0-based address column in the sheet export (default 0). `--header` skips the first row. |
| `--dry-run` / `--yes` | Preview with no network call / allow the paid lookups. |
| `--out F` | Also write the results as one JSON list. |

Output is one JSON line per address: `input`, `status`, `canonical`, `errors`.
`verified` means it matched as written. `corrected` means it matched after PostGrid
fixed the format. `failed` with "Missing Value: Suite identifier" means the street
exists but the building wants a suite. `failed` with "Unable to find a match" means
no match: check an official source before you call it wrong.

Traps found in use:

- The **test** key answers every address with one dummy address. The tool refuses a
  key that starts with `test_`, and an empty one.
- It checks the US and Canada. A real UK or French address comes back `failed`.
- A new or rare address can be real and still fail (a Vancouver office on the
  company's own contact page returned "no match"). Treat `failed` as "look again".
- The request needs a `User-Agent` header, or Cloudflare answers error 1010.
- A note in brackets is cut off before the lookup. The cut starts at the first bracket
  that has no postal code after it, so "PO Box 12345 (Station A) Toronto ON M5V 2T6"
  stays whole.
- A timeout or network error marks that row `error` and the run goes on, so the
  `--out` file has every row up to a stop. After a 401 or 403 the run stops and the
  rows after it are missing.

Test: `python3 address-verify.test.py` runs against a local fake server.
