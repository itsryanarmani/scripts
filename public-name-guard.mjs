#!/usr/bin/env node
// public-name-guard: keep the names of private repositories out of public ones.
//
// The deny list never lives in this file, because this repo is public. It comes
// from the environment: NAME_GUARD_NAMES (one name per line or comma separated),
// NAME_GUARD_FILE (a file of names), or NAME_GUARD_OWNER (every private repo of
// that owner, read with `gh`). NAME_GUARD_EXTRA adds brand words and domains.
// NAME_GUARD_ALLOW removes generic words that are also repo names.
//
// Output never prints a matched name. CI logs of a public repo are public, so a
// report says where a match sits and how many there are, nothing more.
//
//   public-name-guard check-text [--label L]      text on stdin
//   public-name-guard check-tree [--ref REF]      files in a git ref (default HEAD)
//   public-name-guard check-range BASE..HEAD      added lines and commit messages
//   public-name-guard sweep OWNER [--since ISO] [--redact]
//                                                 issues, PRs, comments of every own public repo
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';

const MIN_LEN = 4;
const split = (s) => (s || '').split(/[\n,]+/).map((x) => x.trim()).filter(Boolean);
const gh = (args) => execFileSync('gh', args, { encoding: 'utf8', maxBuffer: 1 << 28 });

export function loadNames(env = process.env) {
  let names = [...split(env.NAME_GUARD_NAMES), ...split(env.NAME_GUARD_EXTRA)];
  if (env.NAME_GUARD_FILE) names.push(...split(fs.readFileSync(env.NAME_GUARD_FILE, 'utf8')));
  if (env.NAME_GUARD_OWNER) {
    const out = gh(['repo', 'list', env.NAME_GUARD_OWNER, '--visibility', 'private', '--limit', '1000', '--json', 'name', '-q', '.[].name']);
    names.push(...split(out));
  }
  const allow = new Set(split(env.NAME_GUARD_ALLOW).map((x) => x.toLowerCase()));
  return [...new Set(names)].filter((n) => n.length >= MIN_LEN && !allow.has(n.toLowerCase()));
}

// A name matches when no letter or digit touches either side, so "name.com"
// and "name-docs" match and "xnamex" does not.
export function buildMatcher(names) {
  if (!names.length) return Object.assign(() => 0, { redact: (t) => t });
  const alt = names.sort((a, b) => b.length - a.length).map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const rx = new RegExp(`(?<![A-Za-z0-9])(?:${alt})(?![A-Za-z0-9])`, 'gi');
  return Object.assign((text) => (text.match(rx) || []).length, { redact: (t) => (t || '').replace(rx, '[redacted]') });
}

const lineHits = (match, text) =>
  text.split('\n').flatMap((l, i) => (match(l) ? [i + 1] : []));

// A failed git call must stop the run: an empty result would read as "clean".
const git = (args) => {
  const r = spawnSync('git', args, { encoding: 'utf8', maxBuffer: 1 << 28 });
  if (r.status !== 0) throw new Error(`git ${args[0]} failed`);
  return r.stdout;
};

// A path that holds a name is never printed, because the log is public.
const showPath = (match, f) => (match(f) ? '<path redacted>' : f);

function checkTree(match, ref) {
  const files = git(['ls-tree', '-r', '--name-only', ref]).split('\n').filter(Boolean);
  const bad = [];
  for (const f of files) {
    if (match(f)) bad.push('<path redacted> (path)');
    const blob = git(['show', `${ref}:${f}`]);
    if (blob.includes('\0')) continue;
    const lines = lineHits(match, blob);
    if (lines.length) bad.push(`${showPath(match, f)}:${lines.slice(0, 5).join(',')}`);
  }
  return bad;
}

function checkRange(match, range) {
  const bad = [];
  const log = git(['log', '--format=%H%x00%an%x00%ae%x00%B%x01', range]).split('\x01').filter((x) => x.trim());
  for (const entry of log) {
    const [sha, an, ae, body] = entry.trim().split('\0');
    if (match(`${an} ${ae}\n${body}`)) bad.push(`commit ${sha.slice(0, 7)} (message or author)`);
  }
  for (const f of git(['log', '--name-only', '--format=', range]).split('\n').filter(Boolean)) {
    if (match(f)) bad.push('<path redacted> (path)');
  }
  // Every commit's patch, not the net diff: a name added then removed stays in history.
  const diff = git(['log', '-p', '--unified=0', '--format=', range]);
  let file = '';
  for (const l of diff.split('\n')) {
    if (l.startsWith('+++ b/')) file = l.slice(6);
    else if (l.startsWith('+') && match(l)) bad.push(`${showPath(match, file)} (added line)`);
  }
  return bad;
}

