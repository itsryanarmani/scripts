#!/usr/bin/env node
// Claim a verified ChatGPT business profile for each site of a multi-site
// directory monorepo, by DNS TXT. Drives the user's logged-in browser through
// `browse` and writes the one TXT record through the Cloudflare API.
//
//   chatgpt-business-claim.mjs plan  <repo-dir>
//   chatgpt-business-claim.mjs claim <repo-dir> <site...> [--yes]
//
// Without --yes, `claim` stops before every write and exits 0. The TXT value
// and the API token are never printed or saved.
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { Resolver } from "node:dns/promises";
import { join } from "node:path";

// Customer type is a factual claim to OpenAI, so each run names it. No default.
const TYPES = {
  "online-store": "Through an online store",
  "physical-location": "At a physical location",
};

const HUB = "https://chatgpt.com/business-hub";
const SESSION = process.env.BROWSE_SESSION || "personal";
const TOKEN = process.env.CLOUDFLARE_API_TOKEN || process.env.CF_API_TOKEN || "";
const OUT = process.env.CLAIM_OUT || "e2e-artifacts/chatgpt-business-claim";

const die = (msg) => {
  console.error(`error: ${msg}`);
  process.exit(1);
};

// Read name and domain from sites/<id>/directory.config.ts.
export function listSites(repo) {
  const root = join(repo, "sites");
  return readdirSync(root, { withFileTypes: true })
    .filter((d) => d.isDirectory() && !d.name.startsWith("_"))
    .flatMap((d) => {
      let src;
      try {
        src = readFileSync(join(root, d.name, "directory.config.ts"), "utf8");
      } catch {
        return [];
      }
      const name = /^\s*name:\s*"([^"]+)"/m.exec(src)?.[1];
      const domain = /^\s*domain:\s*"([^"]+)"/m.exec(src)?.[1];
      return name && domain ? [{ id: d.name, name, domain }] : [];
    });
}

// Run Playwright code in the user's browser. Arguments pass as JSON, never
// by string concatenation of untrusted text into code.
function browse(code, args = {}) {
  const body = `const A = ${JSON.stringify(args)};\n${code}`;
  const out = execFileSync(
    "browse",
    ["execute", "--session", SESSION, body],
    { encoding: "utf8", timeout: 120_000 },
  );
  return out.split("\nConsole logs:")[0].trim();
}

