# Cursor Cloud rollout

Helpers and templates for fleet `.cursor/environment.json` setup.

## Cost

Creating environments/builds is included with Cloud Agents. Running agents costs model usage — set a spend limit.

## Templates (`cursor-cloud-rollout-templates/`)

| File | Purpose |
|---|---|
| `agents-block.md` | Cloud block for `AGENTS.md` |
| `cursorignore` | Keep secrets out of agent context |
| `env.example` | Variable names only |
| `gitignore-additions.txt` | Ignore `.env.local` |

## Helpers

```bash
./cursor-cloud-detect.py itsryanarmani private-repo-4944
./cursor-cloud-environment-json.py private-repo-4944 "npm ci" "npm test"
```

Fleet scripts (`cursor-cloud-rollout`, `cursor-cloud-merge`, `cursor-cloud-env-setup`) land in follow-up PRs so each stays under the 500-line cap.

## API note

`api.cursor.com` has no durable Secrets/Environments endpoints. Session `envVars` on agent create is the supported secret path. Dashboard Secrets remain UI-only.
