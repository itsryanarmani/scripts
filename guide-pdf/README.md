# guide-pdf

Render long-form markdown guides to print-ready PDFs (cover, TOC, tables, themed sections) with PDFKit only — no browser.

## Use

```bash
bun guide-pdf/render.ts path/to/guide.md --out guide.pdf --seed "#7c2d1e" --publisher "Your series"
```

Copy `guide-pdf.ts` into any repo, or depend on this folder. Theme tokens are generic; no product name is required on the cover unless you pass `--publisher`.

## Markdown

Headings, lists, `>` quotes, fenced code, and pipe tables. Optional frontmatter: `title`, `description`, `updated`.

## Human copy

Run prose through the `humanizer` skill before PDF export so guides read like a person wrote them.
