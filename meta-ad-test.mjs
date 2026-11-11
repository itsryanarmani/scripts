#!/usr/bin/env node
// meta-ad-test — create a small Meta test (1 campaign, 1 ad set, N ads) from a plan file. Everything starts PAUSED.
//
//   set -a; . <your meta env file>; set +a
//   meta-ad-test.mjs plan.json             # dry run: validates the plan, prints payloads, sends nothing
//   meta-ad-test.mjs plan.json --create    # uploads images, creates every object PAUSED, writes created.json
//   I_APPROVE_SPEND=yes meta-ad-test.mjs plan.json --activate   # checks the pages, sets the flight, goes ACTIVE
//   meta-ad-test.mjs plan.json --pause     # pauses the campaign, the ad set and every ad
//   meta-ad-test.mjs plan.json --report    # spend, CTR and CPC per ad vs the plan; verdict per ad (read only)
//   meta-ad-test.mjs plan.json --report --apply-kill-gate   # also pause every ad that hit its kill gate
//   meta-ad-test.mjs plan.json --report --insights saved.json [--md report.md]   # offline: read a saved fixture
//
// Environment: META_MARKETING_TOKEN, META_ADS_AD_ACCOUNT_ID, META_PIXEL_ID (optional). The token goes in a
// header, is never printed, and is scrubbed from every error.
//
// plan = {
//   campaign: { name, slug, objective?, lifetimeBudget, currencyMinorUnit?, flightDays, pageId, baseUrl,
//               geo: { regionKey } | { countries: ["CA"] }, age: [min, max], placements: { facebook: ["feed"],
//               instagram: ["stream"] }, optimizationGoal?, targetingSuggestions?: { <id>: <label> } },
//   utmTemplate: "utm_source=meta&...&utm_content={ad}&utm_term={persona}&meta_ad_id={{ad.id}}",
//   creativesDir: "creatives",                     // relative to the plan; holds each ad's image file
//   ads: [ { id, persona, landing, creative, headline, description, primaryText, cta, hypothesis, killGate } ]
// }
// An ad may carry expected: { ctr: "0.6-1.0%", cpc: "2.70-4.50" }, outcome and nextHypothesis (the experiment log).
// A kill gate the report can act on reads: "Stop this ad if it has spent CAD 12 with fewer than 2 link clicks."
// The tool refuses a plan with no geo, no lifetime budget, no flight, or an ad with no hypothesis or kill gate.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const argv = process.argv.slice(2);
const planPath = argv.find((a) => !a.startsWith("--"));
if (!planPath) {
  console.error("usage: meta-ad-test.mjs plan.json [--create|--activate|--pause]");
  process.exit(2);
}
const mode = argv.includes("--create") ? "create" : argv.includes("--activate") ? "activate" : argv.includes("--pause") ? "pause" : argv.includes("--report") ? "report" : "dry";
const flagValue = (name) => (argv.includes(name) ? argv[argv.indexOf(name) + 1] : undefined);
const insightsFile = flagValue("--insights");
const mdFile = flagValue("--md");
const applyKillGate = argv.includes("--apply-kill-gate");
const root = dirname(resolve(planPath));
const plan = JSON.parse(readFileSync(planPath, "utf8"));
const { campaign: c, ads } = plan;
const createdFile = join(root, "created.json");

function validate() {
  const need = (ok, msg) => {
    if (!ok) throw new Error(`plan refused: ${msg}`);
  };
  need(c?.name && c.slug && c.pageId && c.baseUrl, "campaign needs name, slug, pageId and baseUrl");
  need(c.geo && (c.geo.regionKey || c.geo.countries?.length), "campaign.geo is required (a default geo spends in the wrong place)");
  need(Number.isFinite(c.lifetimeBudget) && c.lifetimeBudget > 0, "campaign.lifetimeBudget is required (a cap Meta cannot exceed)");
  need(Number.isInteger(c.flightDays) && c.flightDays > 0, "campaign.flightDays is required");
  need(Array.isArray(c.age) && c.age.length === 2, "campaign.age must be [min, max]");
  need(plan.utmTemplate?.includes("utm_content={ad}"), "utmTemplate must carry utm_content={ad}");
  need(Array.isArray(ads) && ads.length > 0, "plan needs at least one ad");
  for (const ad of ads) {
    need(ad.id && ad.landing && ad.creative && ad.headline && ad.primaryText, `ad ${ad.id ?? "?"} is missing id, landing, creative, headline or primaryText`);
    need(ad.hypothesis && ad.killGate, `ad ${ad.id} needs a hypothesis and a kill gate`);
  }
}
// --pause must work from the saved ids even when the plan no longer validates.
if (mode !== "pause") validate();

