#!/usr/bin/env node
// ad-creatives-render — turn a JSON spec into static ad PNGs (HTML template -> headless screenshot).
//
//   node ad-creatives-render.mjs spec.json [outDir]
//
// Text, UI and logo-heavy creatives belong in a template, not an image model: the DOM prints every
// character and every colour exactly. Needs `playwright` resolvable from the current directory.
//
// spec = {
//   brand: { name, url, cta, logoSvg?, fontDisplay?, fontBody?, googleFonts? },
//   themes?: { <name>: { bg, fg, mute, accent, card, line, btnBg, btnFg } },   // any CSS colour
//   ads: [ { id, theme, template: "statement"|"timeline"|"form"|"chips", ...props } ]
// }
// statement: eyebrow, headline, sub.   timeline: headline, steps [[label, tag, done]].
// form: headline, sub, fields [[label, placeholder]].   chips: headline, sub, chips [[strong, rest]].
//
// Every ad renders at feed 1080x1350 and story 1080x1920. The story keeps the platform's UI safe zones
// (250 px top, 340 px bottom) free. Output: <outDir>/<id>__feed.png, <id>__story.png, manifest.json.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const [specPath, outArg] = process.argv.slice(2);
if (!specPath) {
  console.error("usage: ad-creatives-render.mjs spec.json [outDir]");
  process.exit(2);
}
const spec = JSON.parse(readFileSync(specPath, "utf8"));
const out = outArg ?? "creatives";
mkdirSync(out, { recursive: true });

const DEFAULT_THEMES = {
  light: { bg: "#fafafa", fg: "#16181d", mute: "#5b6270", accent: "#4f46e5", card: "#ffffff", line: "#e4e6eb", btnBg: "#4f46e5", btnFg: "#ffffff" },
  dark: { bg: "#0d0f13", fg: "#f1f2f5", mute: "#a7adba", accent: "#8b87ff", card: "#171a20", line: "#2a2e37", btnBg: "#8b87ff", btnFg: "#0d0f13" },
  accent: { bg: "#3f3fc4", fg: "#ffffff", mute: "#dcdcff", accent: "#ffffff", card: "#4a4ad0", line: "#6b6be0", btnBg: "#ffffff", btnFg: "#2d2da0" },
};
const themes = { ...DEFAULT_THEMES, ...(spec.themes ?? {}) };
const brand = spec.brand ?? {};
for (const k of ["name", "url", "cta"]) if (!brand[k]) throw new Error(`spec.brand.${k} is required`);
const display = brand.fontDisplay ?? "Georgia, serif";
const body = brand.fontBody ?? "system-ui, sans-serif";
const fontLink = brand.googleFonts ? `<link href="${brand.googleFonts}" rel="stylesheet">` : "";

const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
const SIZES = { feed: [1080, 1350], story: [1080, 1920] };

