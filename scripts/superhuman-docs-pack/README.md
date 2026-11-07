# superhuman-docs-pack — build + publish a Superhuman Docs (Coda) pack

Superhuman Docs = the 2026 rebrand of Coda. SDK unchanged (`@codahq/packs-sdk`); CLI is
now `packs` (`coda` still aliases). Concept skill: `superhuman-docs-pack` in `itsryanarmani/skills`.

## Publish flow (verified working)
```bash
# Node 20 REQUIRED — packs build/upload SEGFAULT on Node 22/25 (exit 139)
export PATH="/opt/homebrew/opt/node@20/bin:$PATH"
cd integrations/<pack> && npm install
npx coda register <PACK_SCOPED_TOKEN>          # coda.io/account -> API Settings (Pack scope, NOT an MCP token)
npx coda create pack.ts --name "…" --description "…"   # first time -> Pack id in .coda-pack.json
npx coda upload pack.ts -n "notes"
# release PROMPTS on /dev/tty (fails headless) + warns if not on main -> wrap in a pty:
yes | script -q /dev/null /bin/zsh -c 'cd $PWD; export PATH="/opt/homebrew/opt/node@20/bin:$PATH"; npx coda release pack.ts 1 -n "Initial release."'
```

## Traps
- Node 20 only (22/25 segfault, exit 139, silent).
- Pack-scoped token (MCP token can't publish).
- `release` needs a TTY -> `yes | script -q /dev/null …`; refuses any uncommitted repo change.
- `.coda.json`=token (gitignore); `.coda-pack.json`=Pack id (commit).
- Gallery listing = review-gated web action (browser login).