const TOKEN = process.env.META_MARKETING_TOKEN ?? "";
const ACT = `act_${(process.env.META_ADS_AD_ACCOUNT_ID ?? "").replace(/^act_/, "")}`;
const PIXEL = process.env.META_PIXEL_ID ?? "";
const GRAPH = "https://graph.facebook.com/v21.0";
if (mode === "report" && !existsSync(createdFile)) throw new Error("no created.json next to the plan. Run --create first.");
if (mode !== "dry" && !(mode === "report" && insightsFile) && (!TOKEN || ACT === "act_")) throw new Error("set META_MARKETING_TOKEN and META_ADS_AD_ACCOUNT_ID first");

const scrub = (s) => (TOKEN ? String(s).split(TOKEN).join("[redacted]") : String(s));
async function graph(path, method, body) {
  const res = await fetch(`${GRAPH}/${path}`, {
    method,
    headers: { authorization: `Bearer ${TOKEN}`, ...(body instanceof FormData ? {} : { "content-type": "application/json" }) },
    body: body instanceof FormData ? body : body && JSON.stringify(body),
  });
  const json = await res.json();
  if (!res.ok || json.error) {
    throw new Error(scrub(`graph ${method} ${path.split("?")[0]}: ${json.error?.error_user_msg ?? json.error?.message ?? res.status} (code ${json.error?.code}/${json.error?.error_subcode})`));
  }
  return json;
}

// Pause runs first and needs only the saved ids, so a broken plan cannot block an emergency stop.
async function pauseAll() {
  const made = JSON.parse(readFileSync(createdFile, "utf8"));
  for (const id of [made.campaign, made.adset, ...Object.values(made.ads)]) await graph(id, "POST", { status: "PAUSED" });
}
if (mode === "pause") {
  await pauseAll();
  console.log("PAUSED all");
  process.exit(0);
}

const slug = (s) => s.replace(/-/g, "_");
const utm = (ad) => plan.utmTemplate.replace("{campaign}", c.slug).replace("{ad}", slug(ad.id)).replace("{persona}", slug(ad.persona ?? "all"));
const link = (ad) => `${c.baseUrl}${ad.landing}`;

const targeting = {
  geo_locations: c.geo.regionKey ? { regions: [{ key: c.geo.regionKey }] } : { countries: c.geo.countries },
  age_min: c.age[0],
  age_max: c.age[1],
  publisher_platforms: Object.keys(c.placements ?? { facebook: 1, instagram: 1 }),
  ...(c.placements?.facebook ? { facebook_positions: c.placements.facebook } : {}),
  ...(c.placements?.instagram ? { instagram_positions: c.placements.instagram } : {}),
  // Automatic audience on: suggestions are hints, not a hard filter. A narrow hard filter can fall under
  // the platform's reporting floor and saturate on a small budget.
  targeting_automation: { advantage_audience: 1 },
  ...(c.targetingSuggestions ? { flexible_spec: [{ work_positions: Object.entries(c.targetingSuggestions).map(([id, name]) => ({ id, name })) }] } : {}),
};

const flight = (fromMs) => ({ start_time: new Date(fromMs).toISOString(), end_time: new Date(fromMs + c.flightDays * 86_400_000).toISOString() });