// An API failure must stop the run too: a rate limit would read as "clean".
function sweep(match, owner, { since, redact }) {
  const bad = [];
  let removed = 0;
  const repos = split(gh(['repo', 'list', owner, '--visibility', 'public', '--limit', '1000', '--source', '--json', 'name', '-q', '.[].name']));
  const q = since ? `&since=${encodeURIComponent(since)}` : '';
  const patch = (path, fields) => gh(['api', '-X', 'PATCH', path, ...Object.entries(fields).flatMap(([k, v]) => ['-f', `${k}=${v}`])]);
  for (const repo of repos) {
    const base = `repos/${owner}/${repo}`;
    const rn = showPath(match, repo);
    const api = (p) => gh(['api', '--paginate', `${base}/${p}`, '-q', '.[]|@json']).split('\n').filter(Boolean).map((x) => JSON.parse(x));
    // A removed match is resolved. Only a match still public makes the run fail.
    const drop = (path) => { if (!redact) return false; try { gh(['api', '-X', 'DELETE', path]); return true; } catch { return false; } };
    for (const i of api(`issues?state=all&per_page=100${q}`)) {
      if (!match(`${i.title}\n${i.body || ''}`)) continue;
      let fixed = false;
      if (redact) {
        try {
          if (i.pull_request) patch(`${base}/pulls/${i.number}`, { title: match.redact(i.title), body: match.redact(i.body) });
          else gh(['api', 'graphql', '-f', `query=mutation{deleteIssue(input:{issueId:"${i.node_id}"}){clientMutationId}}`]);
          fixed = true;
        } catch { /* needs admin */ }
      }
      if (fixed) removed++; else bad.push(`${rn}#${i.number} (${i.pull_request ? 'pull request' : 'issue'})`);
    }
    for (const c of api(`issues/comments?per_page=100${q}`)) {
      if (match(c.body || '')) { if (drop(`${base}/issues/comments/${c.id}`)) removed++; else bad.push(`${rn} comment ${c.id}`); }
    }
    for (const c of api(`pulls/comments?per_page=100${q}`)) {
      if (match(c.body || '')) { if (drop(`${base}/pulls/comments/${c.id}`)) removed++; else bad.push(`${rn} review comment ${c.id}`); }
    }
    // A submitted review cannot be deleted. Report it so a person can act.
    for (const i of api(`issues?state=all&per_page=100${q}`).filter((x) => x.pull_request)) {
      for (const r of api(`pulls/${i.number}/reviews?per_page=100`)) {
        if (match(r.body || '')) bad.push(`${rn}#${i.number} review ${r.id}`);
      }
    }
  }
  if (removed) console.log(`public-name-guard: removed ${removed} place(s) that named a private repository`);
  return bad;
}

function main(argv) {
  const [cmd, ...rest] = argv;
  const flag = (n) => { const i = rest.indexOf(n); return i < 0 ? undefined : rest[i + 1]; };
  const names = loadNames();
  if (!names.length) { console.error('public-name-guard: no deny list configured'); return 2; }
  const match = buildMatcher(names);
  let bad = [];
  try {
  if (cmd === 'check-text') {
    const label = flag('--label') || 'text';
    bad = match(fs.readFileSync(0, 'utf8')) ? [match(label) ? '<label redacted>' : label] : [];
  } else if (cmd === 'check-tree') bad = checkTree(match, flag('--ref') || 'HEAD');
  else if (cmd === 'check-range') bad = checkRange(match, rest[0]);
  else if (cmd === 'sweep') bad = sweep(match, rest[0], { since: flag('--since'), redact: rest.includes('--redact') });
  else { console.error('usage: public-name-guard check-text|check-tree|check-range|sweep'); return 2; }
  } catch (e) {
    console.error(`public-name-guard: could not finish the check (${String(e.message).split('\n')[0].slice(0, 60)})`);
    return 2;
  }
  if (bad.length) {
    console.error(`public-name-guard: ${bad.length} place(s) name a private repository`);
    for (const b of bad.slice(0, 50)) console.error(`  ${b}`);
    return 1;
  }
  console.log('public-name-guard: clean');
  return 0;
}

if (import.meta.url === `file://${process.argv[1]}`) process.exit(main(process.argv.slice(2)));
