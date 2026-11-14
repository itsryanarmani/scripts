#!/usr/bin/env node
// HTML statics for notes, iMessage, and blurred-PDF ads (4:5 and 9:16).
// No logos, no invented testimonials. Placeholder names only (Alex, a friend).

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
}[c]));

const size = (aspect) => aspect === "9:16" ? [1080, 1920] : [1080, 1350];

function shell(aspect, font, body) {
  const [w, h] = size(aspect);
  const top = aspect === "9:16" ? 220 : 80;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<style>
*{box-sizing:border-box;margin:0}
body{width:${w}px;height:${h}px;background:#f4f4f5;color:#111;font-family:${font};padding:${top}px 72px 96px;overflow:hidden}
</style></head><body>${body}</body></html>`;
}

export function notesTemplate({ aspect = "4:5", headline = "Things nobody told me", items = ["Start with the hard step", "Write the checklist once", "Keep the price on the page"], name = "Alex" } = {}) {
  const lis = items.map((item) => `<li>${esc(item)}</li>`).join("");
  return shell(aspect, 'system-ui,-apple-system,sans-serif',
    `<div style="color:#d4a017;font:600 28px system-ui">Notes</div>
<div style="font:600 36px/1.25 system-ui;margin:24px 0 12px">${esc(headline)}</div>
<ul style="font:22px/1.6 system-ui;padding-left:28px">${lis}</ul>
<div style="margin-top:8px;color:#d4a017">▌</div>`);
}

export function imessageTemplate({ aspect = "4:5", sender = "Alex", recipient = "a friend", pain = "I needed a straight answer on this.", recommendation = "This short guide laid it out clearly.", title = "A short guide" } = {}) {
  const grey = "background:#e5e5ea;color:#000;border-radius:16px;padding:12px 16px;max-width:70%;font:20px/1.4 system-ui";
  const blue = "background:#0b84ff;color:#fff;border-radius:16px;padding:12px 16px;max-width:70%;margin-left:auto;font:20px/1.4 system-ui";
  return shell(aspect, 'system-ui,-apple-system,sans-serif',
    `<div style="color:#666;font:14px system-ui;margin-bottom:16px">iMessage · ${esc(sender)}</div>
<div style="${grey}">${esc(pain)}</div>
<div style="${blue};margin-top:10px">${esc(recommendation)}</div>
<div style="margin:12px 0 0 auto;max-width:70%;border:1px solid #ddd;border-radius:12px;padding:12px;background:#fff;font:18px system-ui">${esc(title)}</div>
<div style="color:#888;font:14px system-ui;margin-top:14px">${esc(recipient)} is typing…</div>`);
}

export function blurredPdfTemplate({ aspect = "4:5", title = "The field guide", body = "A table of contents and the first pages sit here, blurred so the title stays the hook." } = {}) {
  return shell(aspect, 'Georgia,serif',
    `<div style="font:600 40px/1.2 Georgia">${esc(title)}</div>
<div style="margin-top:28px;filter:blur(8px);color:#333;font:22px/1.5 Georgia">${esc(body)}</div>
<div style="margin-top:40px;color:#444;font:18px system-ui">See what’s inside</div>`);
}

const generators = { notes: notesTemplate, imessage: imessageTemplate, "blurred-pdf": blurredPdfTemplate };

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const arg = (flag, fallback) => {
    const i = args.indexOf(flag);
    return i >= 0 ? args[i + 1] : fallback;
  };
  const format = args[0];
  const fn = generators[format];
  if (!fn) {
    console.error("usage: node templates.mjs <notes|imessage|blurred-pdf> [--aspect 4:5|9:16]");
    process.exit(2);
  }
  process.stdout.write(fn({ aspect: arg("--aspect", "4:5"), headline: arg("--headline"), title: arg("--title"), body: arg("--body") }));
}
