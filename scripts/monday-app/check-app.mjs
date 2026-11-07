#!/usr/bin/env node
/**
 * Pre-submission checks for a monday.com marketplace app. Runs the two checks
 * that are cheap to run and each caught a real problem when submitting by hand:
 *
 *   1. Install link     — GET https://auth.monday.com/oauth2/authorize?client_id=<id>&response_type=install
 *                          with redirects disabled, assert the response is a 302 whose
 *                          oauth_payload_token (Location query param or Set-Cookie) is a JWT
 *                          whose payload decodes to that same client id. Catches a dead or
 *                          mis-copied Client ID before reviewers hit it. The Client ID lives
 *                          on the app's General settings page in the Developer Center.
 *   2. Reviewer key     — GET <api-base>/posts and <api-base>/accounts with the bearer key,
 *                          assert both return 200. Catches silently-expired keys: a key that
 *                          worked in a previous session had expired by submission time.
 *
 * Usage:
 *   check-app.mjs --client-id <id>                             # check 1 only
 *   check-app.mjs --api-base <url> --api-key <key>             # check 2 only
 *   check-app.mjs --client-id <id> --api-base <url> --api-key <key>   # both
 *
 * Exit codes: 0 all checks passed, 1 a check failed, 2 usage error.
 * No dependencies beyond Node >= 18 (global fetch). See the monday-app-submission
 * skill in itsryanarmani/skills for the full Developer Center playbook.
 */
const INSTALL_URL = (clientId) =>
  `https://auth.monday.com/oauth2/authorize?client_id=${encodeURIComponent(clientId)}&response_type=install`;

const HELP = `Usage: check-app.mjs [options]

Pre-submission checks for a monday.com marketplace app.

Options:
  --client-id <id>      monday Client ID (Developer Center -> General settings).
                        Verifies the shareable install link returns a 302 whose
                        oauth_payload_token JWT decodes to this client id.
  --api-base <url>      Your API base URL (e.g. https://api.example.com).
  --api-key <key>       Bearer key handed to reviewers. GET /posts and
                        GET /accounts must both return 200.
                        Pass via --api-key or env MONDAY_API_KEY (avoids
                        putting the key in shell history / ps output).
  -h, --help            Show this help.

Runs whichever checks its options enable; pass all three to run both.
Exit codes: 0 pass, 1 a check failed, 2 usage error.`;

function usageError(msg) {
  console.error(`check-app.mjs: ${msg}\n\n${HELP}`);
  process.exit(2);
}

function parseArgs(argv) {
  const opts = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-h" || a === "--help") return { help: true };
    if (a === "--client-id" || a === "--api-base" || a === "--api-key") {
      const v = argv[i + 1];
      if (!v || v.startsWith("--")) usageError(`${a} requires a value`);
      const key = { "--client-id": "clientId", "--api-base": "apiBase", "--api-key": "apiKey" }[a];
      opts[key] = v;
      i++;
    } else {
      usageError(`unknown argument: ${a}`);
    }
  }
  if (opts.apiBase) opts.apiKey = opts.apiKey ?? process.env.MONDAY_API_KEY;
  if (!opts.clientId && !(opts.apiBase && opts.apiKey)) {
    usageError("need --client-id, or --api-base + --api-key (or env MONDAY_API_KEY), or all three");
  }
  if (opts.apiBase && opts.clientId && !opts.apiKey) {
    usageError("--api-base also needs --api-key (or env MONDAY_API_KEY)");
  }
  if (opts.apiKey && !opts.apiBase) usageError("--api-key also needs --api-base");
  return opts;
}

function decodeJwtPayload(token) {
  const parts = token.split(".");
  if (parts.length < 2) throw new Error("not a JWT (expected 3 dot-separated parts)");
  // JWT payloads are base64url without padding.
  const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
  const json = Buffer.from(b64, "base64").toString("utf8");
  return JSON.parse(json);
}

function findTokenValue(searchIn) {
  // oauth_payload_token has been observed in the 302 Location query string and
  // in Set-Cookie; accept either so a monday-side change doesn't break the check.
  for (const value of searchIn) {
    const m = /oauth_payload_token=([^&;"\s]+)/.exec(value);
    if (m) return decodeURIComponent(m[1]);
  }
  return null;
}

async function checkInstallLink(clientId) {
  const url = INSTALL_URL(clientId);
  let res;
  try {
    res = await fetch(url, { redirect: "manual" });
  } catch (e) {
    console.error(`FAIL install link: request to ${url} failed: ${e.message}`);
    return false;
  }
  const location = res.headers.get("location") ?? "";
  const cookies = res.headers.getSetCookie?.() ?? [];
  const token =
    findTokenValue([location, ...cookies]) ??
    findTokenValue([await res.text().catch(() => "")]);

  if (res.status !== 302) {
    console.error(`FAIL install link: expected 302, got ${res.status} for ${url}`);
    return false;
  }
  if (!token) {
    console.error(
      `FAIL install link: 302 ok but no oauth_payload_token in Location, Set-Cookie, or body`,
    );
    console.error(`  location: ${location || "(none)"}`);
    return false;
  }

  let payload;
  try {
    payload = decodeJwtPayload(token);
  } catch (e) {
    console.error(`FAIL install link: oauth_payload_token is not a decodable JWT: ${e.message}`);
    return false;
  }

  const inToken = payload.client_id ?? payload.clientId;
  if (inToken === clientId) {
    console.log(`ok   install link: 302, oauth_payload_token decodes to client_id ${clientId}`);
    return true;
  }
  console.error(`FAIL install link: token client id mismatch`);
  console.error(`  expected: ${clientId}`);
  console.error(`  in token: ${inToken ?? "(no client_id field)"} (payload: ${JSON.stringify(payload)})`);
  return false;
}

async function checkApi(base, key) {
  const root = base.replace(/\/+$/, "");
  let allOk = true;
  for (const path of ["/posts", "/accounts"]) {
    let res;
    try {
      res = await fetch(root + path, { headers: { Authorization: `Bearer ${key}` } });
    } catch (e) {
      console.error(`FAIL api key: GET ${path} failed: ${e.message}`);
      allOk = false;
      continue;
    }
    if (res.status === 200) {
      console.log(`ok   api key: GET ${path} -> 200`);
    } else {
      console.error(`FAIL api key: GET ${path} -> ${res.status} (expected 200)`);
      allOk = false;
    }
  }
  return allOk;
}

const opts = parseArgs(process.argv.slice(2));
if (opts.help) {
  console.log(HELP);
  process.exit(0);
}

let ok = true;
if (opts.clientId) ok = (await checkInstallLink(opts.clientId)) && ok;
if (opts.apiBase && opts.apiKey) ok = (await checkApi(opts.apiBase, opts.apiKey)) && ok;

process.exit(ok ? 0 : 1);