const frame = (t, h, inner) => {
  const story = h > 1500;
  return `<!doctype html><html><head><meta charset="utf-8">${fontLink}<style>
*{box-sizing:border-box;margin:0}
body{width:1080px;height:${h}px;background:${t.bg};color:${t.fg};font-family:${body};display:flex;flex-direction:column;padding:${story ? 250 : 88}px 88px ${story ? 340 : 80}px;overflow:hidden}
.brand{display:flex;align-items:center;gap:16px;font-size:42px;font-weight:600;letter-spacing:-.02em}
.brand svg{width:56px;height:56px;color:${t.accent}}
.main{flex:1;display:flex;flex-direction:column;justify-content:center;gap:40px}
.eyebrow{font-size:30px;font-weight:500;letter-spacing:.14em;text-transform:uppercase;color:${t.accent}}
h1{font-family:${display};font-weight:600;font-size:${story ? 128 : 112}px;line-height:1.03;letter-spacing:-.02em;word-spacing:.08em;text-wrap:balance}
.sub{font-size:40px;line-height:1.35;color:${t.mute};max-width:860px}
.foot{display:flex;align-items:center;justify-content:space-between}
.btn{background:${t.btnBg};color:${t.btnFg};font-size:36px;font-weight:600;padding:26px 44px;border-radius:18px}
.url{font-size:32px;color:${t.mute}}
.card{background:${t.card};border:2px solid ${t.line};border-radius:28px;padding:40px}
.row{display:flex;align-items:center;gap:24px;padding:22px 0;border-bottom:2px solid ${t.line};font-size:34px}
.row:last-child{border-bottom:0}
.dot{width:36px;height:36px;border-radius:50%;background:${t.accent};flex:none;display:grid;place-items:center;color:${t.bg};font-size:22px;font-weight:600}
.dot.off{background:transparent;border:3px solid ${t.line}}
.tag{margin-left:auto;font-size:26px;color:${t.mute}}
.chips{display:flex;flex-wrap:wrap;gap:18px}
.chip{border:2px solid ${t.line};background:${t.card};border-radius:999px;padding:18px 34px;font-size:36px;font-weight:500}
.chip b{color:${t.accent}}
.lab{font-size:26px;font-weight:500;margin-top:22px}.lab:first-child{margin-top:0}
.field{border:2px solid ${t.line};border-radius:14px;padding:20px 24px;font-size:30px;color:${t.mute};background:${t.bg};margin-top:12px}
</style></head><body>
<div class="brand">${brand.logoSvg ?? ""}<span>${esc(brand.name)}</span></div>
<div class="main">${inner}</div>
<div class="foot"><div class="btn">${esc(brand.cta)} →</div><div class="url">${esc(brand.url)}</div></div>
</body></html>`;
};

const TEMPLATES = {
  statement: (a) => `${a.eyebrow ? `<div class="eyebrow">${esc(a.eyebrow)}</div>` : ""}<h1>${esc(a.headline)}</h1>${a.sub ? `<div class="sub">${esc(a.sub)}</div>` : ""}`,
  timeline: (a) => `<h1 style="font-size:96px">${esc(a.headline)}</h1><div class="card">${a.steps.map(([s, who, done]) => `<div class="row"><div class="dot ${done ? "" : "off"}">${done ? "✓" : ""}</div><span>${esc(s)}</span><span class="tag">${esc(who)}</span></div>`).join("")}</div>`,
  form: (a) => `<h1 style="font-size:96px">${esc(a.headline)}</h1>${a.sub ? `<div class="sub">${esc(a.sub)}</div>` : ""}<div class="card">${a.fields.map(([l, p]) => `<div class="lab">${esc(l)}</div><div class="field">${esc(p)}</div>`).join("")}</div>`,
  chips: (a) => `<h1 style="font-size:96px">${esc(a.headline)}</h1>${a.sub ? `<div class="sub">${esc(a.sub)}</div>` : ""}<div class="chips">${a.chips.map(([s, r]) => `<div class="chip"><b>${esc(s)}</b> ${esc(r ?? "")}</div>`).join("")}</div>`,
};

const { chromium } = await import("playwright");
const browser = await chromium.launch();
const manifest = [];
try {
  for (const ad of spec.ads) {
    const make = TEMPLATES[ad.template];
    const theme = themes[ad.theme];
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(ad.id ?? "")) throw new Error(`ad id ${JSON.stringify(ad.id)} must use only letters, digits, - and _`);
    if (!make) throw new Error(`ad ${ad.id ?? "?"}: unknown template ${ad.template}`);
    if (!theme) throw new Error(`ad ${ad.id}: unknown theme ${ad.theme}`);
    for (const [size, [w, h]] of Object.entries(SIZES)) {
      const page = await browser.newPage({ viewport: { width: w, height: h } });
      await page.setContent(frame(theme, h, make(ad)), { waitUntil: "networkidle" });
      await page.evaluate(() => document.fonts.ready);
      const file = `${ad.id}__${size}.png`;
      await page.screenshot({ path: join(out, file) });
      await page.close();
      manifest.push({ id: ad.id, size, file });
    }
  }
} finally {
  await browser.close();
}
writeFileSync(join(out, "manifest.json"), JSON.stringify(manifest, null, 2));
console.log(`rendered ${manifest.length} images to ${out}`);