const payloads = (hashes = {}) => ({
  campaign: { name: c.name, objective: c.objective ?? "OUTCOME_TRAFFIC", status: "PAUSED", special_ad_categories: [], is_adset_budget_sharing_enabled: false },
  adset: (campaignId) => ({
    name: `${c.name} | ad set`,
    campaign_id: campaignId,
    status: "PAUSED",
    billing_event: "IMPRESSIONS",
    optimization_goal: c.optimizationGoal ?? "LINK_CLICKS",
    bid_strategy: "LOWEST_COST_WITHOUT_CAP",
    destination_type: "WEBSITE",
    lifetime_budget: Math.round(c.lifetimeBudget * (c.currencyMinorUnit ?? 100)),
    ...flight(Date.now() + 86_400_000), // provisional: --activate resets it
    targeting,
  }),
  creative: (ad) => ({
    name: `${ad.id} creative`,
    url_tags: utm(ad),
    // Keep the words and the picture as designed. Copy rules may forbid machine-written claims.
    degrees_of_freedom_spec: { creative_features_spec: Object.fromEntries(["text_optimizations", "image_touchups", "enhance_cta", "inline_comment", "add_text_overlay", "image_brightness_and_contrast"].map((f) => [f, { enroll_status: "OPT_OUT" }])) },
    object_story_spec: {
      page_id: c.pageId,
      link_data: {
        link: link(ad),
        message: ad.primaryText,
        name: ad.headline,
        description: ad.description,
        image_hash: hashes[ad.id] ?? "<image_hash>",
        call_to_action: { type: ad.cta ?? "LEARN_MORE", value: { link: link(ad) } },
      },
    },
  }),
  ad: (ad, adsetId, creativeId) => ({
    name: `[${c.slug}] ${ad.id}`,
    adset_id: adsetId,
    creative: { creative_id: creativeId },
    status: "PAUSED",
    ...(PIXEL ? { tracking_specs: [{ "action.type": ["offsite_conversion"], fb_pixel: [PIXEL] }] } : {}),
  }),
});

if (mode === "dry") {
  const p = payloads();
  console.log("DRY RUN. The plan is valid. Nothing is sent.\n");
  console.log("campaign:", JSON.stringify(p.campaign));
  console.log("adset:", JSON.stringify(p.adset("<campaign_id>")));
  for (const ad of ads) console.log(`ad ${ad.id}: ${link(ad)}?${utm(ad)}`);
  console.log(`lifetime budget: ${c.lifetimeBudget} over ${c.flightDays} days`);
}

if (mode === "create") {
  if (existsSync(createdFile)) throw new Error("created.json exists. Delete the old campaign and the file first.");
  const hashes = {};
  for (const ad of ads) {
    const form = new FormData();
    form.append("filename", new Blob([readFileSync(join(root, plan.creativesDir ?? "creatives", ad.creative))]), ad.creative);
    hashes[ad.id] = Object.values((await graph(`${ACT}/adimages`, "POST", form)).images)[0].hash;
  }
  const p = payloads(hashes);
  const created = { campaign: null, adset: null, ads: {} };
  try {
    created.campaign = (await graph(`${ACT}/campaigns`, "POST", p.campaign)).id;
    created.adset = (await graph(`${ACT}/adsets`, "POST", p.adset(created.campaign))).id;
    for (const ad of ads) {
      const creative = (await graph(`${ACT}/adcreatives`, "POST", p.creative(ad))).id;
      created.ads[ad.id] = (await graph(`${ACT}/ads`, "POST", p.ad(ad, created.adset, creative))).id;
    }
  } catch (err) {
    console.error(scrub(err.message));
    if (created.campaign) {
      await graph(created.campaign, "DELETE").catch(() => {});
      console.error("rolled back: campaign deleted");
    }
    process.exit(1);
  }
  writeFileSync(createdFile, JSON.stringify(created, null, 2));
  console.log("created, all PAUSED:", JSON.stringify(created));
}

