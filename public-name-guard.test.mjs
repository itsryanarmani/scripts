import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const BIN = fileURLToPath(new URL('./public-name-guard.mjs', import.meta.url));
const SECRET = 'zorbwidget'; // a fake private repo name

const run = (args, { cwd, input, env = {} } = {}) =>
  spawnSync('node', [BIN, ...args], {
    cwd,
    input,
    encoding: 'utf8',
    env: { PATH: process.env.PATH, NAME_GUARD_NAMES: `${SECRET}\nabc`, ...env },
  });

function repo(files, message = 'Add files') {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'png-'));
  const g = (...a) => spawnSync('git', ['-C', dir, ...a], { encoding: 'utf8' });
  g('init', '-q', '-b', 'main');
  g('config', 'user.name', 'T'); g('config', 'user.email', 't@example.com');
  g('commit', '-q', '--allow-empty', '-m', 'root');
  for (const [f, body] of Object.entries(files)) fs.writeFileSync(path.join(dir, f), body);
  g('add', '-A'); g('commit', '-q', '-m', message);
  return dir;
}

test('no deny list is an error, never a silent pass', () => {
  const r = run(['check-text'], { input: 'anything', env: { NAME_GUARD_NAMES: '' } });
  assert.equal(r.status, 2);
});

test('clean text passes', () => {
  assert.equal(run(['check-text'], { input: 'a downstream site' }).status, 0);
});

test('a name in text fails and the report never prints the name', () => {
  const r = run(['check-text', '--label', 'issue body'], { input: `see ${SECRET.toUpperCase()} repo` });
  assert.equal(r.status, 1);
  assert.ok(!(r.stdout + r.stderr).toLowerCase().includes(SECRET));
  assert.match(r.stderr, /issue body/);
});

test('a name inside a longer word does not match, a name beside a dash or dot does', () => {
  assert.equal(run(['check-text'], { input: `x${SECRET}x` }).status, 0);
  assert.equal(run(['check-text'], { input: `${SECRET}.com` }).status, 1);
  assert.equal(run(['check-text'], { input: `a-${SECRET}-b` }).status, 1);
});

test('names shorter than four characters are ignored', () => {
  assert.equal(run(['check-text'], { input: 'abc' }).status, 0);
});

test('the allow list removes a generic word', () => {
  const r = run(['check-text'], { input: SECRET, env: { NAME_GUARD_ALLOW: SECRET } });
  assert.equal(r.status, 2);
});

test('check-tree flags the file and line, not the name', () => {
  const dir = repo({ 'a.md': 'ok\nok\n', 'b.md': `ok\nuses ${SECRET}\n` });
  const r = run(['check-tree'], { cwd: dir });
  assert.equal(r.status, 1);
  assert.match(r.stderr, /b\.md:2/);
  assert.ok(!r.stderr.includes('a.md'));
  assert.ok(!(r.stdout + r.stderr).includes(SECRET));
});

test('check-tree flags a file path that holds the name', () => {
  const dir = repo({ [`${SECRET}.md`]: 'clean' });
  assert.equal(run(['check-tree'], { cwd: dir }).status, 1);
});

test('check-range flags a commit message and an added line', () => {
  const dir = repo({ 'a.md': 'clean' }, `Move ${SECRET} data`);
  const r = run(['check-range', 'HEAD~1..HEAD'], { cwd: dir });
  assert.equal(r.status, 1);
  assert.match(r.stderr, /commit/);
  assert.ok(!(r.stdout + r.stderr).includes(SECRET));
});

test('check-range passes a clean change', () => {
  const dir = repo({ 'a.md': 'clean' });
  assert.equal(run(['check-range', 'HEAD~1..HEAD'], { cwd: dir }).status, 0);
});

test('a path that holds the name is never printed', () => {
  const dir = repo({ [`${SECRET}.md`]: `uses ${SECRET}` });
  const r = run(['check-tree'], { cwd: dir });
  assert.equal(r.status, 1);
  assert.ok(!(r.stdout + r.stderr).includes(SECRET));
});

test('a bad git ref is an error, never a silent pass', () => {
  const dir = repo({ 'a.md': 'clean' });
  assert.equal(run(['check-tree', '--ref', 'nope'], { cwd: dir }).status, 2);
  assert.equal(run(['check-range', 'nope..HEAD'], { cwd: dir }).status, 2);
});

test('redact swaps a name for a marker and leaves other text alone', async () => {
  const { buildMatcher } = await import('./public-name-guard.mjs');
  const m = buildMatcher([SECRET]);
  assert.equal(m.redact(`a ${SECRET}.com b`), 'a [redacted].com b');
  assert.equal(m.redact('plain'), 'plain');
});

test('check-range flags an added file whose path holds the name, without printing it', () => {
  const dir = repo({ [`${SECRET}.md`]: 'clean' });
  const r = run(['check-range', 'HEAD~1..HEAD'], { cwd: dir });
  assert.equal(r.status, 1);
  assert.ok(!(r.stdout + r.stderr).includes(SECRET));
});

test('a label that holds the name is not printed', () => {
  const r = run(['check-text', '--label', `${SECRET} body`], { input: SECRET });
  assert.equal(r.status, 1);
  assert.ok(!(r.stdout + r.stderr).includes(SECRET));
});

test('check-range flags a name that a later commit removed', () => {
  const dir = repo({ 'a.md': `uses ${SECRET}` });
  const g = (...a) => spawnSync('git', ['-C', dir, ...a], { encoding: 'utf8' });
  fs.writeFileSync(path.join(dir, 'a.md'), 'clean');
  g('commit', '-q', '-am', 'Remove it');
  const r = run(['check-range', 'HEAD~2..HEAD'], { cwd: dir });
  assert.equal(r.status, 1);
  assert.ok(!(r.stdout + r.stderr).includes(SECRET));
});
