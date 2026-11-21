#!/usr/bin/env node
// Render notes / iMessage / blurred-PDF HTML to PNG when a browser is available.
// --dry-run always writes the HTML and checks structure; it never needs Playwright.

import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const args = process.argv.slice(2);
const arg = (flag) => { const i = args.indexOf(flag); return i >= 0 ? args[i + 1] : undefined; };
const dry = args.includes("--dry-run");
const aspect = arg("--aspect") || "4:5";
const out = arg("--out");
const html = arg("--html") ?? (arg("--file") ? readFileSync(arg("--file"), "utf8") : null);

if (!html || !out) {
  console.error("usage: node renderer.mjs --file HTML|--html STR --out PATH [--aspect 4:5|9:16] [--dry-run]");
  process.exit(2);
}

const sizes = { "4:5": [1080, 1350], "9:16": [1080, 1920] };
if (!sizes[aspect]) { console.error("aspect must be 4:5 or 9:16"); process.exit(2); }
const [w, h] = sizes[aspect];

const problems = [];
if (!/<!doctype html>/i.test(html)) problems.push("missing doctype");
if (!/<head>/i.test(html) || !/<body>/i.test(html)) problems.push("missing head or body");
if (!/system-ui|sans-serif|Georgia|serif/.test(html)) problems.push("missing a native font");

mkdirSync(dirname(resolve(out)), { recursive: true });
const htmlOut = out.endsWith(".png") ? out.slice(0, -4) + ".html" : out + ".html";
writeFileSync(htmlOut, html);
if (problems.length) {
  console.error(`structure checks failed: ${problems.join("; ")}`);
  process.exit(2);
}
console.log(`wrote ${htmlOut}`);
if (dry) process.exit(0);

let shot = false;
try {
  const { chromium } = await import("playwright");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  await page.setContent(html, { waitUntil: "load" });
  await page.screenshot({ path: out, type: "png" });
  await browser.close();
  shot = true;
} catch {
  console.log("playwright unavailable; HTML written, PNG skipped");
}
if (shot) console.log(`wrote ${out}`);
