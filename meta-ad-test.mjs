#!/usr/bin/env node
// meta-ad-test — create a small Meta test (1 campaign, 1 ad set, N ads) from a plan file. Everything starts PAUSED.
//
//   set -a; . <your meta env file>; set +a
//   meta-ad-test.mjs plan.json             # dry run: validates the plan, prints payloads, sends nothing
//   meta-ad-test.mjs plan.json --create    # uploads images, creates every object PAUSED, writes created.json
//   I_APPROVE_SPEND=yes meta-ad-test.mjs plan.json --activate   # checks the pages, sets the flight, goes ACTIVE
//   meta-ad-test.mjs plan.json --pause     # pauses the campaign, the ad set and every ad
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
// The tool refuses a plan with no geo, no lifetime budget, no flight, or an ad with no hypothesis or kill gate.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const argv = process.argv.slice(2);
const planPath = argv.find((a) => !a.startsWith("--"));
if (!planPath) {
  console.error("usage: meta-ad-test.mjs plan.json [--create|--activate|--pause]");
  process.exit(2);
}
const mode = argv.includes("--create") ? "create" : argv.includes("--activate") ? "activate" : argv.includes("--pause") ? "pause" : "dry";
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
if (mode !== "dry" && (!TOKEN || ACT === "act_")) throw new Error("set META_MARKETING_TOKEN and META_ADS_AD_ACCOUNT_ID first");

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
  await graph(made.adset, "POST", flight(Date.now() + 300_000));
  for (const id of [made.adset, ...Object.values(made.ads), made.campaign]) await graph(id, "POST", { status: "ACTIVE" });
  console.log("ACTIVE. Lifetime cap", c.lifetimeBudget);
}

if (mode === "pause") {
  const made = JSON.parse(readFileSync(createdFile, "utf8"));
  for (const id of [made.campaign, made.adset, ...Object.values(made.ads)]) await graph(id, "POST", { status: "PAUSED" });
  console.log("PAUSED all");
}
