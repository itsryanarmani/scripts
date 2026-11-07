# vscode-extension — build + publish to VS Code Marketplace + Open VSX

Concept skill: `vscode-extension` in `itsryanarmani/skills`.

## Build + package (Node 20 — vsce/ovsx SEGFAULT on 22/25)
```bash
export PATH="/opt/homebrew/opt/node@20/bin:$PATH"
cd integrations/<ext>
npm install && npm run compile
npx @vscode/vsce package            # -> <name>-<ver>.vsix  (fails if README has an SVG image -> use PNG/remove)
```

## Publish to Open VSX (headless, GitHub-login token)
```bash
# mint token once: open-vsx.org -> GitHub login -> sign Eclipse Publisher Agreement -> Access Tokens
npx ovsx create-namespace <publisher> -p "$OVSX_TOKEN"     # once
npx ovsx publish <name>-<ver>.vsix -p "$OVSX_TOKEN"        # -> Cursor/Windsurf/VSCodium/Gitpod
```

## Publish to VS Code Marketplace (needs a human-made publisher + PAT)
```bash
# create publisher by hand at marketplace.visualstudio.com/manage (the form fights automation)
# create PAT at dev.azure.com (scope: Marketplace -> Manage)
npx @vscode/vsce publish -p "$VSCE_PAT"
```

## Traps
- **Node 20 only** (22/25 segfault, exit 139, silent).
- **No SVG in README.md** (vsce blocks it).
- `package.json` needs `publisher` + `repository` + `license`.
- Open VSX first (easy); VS Code Marketplace publisher is a manual browser step.
