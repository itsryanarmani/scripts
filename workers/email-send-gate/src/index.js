// email-send-gate: per-key outbound send API on Cloudflare Email Sending.
//
// Each caller holds an opaque key. KEYS_JSON maps key -> {binding, from, name?}.
// The binding is a `send_email` binding pinned with `allowed_sender_addresses`,
// so even a correct key can only send as its own address.

const encoder = new TextEncoder();

// Constant-time key comparison. Both keys are hashed to fixed-length digests
// first, so the compare leaks neither length nor early-exit position.
async function keyMatches(provided, stored) {
  const [ha, hb] = await Promise.all([
    crypto.subtle.digest('SHA-256', encoder.encode(provided)),
    crypto.subtle.digest('SHA-256', encoder.encode(stored)),
  ]);
  const a = new Uint8Array(ha);
  const b = new Uint8Array(hb);
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

function json(body, status = 200) {
  return Response.json(body, { status });
}

function loadKeys(env) {
  try {
    const parsed = JSON.parse(env.KEYS_JSON || '{}');
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

// Compares the bearer token against every stored key without early exit, so
// timing does not reveal which position (if any) matched.
async function lookupPersona(token, env) {
  let persona = null;
  for (const [stored, value] of Object.entries(loadKeys(env))) {
    if (await keyMatches(token, stored)) persona = value;
  }
  return persona;
}

async function handleSend(request, env) {
  const auth = request.headers.get('Authorization') || '';
  const match = auth.match(/^Bearer\s+(.+)$/);
  if (!match) return json({ error: 'missing bearer token' }, 401);

  const persona = await lookupPersona(match[1].trim(), env);
  if (!persona || !persona.binding || !persona.from) {
    return json({ error: 'unauthorized' }, 401);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'invalid JSON body' }, 400);
  }
  const { to, subject, text, html, reply_to } = body || {};
  if (!to || !subject || !text) {
    return json({ error: 'required fields: to, subject, text' }, 400);
  }

  const binding = env[persona.binding];
  if (!binding || typeof binding.send !== 'function') {
    return json({ error: `send binding ${persona.binding} is not configured` }, 500);
  }

  const message = { to, from: { email: persona.from, name: persona.name }, subject, text };
  if (html) message.html = html;
  if (reply_to) message.replyTo = reply_to;

  try {
    await binding.send(message);
    return json({ ok: true });
  } catch (err) {
    return json({ ok: false, error: String((err && err.message) || err) }, 502);
  }
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname === '/health' && request.method === 'GET') {
      return json({ ok: true });
    }
    if (pathname === '/send' && request.method === 'POST') {
      return handleSend(request, env);
    }
    return json({ error: 'not found' }, 404);
  },
};

export { keyMatches, lookupPersona, handleSend };
