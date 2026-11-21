import { test } from 'node:test';
import assert from 'node:assert/strict';
import gate, { keyMatches, lookupPersona } from './src/index.js';

const env = (over = {}) => {
  const e = {
    KEYS_JSON: JSON.stringify({ 'k-saina': { binding: 'EMAIL_SAINA', from: 'saina@private-repo-ba8a.com' } }),
    ...over,
  };
  e.EMAIL_SAINA = { send: async (m) => { e._sent = m; } };
  return e;
};

const req = (body, auth) => new Request('https://x/send', {
  method: 'POST', headers: { Authorization: `Bearer ${auth}`, 'content-type': 'application/json' },
  body: JSON.stringify(body ?? { to: 'a@b.c', subject: 's', text: 't' }),
});

test('keyMatches constant-time compare', async () => {
  assert.equal(await keyMatches('a', 'a'), true);
  assert.equal(await keyMatches('a', 'b'), false);
});

test('lookupPersona finds the right persona', async () => {
  const p = await lookupPersona('k-saina', env());
  assert.equal(p.from, 'saina@private-repo-ba8a.com');
  assert.equal(await lookupPersona('nope', env()), null);
});

test('rejects missing bearer', async () => {
  const r = await gate.fetch(new Request('https://x/send', { method: 'POST', body: '{}' }), env());
  assert.equal(r.status, 401);
});

test('rejects bad key and bad body', async () => {
  assert.equal((await gate.fetch(req(null, 'wrong'), env())).status, 401);
  const r = await gate.fetch(req({ to: 'a@b.c' }, 'k-saina'), env());
  assert.equal(r.status, 400);
});

test('sends via the persona binding as its own address', async () => {
  const e = env();
  const r = await gate.fetch(req(null, 'k-saina'), e);
  assert.equal(r.status, 200);
  assert.equal(e._sent.from.email, 'saina@private-repo-ba8a.com');
  assert.equal(e._sent.to, 'a@b.c');
});

test('404 on other paths, health ok', async () => {
  const e = env();
  assert.equal((await gate.fetch(new Request('https://x/nope'), e)).status, 404);
  assert.equal((await gate.fetch(new Request('https://x/health'), e)).status, 200);
});
