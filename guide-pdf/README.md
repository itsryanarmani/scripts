# guide-pdf

`bun guide-pdf/render.ts guide.md --out guide.pdf --seed "#1e3a5f"`

Renders GFM pipe tables; six or more columns use a landscape page for readability.

PDFKit renderer: cover, TOC, tables. Neutral branding unless you pass `--publisher`.