async function cf(path, init = {}) {
  const res = await fetch(`https://api.cloudflare.com/client/v4${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
  });
  const j = await res.json();
  if (!j.success) throw new Error(`cloudflare ${path}: ${JSON.stringify(j.errors)}`);
  return j.result;
}

// Wait until a public resolver returns the record, so "Verify domain" does
// not run against a stale cache.
async function waitForTxt(host, value, tries = 18) {
  const r = new Resolver();
  r.setServers(["1.1.1.1"]);
  for (let i = 0; i < tries; i++) {
    const rows = await r.resolveTxt(host).catch(() => []);
    if (rows.some((p) => p.join("") === value)) return true;
    await new Promise((ok) => setTimeout(ok, 5000));
  }
  return false;
}

async function upsertTxt(domain, host, value) {
  const [zone] = await cf(`/zones?name=${encodeURIComponent(domain)}`);
  if (!zone) throw new Error(`no Cloudflare zone for ${domain}`);
  const found = await cf(`/zones/${zone.id}/dns_records?type=TXT&name=${encodeURIComponent(host)}`);
  const body = JSON.stringify({ type: "TXT", name: host, content: value, ttl: 60 });
  if (found[0]) await cf(`/zones/${zone.id}/dns_records/${found[0].id}`, { method: "PUT", body });
  else await cf(`/zones/${zone.id}/dns_records`, { method: "POST", body });
}

async function claim(site, yes, type) {
  const r = { site: site.id, domain: site.domain, stage: "start", ok: false };
  if (!yes) return { ...r, stage: "dry-run: no write made" };
  if (!TOKEN) die("set CLOUDFLARE_API_TOKEN");
  if (!TYPES[type]) die(`pass --type ${Object.keys(TYPES).join("|")}`);
  site = { ...site, typeLabel: TYPES[type], nameRe: site.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") };

  // 1. Search the Hub. A match means someone else's profile exists: stop.
  const search = browse(
    `await page.goto(${JSON.stringify(HUB)});
     const box = page.getByPlaceholder(/search business/i).or(page.getByRole("combobox")).or(page.getByRole("textbox")).first();
     await box.click(); await box.fill(A.name); await page.waitForTimeout(3500);
     return (await page.locator("main").innerText());`,
    site,
  );
  if (!/No matching business/i.test(search)) return { ...r, stage: "hub-has-match: review by hand" };

  // 2. Create the profile and read the TXT challenge.
  const challenge = browse(
    `await page.getByText(new RegExp("^Create .*" + A.nameRe)).first().click();
     const start = page.getByRole("button", { name: /get started/i });
     if (await start.isVisible({ timeout: 4000 }).catch(() => false)) await start.click();
     await page.getByText(A.typeLabel).first().click();
     await page.locator("input[name=business-website]").fill("https://" + A.domain);
     await page.getByRole("button", { name: /^continue$/i }).click();
     await page.getByText(/Verify that you control/).waitFor({ timeout: 60000 });
     return await page.locator("body").innerText();`,
    site,
  );
  const host = /Name or host\s+(\S+)/.exec(challenge)?.[1];
  const value = /Value or content\s+(openai-business-profile=[A-Za-z0-9_-]+)/.exec(challenge)?.[1];
  if (!host || !value) return { ...r, stage: "no-challenge-found: Hub UI changed" };
  if (host !== `openai-business-profile.${site.domain}`) return { ...r, stage: "unexpected-host: stop" };

  // 3. Write the one TXT record, then wait until a public resolver sees it.
  await upsertTxt(site.domain, host, value);
  if (!(await waitForTxt(host, value))) return { ...r, stage: "dns-not-visible: record written, verify by hand" };

  // 4. Verify. Success moves the page on to profile details.
  const after = browse(
    `await page.getByRole("button", { name: /verify domain/i }).click();
     await page.waitForTimeout(8000);
     return await page.locator("body").innerText();`,
  );
  const ok = /Help people get to know/i.test(after);
  return { ...r, ok, stage: ok ? "verified" : "verify-failed: verify by hand in the Hub" };
}

const [cmd, repo, ...rest] = process.argv.slice(2);
if (!cmd || !repo) die("usage: plan|claim <repo-dir> [site...] [--yes]");
const yes = rest.includes("--yes");
const typeAt = rest.indexOf("--type");
const type = typeAt >= 0 ? rest[typeAt + 1] : undefined;
const ids = rest.filter((a, i) => !a.startsWith("--") && (typeAt < 0 || i !== typeAt + 1));
const sites = listSites(repo);

if (cmd === "plan") {
  for (const s of sites) console.log(`${s.id}\t${s.name}\t${s.domain}`);
} else if (cmd === "claim") {
  if (!ids.length) die("name at least one site; no default of all");
  const todo = ids.map((id) => sites.find((s) => s.id === id) ?? die(`unknown site ${id}`));
  const results = [];
  mkdirSync(OUT, { recursive: true });
  const save = () =>
    writeFileSync(
      join(OUT, "result.json"),
      JSON.stringify({ at: new Date().toISOString(), yes, results }, null, 2),
    );
  for (const s of todo) {
    try {
      results.push(await claim(s, yes, type));
    } catch (e) {
      // Keep the message only: it holds no token or TXT value.
      results.push({ site: s.id, domain: s.domain, ok: false, stage: `error: ${String(e.message).split("\n")[0].slice(0, 200)}` });
    }
    save();
  }
  console.log(JSON.stringify(results, null, 2));
  process.exit(results.every((r) => r.ok || !yes) ? 0 : 1);
} else die(`unknown command ${cmd}`);
