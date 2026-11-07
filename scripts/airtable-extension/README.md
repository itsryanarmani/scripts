# airtable-extension — build + ship an Airtable extension

React app on the Airtable Blocks SDK; source lives in `frontend/`. Concept skill:
`airtable-extension` in `itsryanarmani/skills`.

## Flow
```bash
cd integrations/<app>
npm install               # depend on @airtable/blocks ONLY (see trap)
npm run build             # tsc --noEmit && vite build
block run                 # dev inside a base;  block release  to publish
```

## Traps (each = a build round-trip)
- **There is NO `@airtable/blocks-ui` package** — it 404s and breaks the whole install.
  Depend on `@airtable/blocks`; import UI from the `@airtable/blocks/ui` subpath.
- **React 16/17, not 18** — mount with `ReactDOM.render` / `initializeBlock`, never
  `react-dom/client` `createRoot`.
- Code lives in `frontend/`, not `src/`. Persist config in `globalConfig`.

## One call
```ts
import { createClient } from "@contentrabbit/sdk";
const cr = createClient({ apiKey });                 // from globalConfig
await cr.posts.create({ platformType: row.platform, content: row.text });
```
