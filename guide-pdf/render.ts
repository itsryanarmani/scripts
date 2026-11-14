#!/usr/bin/env bun
/** CLI: markdown file -> PDF. No framework deps beyond pdfkit. */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { parseArgs } from "node:util";
import { renderGuidePdf, themeFromSeed, type GuidePdfTheme } from "./guide-pdf";
import { splitFrontmatter } from "./markdown";

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    out: { type: "string" },
    seed: { type: "string", default: "#1e3a5f" },
    publisher: { type: "string" },
    domain: { type: "string", default: "example.com" },
  },
});
const input = positionals[0];
if (!input) {
  console.error("Usage: bun render.ts <guide.md> --out out.pdf [--seed #hex] [--publisher line]");
  process.exit(2);
}
const text = readFileSync(input, "utf8");
const split = splitFrontmatter(text);
const body = (split ? split.body.replace(/^\n+/, "") : text).trim();
const fm = split ? (Bun.YAML.parse(split.yaml) as Record<string, string>) : {};
const guide = {
  slug: "guide",
  title: fm.title ?? "Guide",
  description: fm.description ?? "",
  country: null,
  related: null,
  updated: fm.updated ?? "2026-01-01",
  body,
  sources: [],
  faq: [],
  words: body.split(/\s+/).length,
};
const theme: GuidePdfTheme = themeFromSeed(values.seed!, values.publisher);
const out = values.out ?? join(dirname(input), "guide.pdf");
mkdirSync(dirname(out), { recursive: true });
await renderGuidePdf(guide, { name: values.publisher ?? "", domain: values.domain!, defaultLocale: "en" }, out, theme);
console.log("wrote", out);
