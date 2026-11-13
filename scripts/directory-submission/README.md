# directory-submission

Generate the submission packet for listing a live website on free web
directories (SEO backlinks, traffic) and MCP directories (remote `/mcp`
endpoints). Companion to the `website-directory-submission` skill — the skill
owns the directory tables and order of operations; this generator owns the
mechanical copy-paste artifacts so every site submits identical, complete
packets.

## Run

```sh
node gen.mjs site.json --out ./out
```

`site.json` shape:

```json
{
  "name": "Dish Directory",
  "tagline": "Every restaurant, its dishes, prices and hours — by city.",
  "short": "<=260 chars",
  "long": "<=500 chars",
  "url": "https://private-repo-ba8a.com",
  "repo": "https://github.com/itsryanarmani/private-repo-ba8a",
  "mcp_url": "https://private-repo-ba8a.com/mcp",
  "registry_name": "io.github.itsryanarmani/private-repo-ba8a",
  "contact_email": "hello@example.com",
  "pricing": "Free",
  "category_web": "Food & Drink",
  "category_mcp": "Search & Data Extraction",
  "tags": ["restaurants", "directory", "mcp"],
  "tools": [
    { "name": "search_listings", "description": "Search published restaurants by text, place and category." }
  ]
}
```

Output files in `--out`:

| File | Use |
|---|---|
| `packet.md` | The §0 packet: every field a directory form asks for, copy-paste ready. |
| `server.json` | Official MCP registry manifest (`remotes[]` streamable-http). Validate + publish with `mcp-publisher`. |
| `submissions.csv` | Tracking sheet seeded with one row per directory from `directories.json`. |
| `mcp-so-issue.md` | Ready-to-file mcp.so submission issue body. |
| `awesome-remote-entry.md` | README entry block for the awesome-remote-mcp-servers PR. |

`directories.json` is the machine-readable directory table (same content as the
skill's §1–§4, without prose). Update it when the skill's tables change.

## What stays manual

The generator prepares; it does not log in anywhere. Human-gated submits
(Product Hunt, BetaList, review-site profiles, Glama/Smithery web forms) are
completed by a human with `packet.md` open. GitHub-based submits (awesome-list
PRs, mcp.so issues) and `mcp-publisher publish` (after `mcp-publisher login
github`) are the automatable remainder — an agent finishes those.