if (mode === "activate") {
  if (process.env.I_APPROVE_SPEND !== "yes") throw new Error(`Going live spends up to ${c.lifetimeBudget}. Set I_APPROVE_SPEND=yes.`);
  const made = JSON.parse(readFileSync(createdFile, "utf8"));
  // Trust the saved objects, not the plan file: the plan may have been edited since --create.
  const saved = await graph(`${made.adset}?fields=lifetime_budget`, "GET");
  const planned = Math.round(c.lifetimeBudget * (c.currencyMinorUnit ?? 100));
  if (Number(saved.lifetime_budget) !== planned) throw new Error(`ad set budget is ${saved.lifetime_budget} but the plan says ${planned}. Refusing to activate.`);
  for (const ad of ads) {
    const res = await fetch(link(ad), { redirect: "follow" });
    if (res.status !== 200) throw new Error(`${link(ad)} answers ${res.status}. Ship the landing pages first.`);
  }
  // Meta allows one call per object every 30 seconds, and locks a start time that is under 15 minutes away.
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const retryRate = async (fn) => {
    for (let i = 0; ; i++) {
      try {
        return await fn();
      } catch (err) {
        if (i >= 3 || !/code 613\//.test(err.message)) throw err;
        await sleep(35_000);
      }
    }
  };
  try {
    await retryRate(() => graph(made.adset, "POST", flight(Date.now() + 300_000)));
    await sleep(35_000); // the flight call counts against the ad set's rate limit
  } catch (err) {
    if (!/1815377/.test(err.message)) throw err;
    const saved = await graph(`${made.adset}?fields=end_time`, "GET");
    if (!(Date.parse(saved.end_time) > Date.now() + 3_600_000)) throw new Error(`flight is locked and the saved end time ${saved.end_time} is not in the future. Recreate the ad set.`);
    console.log(`flight already locked by Meta; keeping the saved dates (ends ${saved.end_time})`);
  }
  try {
    for (const id of [made.adset, ...Object.values(made.ads), made.campaign]) await retryRate(() => graph(id, "POST", { status: "ACTIVE" }));
  } catch (err) {
    // A half-activated test can spend. Put everything back to PAUSED before failing.
    await pauseAll().catch(() => {});
    throw new Error(`activation failed, everything paused: ${err.message}`);
  }
  // Read the real state back. A success message from the POST is not proof.
  const states = await Promise.all([made.campaign, made.adset, ...Object.values(made.ads)].map(async (id) => [id, (await graph(`${id}?fields=effective_status`, "GET")).effective_status]));
  const notActive = states.filter(([, st]) => st !== "ACTIVE");
  if (notActive.length) console.log("NOT ACTIVE after activation:", JSON.stringify(notActive), "(ads in review show IN_PROCESS or PENDING_REVIEW)");
  console.log(`ACTIVE. Lifetime cap ${c.lifetimeBudget}. ${states.length - notActive.length} of ${states.length} objects ACTIVE.`);
}


// ---- report: read only unless --apply-kill-gate -------------------------------------------------------------
if (mode === "report") {
  if (applyKillGate && insightsFile) throw new Error("--apply-kill-gate refuses to act on a saved fixture. Run it against the live account.");
  const made = JSON.parse(readFileSync(createdFile, "utf8"));
  async function allInsights() {
    // Follow every page. An ad on a later page would otherwise read as no delivery and escape its gate.
    const rows = [];
    let after;
    do {
      const r = await graph(`${made.adset}/insights?level=ad&date_preset=maximum&limit=100&fields=ad_id,spend,impressions,inline_link_clicks,inline_link_click_ctr,cost_per_inline_link_click${after ? `&after=${after}` : ""}`, "GET");
      rows.push(...(r.data ?? []));
      after = r.paging?.next ? r.paging.cursors?.after : undefined;
    } while (after);
    return rows;
  }
  const read = insightsFile
    ? JSON.parse(readFileSync(insightsFile, "utf8"))
    : {
        adset: await graph(`${made.adset}?fields=effective_status,lifetime_budget,budget_remaining`, "GET"),
        ads: Object.fromEntries(await Promise.all(Object.values(made.ads).map(async (id) => [id, await graph(`${id}?fields=effective_status`, "GET")]))),
        currency: (await graph(`${ACT}?fields=currency`, "GET")).currency,
        insights: await allInsights(),
      };
  const range = (text) => {
    const m = /(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)/.exec(String(text ?? ""));
    return m ? [Number(m[1]), Number(m[2])] : null;
  };
  const parseGate = (text) => {
    // Exact form only, with a currency code. A looser match can pause the wrong ad.
    const m = /^Stop this ad if it has spent ([A-Z]{3}) (\d+(?:\.\d+)?) with fewer than (\d+) link clicks?\.?$/.exec(String(text ?? "").trim());
    return m ? { currency: m[1], spend: Number(m[2]), clicks: Number(m[3]) } : null;
  };
  const MIN_IMPRESSIONS = 1000;
  const rows = ads.map((ad) => {
    const id = made.ads[ad.id];
    const row = (read.insights ?? []).find((r) => r.ad_id === id);
    const status = read.ads?.[id]?.effective_status ?? "UNKNOWN";
    // Meta leaves a metric out of a row when it is zero, so a missing click count on a row that has impressions means zero.
    const spend = Number(row?.spend ?? 0), impressions = Number(row?.impressions ?? 0), clicks = Number(row?.inline_link_clicks ?? 0);
    const ctr = Math.round(Number(row?.inline_link_click_ctr ?? 0) * 100) / 100, cpc = Math.round(Number(row?.cost_per_inline_link_click ?? 0) * 100) / 100;
    const parsed = parseGate(ad.killGate);
    const gate = parsed && read.currency && parsed.currency === read.currency ? parsed : null;
    const expCtr = range(ad.expected?.ctr), expCpcText = ad.expected?.cpc ?? Object.entries(ad.expected ?? {}).find(([k]) => /cpc/i.test(k))?.[1], expCpc = range(expCpcText);
    const notes = [];
    if (!gate) notes.push("gate unreadable: not acted on, check it by hand");
    let verdict, why;
    if (!row) { verdict = "WAIT"; why = "no delivery yet"; }
    else if (gate && spend >= gate.spend && clicks < gate.clicks) { verdict = "KILL"; why = `spent ${spend.toFixed(2)} with ${clicks} link clicks (gate: ${gate.spend} and ${gate.clicks})`; }
    else if (impressions < MIN_IMPRESSIONS) { verdict = "WAIT"; why = `only ${impressions} impressions, under ${MIN_IMPRESSIONS}`; }
    else if (expCtr && ctr > expCtr[1]) { verdict = "LEADING"; why = `CTR ${ctr}% is above the expected ${expCtr[0]}-${expCtr[1]}%`; }
    else if (expCtr && ctr < expCtr[0]) { verdict = "WATCH"; why = `CTR ${ctr}% is below the expected ${expCtr[0]}-${expCtr[1]}%`; }
    else { verdict = "ON TRACK"; why = expCtr ? `CTR ${ctr}% is inside the expected range` : "no expected CTR in the plan"; }
    if (expCpc && cpc && cpc > expCpc[1]) notes.push(`CPC ${cpc} is above the expected ${expCpc[0]}-${expCpc[1]}`);
    return { ad, id, status, spend, impressions, clicks, ctr, cpc, verdict, why, notes, expCtr, expCpc, expCpcText };
  });
  const out = [];
  const a = read.adset ?? {};
  out.push(`ad set ${a.effective_status ?? "?"}: budget remaining ${a.budget_remaining ?? "?"} of ${a.lifetime_budget ?? "?"} (minor units)`);
  for (const r of rows) {
    out.push("", `${r.ad.id}  ${r.verdict}  [${r.status}]  spend ${r.spend.toFixed(2)}  impressions ${r.impressions}  link clicks ${r.clicks}  CTR ${r.ctr}%  CPC ${r.cpc}`);
    out.push(`  verdict: ${r.why}`, `  hypothesis: ${r.ad.hypothesis}`, `  expected: ctr ${r.ad.expected?.ctr ?? "-"}, cpc ${r.expCpcText ?? "-"}; kill gate: ${r.ad.killGate}`);
    for (const n of r.notes) out.push(`  note: ${n}`);
    if (r.ad.outcome) out.push(`  outcome: ${r.ad.outcome}`);
    if (r.ad.nextHypothesis) out.push(`  next hypothesis: ${r.ad.nextHypothesis}`);
  }
  const done = rows.filter((r) => r.verdict === "KILL" || r.verdict === "LEADING");
  if (done.length) out.push("", `Record an outcome and a nextHypothesis in the plan for: ${done.map((r) => r.ad.id).join(", ")}.`);
  console.log(scrub(out.join("\n")));
  if (mdFile) {
    const md = ["| ad | verdict | spend | impressions | link clicks | CTR | CPC | hypothesis |", "|---|---|---|---|---|---|---|---|", ...rows.map((r) => `| ${r.ad.id} | ${r.verdict} | ${r.spend.toFixed(2)} | ${r.impressions} | ${r.clicks} | ${r.ctr}% | ${r.cpc} | ${String(r.ad.hypothesis).replace(/\|/g, "/")} |`)];
    writeFileSync(mdFile, scrub(md.join("\n") + "\n"));
  }
  if (applyKillGate) {
    for (const r of rows.filter((x) => x.verdict === "KILL" && !["PAUSED", "ARCHIVED", "DELETED"].includes(x.status))) {
      await graph(r.id, "POST", { status: "PAUSED" });
      console.log(`PAUSED ${r.ad.id}: ${r.why}`);
    }
  }
}
