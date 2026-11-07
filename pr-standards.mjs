import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFile, execFileSync, spawnSync } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

import { ASSISTED_BY_VALID_RE, assistedByLinesFromBody, isValidAssistedByLine } from './assisted-by.mjs';

const execFileAsync = promisify(execFile);
const PREFIX_REGISTRY_PATH = fileURLToPath(new URL('./repo-prefixes.json', import.meta.url));
const TEMPLATES_DIR = fileURLToPath(new URL('./pr-standards-templates/', import.meta.url));
const AGENTS_BLOCK_START = '<!-- pr-standards:start -->';
const AGENTS_BLOCK_END = '<!-- pr-standards:end -->';

// Banned AI attribution names in Co-authored-by trailers. These are matched as
// whole words in the author name field so "Pia" does not match pi and "Gupta"
// does not match GPT. vibecodereview is explicitly exempt.
export const DEFAULT_BANNED_COMMIT_TRAILERS = [
  'Claude',
  'Codex',
  'Gemini',
  'Kimi',
  'Muse',
  'pi',
  'ChatGPT',
  'GPT',
  'Copilot',
  'Cursor',
  'Devin',
  'Anthropic',
  'OpenAI',
];

export const DEFAULT_EXCLUDE_GLOBS = [
  // Anchored at any depth, not just the repo root. A monorepo keeps a lockfile
  // per workspace, and an unanchored pattern counted apps/*/package-lock.json
  // against the 500-line cap -- so a dependency bump failed the size check on
  // thousands of generated lines nobody reads.
  '**/*.lock',
  '**/package-lock.json',
  '**/bun.lockb',
  '**/pnpm-lock.yaml',
  '**/yarn.lock',
  '**/Cargo.lock',
  'dist/**',
  'build/**',
  '.next/**',
  'out/**',
  'vendor/**',
  '**/generated/**',
  '**/__snapshots__/**',
  '**/*.snap',
  '**/*.generated.*',
  '**/migrations/**',
  '**/*.min.js',
  '**/*.map',
  // Run output, not authored code. Two repos had committed scraper logs, so the
  // PR that untracked them counted 93,162 deleted lines against the cap and the
  // only way to pass was to leave the logs in the tree.
  '**/*.log',
  // Same deadlock, different artifact: untracking a TypeScript incremental
  // build cache counted its whole body against the cap. itsryanarmani/usegeoaeo#71
  // passed only because a tsbuildinfo is minified onto one line; a
  // pretty-printed one would have had no path to green.
  '**/*.tsbuildinfo',
  '**/*.{svg,png,jpg,jpeg,gif,webp,ico,woff,woff2,ttf,otf,mp4,pdf,zip}',
];

export const DEFAULT_CONFIG = {
  prefix: null,
  requireIssue: true,
  allowChoreEscape: false,
  maxLines: 500,
  maxFiles: 40,
  maxTopLevelDirs: 3,
  minBodyChars: 120,
  maxBaseCommitsBehind: 10,
  bannedCommitTrailers: DEFAULT_BANNED_COMMIT_TRAILERS,
  exemptBranches: ['main', 'release', 'refactor', 'gh-pages'],
  excludeGlobs: DEFAULT_EXCLUDE_GLOBS,
  requireProof: true,
  // Warn first, then ratchet. A fleet where no repo runs its tests in CI would
  // go red everywhere on the day this became a failure, and a standard that
  // does that on its first day gets switched off.
  requireAttributableProof: false,
  uiGlobs: [
    '**/*.tsx', '**/*.jsx', '**/*.vue', '**/*.svelte', '**/*.css', '**/*.scss',
    '**/*.html', '**/components/**', '**/app/**/page.*', '**/pages/**',
  ],
  uiExcludeGlobs: [
    '**/*.test.*', '**/*.spec.*', '**/__tests__/**', '**/*.stories.*',
  ],
};

const ALWAYS_EXEMPT_BRANCHES = ['main', 'release', 'refactor', 'gh-pages'];
const EXEMPT_BRANCH_PREFIXES = ['release/', 'dependabot/', 'renovate/'];
const REJECTED_TITLE_OPENERS = [
  'Added',
  'Fixed',
  'Updated',
  'Removed',
  'Changed',
  'Refactored',
  'Implemented',
];
const CONVENTIONAL_TYPES = 'build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test';
const EMOJI_RE = /[\p{Extended_Pictographic}\p{Regional_Indicator}\uFE0F\u200D]/u;

// Escape a literal string so it is safe in a new RegExp. Used for matching
// banned trailer names as whole words.
function escapeRegex(string) {
  return String(string).replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export class ConfigurationError extends Error {
  constructor(message) {
    super(message);
    this.name = 'ConfigurationError';
  }
}

export class ApiError extends Error {
  constructor(message, status = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function fail(check, got, expected, fix) {
  return { check, got, expected, fix };
}

export function derivePrefix(repoName) {
  const rawName = String(repoName).split('/').filter(Boolean).pop() || '';
  // Strip anything that is not a letter before deriving. A prefix must be 2 to
  // 4 lowercase letters, so a name like `3d-tools` derived `3t` and then failed
  // validation on every single invocation, with a message about the config
  // rather than about the name that caused it.
  const cleanName = rawName.replace(/[^A-Za-z-_\s]/g, '');
  const parts = cleanName.split(/[-_\s]+/).filter(Boolean);
  const prefix = parts.length > 1
    ? parts.map((part) => part[0]).join('')
    : cleanName.slice(0, 3);
  // A prefix must be 2 to 4 letters. A repo named `x`, one made entirely of
  // digits, or one that is all separators cannot supply that. Failing later with
  // "prefix must be 2-4 lowercase letters" would point at the config rather than
  // at the real cause, which is the name, so give a usable answer and let the
  // repo override it. Keep only letters here: `a-` and `---` are the right
  // length by accident and would otherwise sail past both fallbacks and be
  // rejected downstream by exactly the message this is meant to avoid.
  const letters = prefix.toLowerCase().replace(/[^a-z]/g, '').slice(0, 4);
  if (letters.length === 0) return 'zz';
  const derived = letters.length === 1 ? `${letters}${letters}` : letters;
  return isValidPrefix(derived) ? derived : 'zz';
}

function isValidPrefix(prefix) {
  return typeof prefix === 'string' && /^[a-z]{2,4}$/.test(prefix);
}

function registryPrefix(repoName) {
  try {
    const registry = JSON.parse(fs.readFileSync(PREFIX_REGISTRY_PATH, 'utf8'));
    if (!registry || Array.isArray(registry) || typeof registry !== 'object') return null;
    const prefix = registry[repoName];
    return isValidPrefix(prefix) ? prefix : null;
  } catch {
    // A broken registry must not prevent a new repo from using derivation.
    return null;
  }
}

function resolveFallbackPrefix(repoName) {
  const registered = registryPrefix(repoName);
  return registered
    ? { prefix: registered, source: 'registry' }
    : { prefix: derivePrefix(repoName), source: 'derived' };
}

function isExemptBranch(name, config) {
  return ALWAYS_EXEMPT_BRANCHES.includes(name)
    || (config.exemptBranches || []).includes(name)
    || EXEMPT_BRANCH_PREFIXES.some((prefix) => name.startsWith(prefix));
}

export function validateBranchName(name, config = DEFAULT_CONFIG) {
  const branch = String(name || '');
  if (isExemptBranch(branch, config)) {
    return { ok: true, exempt: true, failures: [], issueNumber: null };
  }

  if (config.allowChoreEscape && /^chore\/[a-z0-9]+(?:-[a-z0-9]+)*$/.test(branch)) {
    const slug = branch.slice('chore/'.length);
    if (slug.length >= 3 && slug.length <= 48) {
      return { ok: true, choreEscape: true, failures: [], issueNumber: null };
    }
  }

  // [1-9][0-9]* rather than [0-9]+: there is no issue #0, and a leading zero
  // makes cr-007-x and cr-7-x two branch names for one issue.
  const pattern = new RegExp(`^${config.prefix}-([1-9][0-9]*)-([a-z0-9]+(?:-[a-z0-9]+)*)$`);
  const match = pattern.exec(branch);
  if (!match) {
    const expected = `${config.prefix}-<issue>-<slug>`;
    return {
      ok: false,
      failures: [fail(
        'branch name',
        branch || '(empty)',
        `${expected}   e.g. ${config.prefix}-142-fix-onboarding-drop-off`,
        `git branch -m ${config.prefix}-<issue>-<slug>`,
      )],
      issueNumber: null,
    };
  }

  const slug = match[2];
  if (slug.length < 3 || slug.length > 48) {
    return {
      ok: false,
      failures: [fail(
        'branch slug',
        slug,
        '3-48 lowercase letters, numbers, and single hyphens',
        `git branch -m ${config.prefix}-${match[1]}-describe-the-change`,
      )],
      issueNumber: Number(match[1]),
    };
  }

  return { ok: true, failures: [], issueNumber: Number(match[1]) };
}

function subjectFromTitle(title) {
  const match = /^\[([A-Za-z]{2,4})-([1-9][0-9]*)\]\s+(.+)$/.exec(String(title || ''));
  return match ? { tagPrefix: match[1], tagIssue: Number(match[2]), subject: match[3] } : null;
}

// A PR title is whatever its author typed, and this output is read by agents
// that act on it and humans who paste it into a shell. Interpolating the title
// into a double-quoted command made `$(...)` and backticks live. Single-quote
// it, escaping embedded single quotes, so the text stays inert.
function shellFix(prefix, issueNumber, subject) {
  const safe = String(subject).replace(/'/g, "'\\''");
  return `gh pr edit --title '[${prefix.toUpperCase()}-${issueNumber}] ${safe}'`;
}

export function validateTitle(title, prefix, issueNumber) {
  let subject;
  const failures = [];

  if (issueNumber === null) {
    subject = String(title || '');
  } else {
    const parsed = subjectFromTitle(title);
    if (!parsed) {
      return {
        ok: false,
        failures: [fail(
          'PR title format',
          String(title || '(empty)'),
          `[${prefix.toUpperCase()}-${issueNumber}] Imperative subject`,
          `gh pr edit --title "[${prefix.toUpperCase()}-${issueNumber}] Fix the described issue"`,
        )],
      };
    }

    if (parsed.tagPrefix !== prefix.toUpperCase()) {
      failures.push(fail(
        'PR title tag',
        `[${parsed.tagPrefix}-${parsed.tagIssue}]`,
        `[${prefix.toUpperCase()}-${issueNumber}]`,
        shellFix(prefix, issueNumber, parsed.subject),
      ));
    }
    if (parsed.tagIssue !== issueNumber) {
      failures.push(fail(
        'PR title issue',
        String(parsed.tagIssue),
        String(issueNumber),
        shellFix(prefix, issueNumber, parsed.subject),
      ));
    }
    subject = parsed.subject;
  }

  if (subject.length < 10 || subject.length > 50) {
    const editCommand = issueNumber === null
      ? `gh pr edit --title "Describe the change"`
      : `gh pr edit --title "[${prefix.toUpperCase()}-${issueNumber}] Describe the change"`;
    failures.push(fail(
      'PR title subject length',
      `${subject.length} characters`,
      '10-50 characters',
      editCommand,
    ));
  }
  if (!/^\p{Lu}/u.test(subject)) {
    const editCommand = issueNumber === null
      ? `gh pr edit --title "Fix the described issue"`
      : `gh pr edit --title "[${prefix.toUpperCase()}-${issueNumber}] Fix the described issue"`;
    failures.push(fail(
      'PR title capitalization',
      subject,
      'a subject that starts with a capital letter',
      editCommand,
    ));
  }
  if (/\.$/.test(subject)) {
    const editCommand = issueNumber === null
      ? `gh pr edit --title "Fix the described issue"`
      : `gh pr edit --title "[${prefix.toUpperCase()}-${issueNumber}] Fix the described issue"`;
    failures.push(fail(
      'PR title punctuation',
      subject,
      'no trailing period',
      editCommand,
    ));
  }
  if (REJECTED_TITLE_OPENERS.some((word) => new RegExp(`^${word}\\b`, 'i').test(subject))
    || /^[A-Za-z][A-Za-z'-]*ing\b/i.test(subject)) {
    const editCommand = issueNumber === null
      ? `gh pr edit --title "Fix the described issue"`
      : `gh pr edit --title "[${prefix.toUpperCase()}-${issueNumber}] Fix the described issue"`;
    failures.push(fail(
      'PR title mood',
      subject,
      'an imperative subject, not a past-tense or -ing opener',
      editCommand,
    ));
  }
  if (EMOJI_RE.test(String(title))) {
    const editCommand = issueNumber === null
      ? `gh pr edit --title "Fix the described issue"`
      : `gh pr edit --title "[${prefix.toUpperCase()}-${issueNumber}] Fix the described issue"`;
    failures.push(fail(
      'PR title emoji',
      String(title),
      'no emoji',
      editCommand,
    ));
  }
  if (new RegExp(`^(?:${CONVENTIONAL_TYPES})(?:\\([^)]*\\))?!?:\\s+`, 'i').test(subject)) {
    const editCommand = issueNumber === null
      ? `gh pr edit --title "Fix the described issue"`
      : `gh pr edit --title "[${prefix.toUpperCase()}-${issueNumber}] Fix the described issue"`;
    failures.push(fail(
      'PR title prefix',
      subject,
      'no conventional-commit prefix',
      editCommand,
    ));
  }

  return { ok: failures.length === 0, failures };
}

// Every form GitHub actually treats as a closing reference. Three things are
// easy to miss and each one lets a second concern in unseen: all nine keywords
// rather than Closes and Fixes, an optional colon after the keyword
// (`Closes: #10`), and the cross-repo `owner/name#100` form. A reference into
// another repo still counts toward the one-reference rule, because it is still
// a second thing this pull request closes, but it can never satisfy the branch
// issue, so it is returned with its repo attached rather than as a bare number.
export function countClosingReferences(body) {
  const references = [];
  const pattern = /\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*(?:([\w.-]+\/[\w.-]+))?#([0-9]+)\b/gi;
  // Quoted text is not a claim -- the same rule the proof checks and the marker
  // scan already apply. A body that explains a reference it was corrected away
  // from ("this originally claimed `Closes #84`") has to name it to explain it,
  // and counting that mention failed the body for having three references when
  // it had one. Fenced blocks go first so a ``` example cannot leak either.
  const visibleBody = String(body || '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/^ {0,3}(`{3,}|~{3,})[\s\S]*?^ {0,3}\1[ \t]*$/gm, '')
    .replace(/`[^`\n]*`/g, '');
  for (const match of visibleBody.matchAll(pattern)) {
    references.push({ repo: match[1] || null, number: Number(match[2]) });
  }
  return references;
}

// Same shape as Assisted-by, on purpose: one line, two tokens, no path.
// The reviewer is a second model. Matching an Assisted-by line means the
// author reviewed their own diff, which is the thing this check exists to
// catch.
const REVIEWED_BY_VALID_RE = /^Reviewed-by:\s*([^\s:,/`]+):([^\s:,`]+)\s*$/i;

export function authorLabels(body) {
  const visible = String(body || '').replace(/<!--[\s\S]*?-->/g, '');
  return assistedByLinesFromBody(visible).flatMap((line) => {
    const match = ASSISTED_BY_VALID_RE.exec(line.trim());
    return match ? [`${match[1]}:${match[2]}`] : [];
  });
}

export function isReviewCheck(item) {
  return item.check === 'Reviewed-by line'
    || item.check === 'Review verdict'
    || (item.check === 'PR body section' && String(item.got).includes('## Review'));
}

// `text` is either the ## Review section or the pull request conversation
// (issue comments, review bodies, and inline comments joined together).
// HTML comments do not count: an unedited template must not pass.
export function reviewProofFailures(text, authors = []) {
  const source = String(text || '').replace(/<!--[\s\S]*?-->/g, '');
  const failures = [];
  const lines = source.split('\n').filter((line) => /^\s*reviewed-by:/i.test(line));
  const good = lines.find((line) => REVIEWED_BY_VALID_RE.test(line.trim()));
  if (!good) {
    failures.push(fail(
      'Reviewed-by line',
      lines[0] ? `not in the accepted form: ${lines[0].trim()}` : 'missing',
      'Reviewed-by: <agent>:<model>',
      'Run a second model on the diff and add Reviewed-by: <agent>:<model> under ## Review, or in a pull request comment.',
    ));
  } else {
    const match = REVIEWED_BY_VALID_RE.exec(good.trim());
    const label = `${match[1]}:${match[2]}`;
    const model = match[2].toLowerCase();
    // The agent name is the seat. The model is the reviewer. Renaming the
    // seat and keeping the model that wrote the diff is the same review.
    const author = authors.find((item) => item.split(':').pop().toLowerCase() === model);
    if (author) {
      failures.push(fail(
        'Reviewed-by line',
        label,
        'a model that did not write the change',
        `${label} uses the same model as ${author}. Run a different model and record that one.`,
      ));
    }
  }
  const verdict = source.split('\n').find((line) => /^\s*verdict\s*:/i.test(line));
  const verdictValue = verdict ? verdict.replace(/^\s*verdict\s*:/i, '').trim() : '';
  if (!verdictValue || /^(?:n\/a|todo|tbd)\b/i.test(verdictValue)) {
    failures.push(fail(
      'Review verdict',
      verdict ? verdict.trim() : 'missing',
      'Verdict: 0 major, or Verdict: followed by the findings',
      'Add a Verdict line under ## Review, or in a pull request comment. Example: Verdict: 0 major',
    ));
  }
  return failures;
}

// A missing or weak ## Review is fine when the same proof is in a comment.
// The body failures stay when the conversation does not carry the proof, so
// the message still tells the author where to put it.
export function unresolvedReviewFailures(bodyFailures, comments, authors = []) {
  const reviewFailures = bodyFailures.filter(isReviewCheck);
  if (reviewFailures.length === 0) return [];
  // One comment has to carry both lines. Joining the thread would let an
  // old `Verdict: TODO` hide a later review that is actually complete.
  const list = Array.isArray(comments) ? comments : [comments];
  if (list.some((text) => reviewProofFailures(text, authors).length === 0)) return [];
  return reviewFailures;
}

function sectionBody(body, heading) {
  const source = String(body || '');
  const headingPattern = new RegExp(`^##\\s+${heading}\\s*$`, 'im');
  const match = headingPattern.exec(source);
  if (!match) return null;
  const start = match.index + match[0].length;
  const rest = source.slice(start);
  const nextHeading = /^##\s+.+$/im.exec(rest);
  return (nextHeading ? rest.slice(0, nextHeading.index) : rest).trim();
}

function sentenceCount(text) {
  return String(text).split(/[.!?]+(?=\s|$)/).map((part) => part.trim()).filter(Boolean).length;
}

// The documented escape hatch, in the forms the checker accepts. It lives in
// a constant because two rules read it: the body check below must not mistake it
// for a refusal to answer, and the proof check must honour it. Two copies of
// this pattern would eventually disagree, and the disagreement would look like
// a lazy body rather than a drifted regex.
//
// Proof: n/a still requires a reason after the dash — that is the hatch's
// burden. Operator: n/a may be bare, because CLAUDE.md specifies that form
// for a mechanical PR with no user-visible surface. Making the reason optional
// for both labels would let a bare `Proof: n/a` match, turn hatch[1] into
// undefined, and hide the n/a from the refusal guard.
//
// Two capture groups: [1] is the Proof reason, [2] is the optional Operator
// reason. Call sites must not assume [1] is always a string.
const PROOF_NA_LINE = /^\s*(?:Proof:\s*n\/a\s*[—–-]\s*(\S.*)|Operator:\s*n\/a(?:\s*[—–-]\s*(\S.*))?)\s*$/i;

// Names, not shape. Two pull requests already failed because a runner they
// actually used was missing (`python3` in #145, `bunx` in #135), and #113 is
// the third. Shape — "a line that looks like argv" — would stop that treadmill,
// but an existing test requires `bunxx frobnicate -> 3 passed` to fail: that
// string is the word-boundary check that `bun` not match inside a longer token.
// A shape check has no allowlist, so it cannot tell `bunxx` from `bash`, and
// any lowercase first word plus a success word would then count as evidence.
// The next missing name is cheaper than emptying the rule. Add the runner
// the evidence actually used.
//
// The word boundary goes AFTER the command name, not before it. Without it
// `bun` matched inside `Bundle`, so "Bundle was verified" satisfied both the
// command and the result check while naming no command at all.
// Order in the alternation does NOT matter, despite what an earlier comment
// here claimed: a failed `\b` makes the engine backtrack and try the other
// branches, so `bun|bunx` matches "bunx" exactly as `bunx|bun` does. What
// fixed the `bunx` failure was adding the name, not moving it. The longer
// names are still written first, because that reads as intent.
//
// `python3` and `python` are here because the checker itself shells to
// `python3` and three of its test suites are `python3` scripts, yet the list
// named neither: a pull request whose evidence was a real `python3` run
// failed the rule, and the author met the regex by prefixing a pointless
// `node -e` to the command that had already run.
//
// `bash` and `sh` are here because a repo whose suite is a shell script
// cannot state that evidence at all — live as PR #205, whose body recorded
// `bash worker-run.test.sh` and failed this check. `docker`, `curl`, and
// `terraform` are the other runners in that same table that the list skipped.
// A list marker and inline-code/prompt marker are separate Markdown layers.
// Accept both in order so `- ` plus a backtick does not hide a real command.
const PROOF_COMMAND_RE = /^(?:[-*+]\s+)?(?:[$>`]\s*)?(?:bunx|bun|npm|pnpm|yarn|node|deno|cargo|go|pytest|python3|python|make|git|gh|npx|bash|sh|docker|curl|terraform|box|\.\/)\b[^\n]*/i;

// Real tools do not all print "passed". oxlint prints "Found 0 warnings",
// tsc prints "0 errors", docker prints "Successfully built", terraform
// prints "No changes.", and this repo's install-pr-hooks prints
// "installed=1 failed=0". Those are passing results. Counting any number of
// warnings or errors as success would let a red run through, so the counts
// that mean clean are zero, not `\d+`. "Successfully" needs the adverb
// form so the word boundary sits after the `y`, not inside the word.
const PROOF_RESULT_RE = /(?:->|\b(?:pass(?:ed)?|success(?:ful(?:ly)?)?|clean|green|ok|verified|complete|no issues|no changes|exit(?:ed|s)?(?:\s+with)?(?:\s+(?:code|status))?(?:\s*:\s*|\s+)0+)\b|\d+\s+(?:tests?|checks?)\s+(?:pass|passed|successful)|\b0\s+(?:warnings?|errors?)\b|\bfailed\s*=\s*0\b)/i;

// oxlint's actual output is "Found N warnings and M errors", both counts in
// one line. `\b0\s+(?:warnings?|errors?)\b` alone would let a nonzero
// warning count through on the back of a clean "0 errors" in the same
// string — "Found 7 warnings and 0 errors" is not a passing result even
// though it contains a zero count. A nonzero warnings/errors count anywhere
// in the text means the run was not clean, full stop.
//
// Same masking, different word: "12 passed, 2 failed" matches `pass(?:ed)?`
// and reads as a passing result, with the "2 failed" right next to it doing
// nothing to stop it. `failed=2` is the same failure wearing install-pr-hooks'
// key=value spelling. Either spelling of a nonzero failure count means the
// run was not clean, same as a nonzero warning or error count.
// The count must not be the value half of a key=value pair. `installed=1
// failed=0` is a clean run of install-pr-hooks, and reading "1 failed" across
// the `=` boundary vetoed it: the 1 counts installs, the failures are 0. The
// lookbehind requires the digits to start a token, so "2 failed" in "12
// passed, 2 failed" still vetoes and `key=1 failed=0` does not.
//
// A count is not always adjacent to the word it counts. go test prints
// "1 test failed", not "1 failed" -- the noun sits between the digit and
// the word this rule looks for, so the count and "failed" need an optional
// noun between them. And a count is not always written without a leading
// zero: "02 failed" still means two failures. `0*` before the required
// nonzero digit absorbs the leading zero without letting an all-zero count
// like "00" or "0" through, since `[1-9]` still demands one nonzero digit.
// Match common exit code/status wording in both zero and nonzero results.
// An arrow records a result but cannot make a nonzero exit successful.
const PROOF_NONZERO_RE = /\bexit(?:ed|s)?(?:\s+with)?(?:\s+(?:code|status))?(?:\s*:\s*|\s+)0*[1-9]\d*\b|(?<![=\d])0*[1-9]\d*\s+(?:(?:tests?|checks?|cases?)\s+)?(?:warnings?|errors?|failed)\b|\bfailed\s*=\s*0*[1-9]\d*\b/i;

function proofCommand(text) {
  const lines = String(text).split('\n').map((line) => line.trim()).filter(Boolean);
  return lines.some((line) => PROOF_COMMAND_RE.test(line));
}

// An index-only change has no test-runner vocabulary. The proof is a
// before/after `git ls-files | grep -c` pair, or a `(none tracked)` /
// `(none)` guard. Four PRs untracked build artifacts and then padded the
// section with "clean" because those lines did not count as a result
// (usegeoaeo#71, private-repo-5073#1205, example#164, private-repo-4a88#225).
// Output lines are results; the command that printed them is not.
// `echo '(none tracked)'` on a command line is not evidence.
//
// Both the count and the guard only mean something as the output of a
// `git ls-files` invocation, and only as the line immediately after it —
// not just anywhere later in the section. Without that adjacency, a prose
// note between the command and an unrelated pair of digit lines (e.g. a
// benchmark count printed further down) would still read as a delta.
// And a delta is only real when the two counts differ: two identical
// `git ls-files | grep -c ''` runs prove nothing changed, so counting
// them as "before/after" evidence would let a no-op pass.
//
// The two counts must also come from the *same* probe. Pairing any two
// ls-files-flavored commands that happen to produce different numbers
// (`git ls-files | grep -c '.ts'` -> 300, then a separate `grep -c '.md'`
// -> 42) would read as a before/after delta even though nothing about the
// index changed between them -- those are two unrelated snapshots, not a
// before and an after of the same measurement. Counts are grouped by their
// normalized command text, and only a differing pair within the same group
// counts as a delta.
const PROOF_NONE_GUARD_RE = /^\(\s*none(?:\s+tracked)?\s*\)$/i;
const PROOF_COUNT_LINE_RE = /^\d+$/;
const LS_FILES_COMMAND_RE = /\bgit\s+ls-files\b/i;

function normalizeLsFilesCommand(line) {
  return line.replace(/^[$>`]\s*/, '').replace(/\s+/g, ' ').trim();
}

function hasIndexStateResult(text) {
  const lines = String(text).split('\n').map((line) => line.trim()).filter(Boolean);
  let expectOutput = false;
  let pendingCommand = null;
  const countsByCommand = new Map();
  for (const line of lines) {
    if (PROOF_COMMAND_RE.test(line)) {
      expectOutput = LS_FILES_COMMAND_RE.test(line);
      pendingCommand = expectOutput ? normalizeLsFilesCommand(line) : null;
      continue;
    }
    if (!expectOutput) continue;
    expectOutput = false;
    if (PROOF_NONE_GUARD_RE.test(line)) return true;
    if (PROOF_COUNT_LINE_RE.test(line)) {
      const counts = countsByCommand.get(pendingCommand) ?? [];
      counts.push(Number(line));
      countsByCommand.set(pendingCommand, counts);
    }
    pendingCommand = null;
  }
  for (const counts of countsByCommand.values()) {
    if (counts.length >= 2 && new Set(counts).size > 1) return true;
  }
  return false;
}

function proofResult(text) {
  if (PROOF_NONZERO_RE.test(text)) return false;
  return PROOF_RESULT_RE.test(text) || hasIndexStateResult(text);
}

function hasCommandAndResult(text) {
  return proofCommand(text) && proofResult(text);
}

// Proof helpers — an agent can type "tested locally" for free; a screenshot
// or a real command output costs work, so proof is the part worth checking.
// A user-attachments URL is the only proof that does not bloat the repo.
//
// Fenced code remains outside this check's scope. Inline code is allowed to
// carry a real URL, so its backticks must not become part of the asset id.
// Both callers pass text the body reader has already been through, so comments
// are gone before this sees them. Stripping them again here was not just
// redundant, it was wrong: a plain regex cannot tell a live `<!--` from an
// escaped `\<!--`, so it deleted the attachments on a line GitHub renders.
function countUserAttachments(body) {
  const visible = String(body || '');
  // No indentation filter here, deliberately. Four leading spaces mark an
  // indented code block only OUTSIDE a list; inside one they are continuation
  // content that renders normally, and a line-start test cannot tell the two
  // apart. Filtering on indentation alone rejected an attachment written under
  // a bullet -- an ordinary way to caption before and after -- which is a false
  // failure on honest work. Answering it needs real block containment, which is
  // the body reader's job (#143), not a second implementation here. Until then
  // an inert URL counts, and that is the safe direction to be wrong.
  const text = visible;
  // Backticks are Markdown syntax, not URL characters. Angle brackets mark
  // the before/after placeholders in this convention's own docs; counting
  // them would let copied examples through as real assets.
  const matches = text.match(/https:\/\/github\.com\/user-attachments\/assets\/[^\s"'\x60\)\]<>]+/g);
  if (!matches) return 0;
  // Distinct assets, not link count. The threshold asks for before AND after,
  // so the same image pasted twice is one image and must not clear it -- and a
  // query string or fragment on the same asset is still that asset. The match
  // itself excludes Markdown delimiters, quotes and whitespace, but not
  // sentence punctuation, so a bare URL followed by a period or comma in prose
  // keeps that character; strip it too or the same asset pasted once inside
  // markdown and once in prose counts as two.
  return new Set(matches.map((url) => url.split(/[?#]/)[0].replace(/[.,;:!?]+$/, ''))).size;
}


// A comment is not visible text, and neither is a fenced code block. A body that
// documents this checker quotes its own escape hatch, and a quoted rule must not
// satisfy the rule it quotes. Both callers read the "How I verified" section
// through here, and they answer an UNTERMINATED fence in opposite directions:
//
//   - The hatch fails CLOSED. A `Proof: n/a` inside a fence that never closes
//     must not grant a waiver, the same way a label nobody can attribute is
//     dropped rather than honoured.
//   - The evidence fails OPEN. A stray ``` above a screenshot must not swallow
//     it and fail a pull request that did nothing wrong.
const QUOTE_PREFIX = /^(?:\s{0,3}>\s?)+/;

function isQuoted(line) {
  return QUOTE_PREFIX.test(line);
}

// A fence may follow a list marker, and it then closes at its own column rather
// than at column zero. Four or more leading spaces is indented code, never a
// fence. A backtick fence cannot carry a backtick in its info string -- GitHub
// reads such a line as plain text, so it never opens anything.
function fenceOpener(line) {
  const match = /^( {0,3})((?:[-*+]|\d{1,9}[.)])[ \t]+)?(`{3,}|~{3,})(.*)$/.exec(line);
  if (!match) return null;
  const [, indent, marker, run, info] = match;
  if (run[0] === '`' && info.includes('`')) return null;
  return { char: run[0], len: run.length, indent: indent.length + (marker || '').length };
}

// The closer sits at the fence's own column, give or take the three spaces
// GitHub always forgives -- measured from column zero, not from the opener's
// indent, so a six-space line never closes a three-space fence.
function isFenceCloser(line, fence) {
  return new RegExp(`^ {0,3}[${fence.char}]{${fence.len},}[ \\t]*$`).test(line);
}

function visibleBody(body, { unmatchedFenceHides }) {
  // Normalise CRLF first: a closer ending in a bare \r never matched, so a
  // CRLF body left a closed fence looking unterminated.
  const lines = String(body || '').replace(/\r\n/g, '\n').split('\n');
  const hidden = new Array(lines.length).fill(false);
  // Lines can be emitted MODIFIED, not just kept or dropped: an inline comment
  // is removed from its line while the rest of that line stays visible.
  const text = lines.slice();
  let fence = null;
  let fenceStart = -1;
  let fenceQuoted = false;
  let inComment = false;

  for (let index = 0; index < lines.length; index += 1) {
    const raw = lines[index];
    let rest = raw;

    // An HTML comment is raw text on GitHub: nothing inside it is parsed, so a
    // fence marker within one never opens a fence. An unterminated comment runs
    // to the end of the document.
    if (inComment) {
      hidden[index] = true;
      const close = rest.indexOf('-->');
      if (close === -1) continue;
      rest = rest.slice(close + 3);
      text[index] = rest;
      hidden[index] = false;
      inComment = false;
    }

    if (fence) {
      const body = fenceQuoted ? rest.replace(QUOTE_PREFIX, '') : rest;
      // A quoted closer cannot close a fence opened outside the quote: GitHub
      // renders it as literal content inside the still-open fence.
      // A fence opened inside a blockquote ends when the quote container does:
      // GitHub cannot continue it outside the quote. Leaving it open swallowed
      // every later line and read real proof as hidden.
      if (fenceQuoted && !isQuoted(rest)) { fence = null; }
      else {
        const closes = fenceQuoted
          ? isFenceCloser(body, fence)
          : !isQuoted(rest) && isFenceCloser(body, fence);
        hidden[index] = true;
        if (closes) fence = null;
        continue;
      }
    }

    // Only an unescaped marker opens a comment, and backslashes escape in pairs
    // so an even run leaves the marker live. A line can carry more than one
    // comment, so keep going until none is left -- stopping at the first let a
    // second comment's contents through as visible evidence.
    let opened = false;
    for (let marker = rest.indexOf('<!--'); marker !== -1; marker = rest.indexOf('<!--', marker + 1)) {
      let slashes = 0;
      for (let at = marker - 1; at >= 0 && rest[at] === '\\'; at -= 1) slashes += 1;
      if (slashes % 2 !== 0) continue;
      const close = rest.indexOf('-->', marker + 4);
      if (close === -1) {
        // An unterminated comment runs to the end of the document, but whatever
        // sat BEFORE the marker on this line still renders. Dropping the whole
        // line lost a hatch or a screenshot written ahead of it.
        rest = rest.slice(0, marker);
        opened = true;
        break;
      }
      rest = rest.slice(0, marker) + rest.slice(close + 3);
      marker -= 1;
    }
    text[index] = rest;
    if (opened) { inComment = true; if (!rest.trim()) hidden[index] = true; continue; }

    const quoted = isQuoted(rest);
    const opener = fenceOpener(quoted ? rest.replace(QUOTE_PREFIX, '') : rest);
    if (opener) {
      fence = opener;
      fenceStart = index;
      fenceQuoted = quoted;
      hidden[index] = true;
    }
  }

  // An unterminated fence is the one case the two callers disagree about.
  if (fence && !unmatchedFenceHides) {
    for (let index = fenceStart; index < lines.length; index += 1) hidden[index] = false;
  }
  return text.filter((_, index) => !hidden[index]).join('\n');
}

function verificationSection(body, options) {
  return sectionBody(visibleBody(body, options), 'How I verified') || '';
}

// Scans the section it is handed. The caller decides which reading of an
// unterminated fence applies, because the hatch and the evidence answer that
// question in opposite directions.
function hasValidProofNa(text) {
  for (const line of String(text || '').split('\n')) {
    const match = PROOF_NA_LINE.exec(line);
    // match[1] is the Proof reason. Operator: n/a leaves it undefined;
    // calling trim() would throw, and Operator is not this hatch anyway.
    if (match && match[1] && match[1].trim().length >= 20) return true;
  }
  return false;
}

// A command and its result cost nothing to type whether or not the command
// ran -- `bun test -> 214 passed` reads identically either way, and nothing
// mechanical can tell the two apart from text alone. What CAN be checked is
// whether the claim points to something outside the body: a run GitHub itself
// executed, or an attachment that took a real screen capture to produce. The
// documented `Proof: n/a` hatch counts too, because it already carries its own
// burden (a stated reason, judged by the review council) that a bare command
// claim does not.
// #210 tried to name, inside one regex, every character that can legitimately
// follow a run ID in prose or Markdown -- and grew a new clause every time the
// review council found one more real shape (a parenthetical closing on a
// period, Markdown bold) that the previous clause rejected, or one more fake
// shape (`_`, `-`, a glued `.`) that it accepted. Four rounds of that and the
// lookahead was still a deny-list wearing an allow-list's name: it enumerated
// followers instead of checking structure.
//
// A later attempt split the match from the validation: grab a broad
// URL-shaped candidate first, decide if it's real after. That reintroduced
// the same bug in a new spot -- the candidate regex still had to exclude
// delimiter characters (`)`, `]`, quotes, a backtick) so Markdown wrappers
// didn't get swallowed into the match, which meant a fake glued onto the
// digits with one of THOSE characters (`123)not-a-run`) got truncated to a
// clean-looking `.../123` before validation ever saw the `)not-a-run` tail.
//
// The fix is one regex, one lookahead, checking the real source text instead
// of a pre-truncated copy of it: what follows the digits is either an
// immediate URL continuation (`/`, `?`, `#`), or a run of ordinary
// closing/punctuation characters that actually reaches whitespace or the end
// of the string. Structural, not enumerable, and there is no separate
// "grab now, worry about the edges later" step for stray characters to hide
// behind. (`_` is in that closing set alongside `*` so a run URL wrapped in
// Markdown underscore-emphasis, `_..._`, reads the same as `**bold**` does.
// `}` closes the set the same way `)` and `]` already do, for a URL wrapped
// in a curly brace instead of a paren or bracket.)
const ACTIONS_RUN_URL =
  /https:\/\/github\.com\/[^\s\/]+\/[^\s\/]+\/actions\/runs\/\d+(?=[\/?#]|[.,;:!*_"'\x60\)\]\}<>]*(?:\s|$))/;

function hasExternalProofEvidence(verifiedSection, hatchSection) {
  if (countUserAttachments(verifiedSection) > 0) return true;
  if (ACTIONS_RUN_URL.test(verifiedSection)) return true;
  if (hasValidProofNa(hatchSection)) return true;
  return false;
}

export function isUiFile(filename, config = DEFAULT_CONFIG) {
  const uiGlobs = config.uiGlobs || [];
  const uiExcludeGlobs = config.uiExcludeGlobs || [];
  const matchesUi = uiGlobs.some((pattern) => matchesGlob(filename, pattern));
  if (!matchesUi) return false;
  const excluded = uiExcludeGlobs.some((pattern) => matchesGlob(filename, pattern));
  return !excluded;
}

// Names the UI files rather than just counting them, because the hatch refusal
// below has to tell an author WHICH file contradicts their "nothing visible
// changed" claim. A bare "your waiver is refused" sends them back to re-read
// their own diff; naming the file makes the disagreement checkable in one look.
export function uiDiffFiles(files, config = DEFAULT_CONFIG) {
  if (!Array.isArray(files) || files.length === 0) return [];
  // A rename that moves a UI file to a name the globs no longer match (an
  // extension swap, or out of components/**) still ships whatever content
  // change rode along with the rename. The pre-rename name is UI evidence
  // GitHub already gives us on the same file object; checking only the new
  // name would let a rename silently clear the proof requirement.
  const names = [];
  for (const file of files) {
    if (typeof file !== 'object' || file === null) {
      const name = String(file || '');
      if (isUiFile(name, config)) names.push(name);
      continue;
    }
    const filename = String(file.filename || '');
    const previous = String(file.previous_filename || '');
    if (isUiFile(filename, config) || isUiFile(previous, config)) names.push(filename || previous);
  }
  return names;
}

export function hasUiDiff(files, config = DEFAULT_CONFIG) {
  return uiDiffFiles(files, config).length > 0;
}

const PROOF_MEDIA_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mov', 'webm']);
// Keep directory signals separate from filename signals. Mixing them makes a
// future exemption easy to apply to the wrong kind of path rule.
const PROOF_MEDIA_DIR_GLOBS = [
  'screenshot*/**',
  '**/screenshots/**',
  'proof*/**',
];
const PROOF_MEDIA_NAME_GLOBS = [
  '**/*before*',
  '**/*after*',
  '**/*demo-recording*',
];
const PROOF_MEDIA_ASSET_DIR_GLOBS = ['public/**', '**/assets/**'];

function isProofMediaPath(filename) {
  const normalized = String(filename).replaceAll('\\', '/').replace(/^\.\//, '');
  if (!normalized.includes('/')) return true;
  // The asset-root exemption wins over every other signal, including a
  // proof-named directory. `public/screenshots/` is a completely ordinary
  // product pattern -- a docs site or a landing page serving a screenshot
  // gallery -- and flagging it rejects honest work, which is the one direction
  // this check must not be wrong in. Someone committing pull request media
  // puts it at the repo root or in `proof/`, not under a served asset root.
  if (PROOF_MEDIA_ASSET_DIR_GLOBS.some((pattern) => matchesGlob(normalized, pattern))) return false;
  if (PROOF_MEDIA_DIR_GLOBS.some((pattern) => matchesGlob(normalized, pattern))) return true;
  return PROOF_MEDIA_NAME_GLOBS.some((pattern) => matchesGlob(normalized, pattern));
}

export function isCommittedProofMedia(file) {
  const filename = String(file.filename || '');
  if (!filename) return false;
  // Only files ADDED by the diff are proof media committed by mistake. Treating
  // modified or renamed files as added rejects honest product-asset changes.
  // Treating a missing status as non-added lets committed media through when a
  // caller lacks a GitHub payload.
  // When no status is supplied, treat the file as added so unit tests can still
  // exercise the glob and extension rules without a GitHub payload.
  if (Object.prototype.hasOwnProperty.call(file, 'status') && file.status !== 'added') return false;
  const lower = filename.toLowerCase();
  const dot = lower.lastIndexOf('.');
  if (dot === -1) return false;
  const ext = lower.slice(dot + 1);
  if (!PROOF_MEDIA_EXTENSIONS.has(ext)) return false;
  return isProofMediaPath(filename);
}

// Proof is one question — does this pull request show the work it did — so it
// is one check, even though its evidence comes from three places: the body, the
// files, and the labels. Splitting it across validateBody and checkSize made
// each caller responsible for suppressing the other's half.
export function checkProof(body, files, config = DEFAULT_CONFIG) {
  const failures = [];
  const warnings = [];
  // No label clears this. #114 removed the size cap's override label because an
  // agent can apply its own label, and that argument applies unchanged here --
  // a proof requirement an agent can waive is not a requirement. The only
  // escape is a stated reason in the body, which the review council judges.
  if (config.requireProof === false) return { failures, warnings };

  for (const file of files || []) {
    if (!isCommittedProofMedia(file)) continue;
    failures.push(fail(
      'committed proof media',
      String(file.filename || ''),
      'proof media uploaded to GitHub user-attachments, not committed',
      'Remove it from the commit and upload it to https://uploads.github.com/user-attachments/assets instead. A screenshot lives in the repo history forever; a link does not.',
    ));
  }

  // A visual change reviewed only as code is reviewed only half. The escape
  // hatch is a stated reason, which the review council judges — the checker
  // cannot tell a real one from "n/a". Both live under ## How I verified per
  // the docs, so an attachment or hatch line pasted under ## What or ## Why
  // does not count: the evidence belongs where the reviewer is told to look.
  // The two readings differ only for an UNTERMINATED fence. Evidence fails
  // OPEN, so a stray ``` above a screenshot does not swallow it and fail a pull
  // request that did nothing wrong. The hatch fails CLOSED, so a `Proof: n/a`
  // inside a fence that never closes grants no waiver.
  //
  // The hatch does not survive contact with a UI diff. It waives proof for a
  // pull request with no visual surface, and whether there IS a visual surface
  // is the one half of that claim the checker can settle on its own — it is
  // already computing it. Leaving the two uncrossed made the waiver
  // unenforceable: `Proof: n/a — no user-visible surface changed by this pull
  // request` is 51 characters of boilerplate that cleared the requirement on
  // any diff at all, and it was live on ~14 open private-repo-f304 pull requests, false
  // on nearly all of them. A reason the checker can read and disprove is not a
  // reason the review council should have to adjudicate.
  //
  // Only refused when the waiver is actually doing the waiving. A pull request
  // that posts before/after media AND states a hatch reason has done the work;
  // failing it for the redundant line would fire the gate on a compliant
  // author, and a gate that fires on everything is worth as little as one that
  // fires on nothing.
  const verifiedSection = verificationSection(body, { unmatchedFenceHides: false });
  const hatchSection = verificationSection(body, { unmatchedFenceHides: true });
  const uiFiles = uiDiffFiles(files || [], config);
  let uiProofFailed = false;
  if (uiFiles.length > 0) {
    const count = countUserAttachments(verifiedSection);
    if (count === 0) {
      uiProofFailed = true;
      if (hasValidProofNa(hatchSection)) {
        const shown = uiFiles.slice(0, 3).join(', ');
        const rest = uiFiles.length > 3 ? `, and ${uiFiles.length - 3} more` : '';
        failures.push(fail(
          'proof of a visible change',
          `\`Proof: n/a\` claimed, but the diff changes ${uiFiles.length} user-visible file(s): ${shown}${rest}`,
          'before and after media, because the hatch only covers a diff with no visual surface',
          'Capture the screen before and after, upload both to GitHub user-attachments, and embed them under "How I verified". If these files genuinely render nothing, the honest fix is a narrower diff, not a waiver the diff contradicts.',
        ));
      } else {
        failures.push(fail(
          'proof of a visible change',
          'no user-attachments URL in the body',
          'before and after media, or `Proof: n/a — <reason>`',
          'Capture the screen before and after, upload both to GitHub user-attachments, and embed them under "How I verified".',
        ));
      }
    } else if (count === 1) {
      warnings.push(fail(
        'proof of a visible change',
        'one user-attachments URL',
        'before and after',
        'One image shows the result, not the change. Add the other side.',
      ));
    }
  }

  // Evidence has to be attributable, not merely present. A command claim like
  // `bun test -> 214 passed` costs an agent nothing to write, and it reads
  // identically whether or not it ran. What can be checked is whether the claim
  // points to something outside the body: a run GitHub itself executed, or an
  // attachment that took a real capture to produce.
  //
  // Silent when the visible-change check above already failed: that failure
  // already names the same gap for a UI diff, and two findings for one missing
  // capture reads as two gaps rather than one.
  //
  // Warn by default (#85). Most repos in the fleet do not yet run their own
  // tests in CI, so failing every PR whose proof lives only in prose would turn
  // the whole fleet red on day one and get the standard switched off. A repo
  // ratchets this to a failure with `requireAttributableProof` once its tests
  // run in CI and a run link is something its own agents can always produce.
  if (!uiProofFailed && hasCommandAndResult(verifiedSection) && !hasExternalProofEvidence(verifiedSection, hatchSection)) {
    const finding = fail(
      'attributable proof',
      'a command and result claimed in text, nothing outside the body to check it against',
      'a linked Actions run, an attachment, or `Proof: n/a — <reason>`',
      'A line like `bun test -> 214 passed` reads the same whether or not it ran. Link the Actions run that produced it, attach a screenshot, or state a `Proof: n/a` reason.',
    );
    if (config.requireAttributableProof) failures.push(finding);
    else warnings.push(finding);
  }
  return { failures, warnings };
}

export function validateBody(body, issueNumber, config = DEFAULT_CONFIG) {
  const source = String(body || '');
  const visibleSource = source.replace(/<!--[\s\S]*?-->/g, '');
  const failures = [];
  const visible = visibleSource.trim();
  if (visible.length < config.minBodyChars) {
    failures.push(fail(
      'PR body length',
      `${visible.length} characters`,
      `at least ${config.minBodyChars} characters`,
      'Add a short explanation under What, Why, and How I verified.',
    ));
  }

  const references = countClosingReferences(visibleSource);
  if (issueNumber === null) {
    if (references.length !== 0) {
      failures.push(fail(
        'closing issue references',
        `${references.length} references`,
        'no Closes #N or Fixes #N for a chore PR',
        'Remove the Closes reference, or use a numbered branch instead of a chore branch.',
      ));
    }
  } else {
    if (references.length !== 1) {
      failures.push(fail(
        'closing issue references',
        `${references.length} references`,
        `exactly one Closes #${issueNumber} or Fixes #${issueNumber}`,
        `Keep only: Closes #${issueNumber}`,
      ));
    } else if (references[0].repo || references[0].number !== issueNumber) {
      const got = references[0].repo ? `${references[0].repo}#${references[0].number}` : `#${references[0].number}`;
      failures.push(fail(
        'closing issue reference',
        got,
        `#${issueNumber}`,
        `Replace it with: Closes #${issueNumber}`,
      ));
    }
  }

  const what = sectionBody(visibleSource, 'What');
  const why = sectionBody(visibleSource, 'Why');
  const verified = sectionBody(visibleSource, 'How I verified');
  if (!what) {
    failures.push(fail('PR body section', 'missing ## What', '## What with one to three sentences', 'Add a ## What section.'));
  } else if (sentenceCount(what) < 1 || sentenceCount(what) > 3) {
    failures.push(fail('## What length', `${sentenceCount(what)} sentences`, 'one to three sentences', 'Rewrite ## What as one to three sentences.'));
  }
  if (!why) {
    failures.push(fail('PR body section', 'missing ## Why', '## Why with the problem and reason for the fix', 'Add a ## Why section.'));
  }
  // The N/A guard exists to reject a section that refuses to answer. The
  // documented proof escape hatch, `Proof: n/a — <reason>`, is an answer, and
  // so is `Operator: n/a` on a mechanical PR. Swap a valid hatch line for its
  // reason before the guard runs, rather than dropping the line outright: a
  // reason of just "TODO" or "N/A" is still a refusal, and the guard must still
  // see it. A bare Operator: n/a has no reason, so the swap is empty text —
  // returning hatch[1] would be undefined and join() would drop the line,
  // hiding an Operator reason of "TODO" captured only in [2].
  // A bare N/A, a TODO, "tested locally", and a `Proof: n/a` with no reason all
  // still fail.
  // Quoted text is not a claim. A body that explains the rule inside the section
  // the rule reads — "a bare `N/A`, a `TODO`, \"tested locally\"" — was failed by
  // its own explanation, and the message named nothing. Drop fenced blocks and
  // inline code before testing for a refusal to answer. Only this test is
  // affected: hasCommandAndResult still reads the raw section, because a command
  // and its output belong in a code block.
  const claimed = verified === null ? null
    : verified
      .replace(/^ {0,3}(`{3,}|~{3,})[\s\S]*?^ {0,3}\1[ \t]*$/gm, '')
      .replace(/`[^`\n]*`/g, '')
      .split('\n').map((line) => {
        const hatch = PROOF_NA_LINE.exec(line);
        if (!hatch) return line;
        // hatch[1] is the Proof reason; hatch[2] is the optional Operator
        // reason. A bare Operator: n/a leaves both undefined — swap in empty
        // text so the labelled n/a does not trip the guard.
        return hatch[1] ?? hatch[2] ?? '';
      }).join('\n');
  const command = Boolean(verified) && proofCommand(verified);
  const result = Boolean(verified) && proofResult(verified);
  const refused = claimed !== null && /\b(?:N\/A|TODO|tested locally)\b/i.test(claimed);
  if (!verified || refused || !command || !result) {
    // Name the half that fell short. Both halves used to produce the same
    // message, so a bunx rejection was read as the command half failing when
    // the result half was the one that missed (`Found 0 warnings`), and #125
    // was filed against the wrong cause.
    let expected = 'a command and its result, such as: bun test -> 214 passed';
    let fix = 'Run a check and record the command and result under ## How I verified.';
    if (verified && !refused && command && !result) {
      expected = 'Found a command but no result. Record 13 passed, Found 0 warnings, a git ls-files before/after count, or (none tracked)';
      fix = 'Found a command but no result. Record what the command printed.';
    } else if (verified && !refused && !command && result) {
      expected = 'Found a result but no command. Name the command you ran, such as: bash tests/x.sh';
      fix = 'Found a result but no command. Name the command you ran.';
    }
    failures.push(fail(
      '## How I verified',
      verified || 'missing',
      expected,
      fix,
    ));
  }
  {
    // The accepted form matches one trailer per line, so a comma-separated
    // list fails. Most work in this fleet has two or more contributors, so
    // that list is the common way this check fails, and the line is right
    // there in the body when it does. A "missing" message denies what the
    // reviewer can see, so the failure must name the line it found.
    //
    // Every candidate line must be checked, not just the first: testing the
    // whole body against the accepted-form pattern only proves that SOME line
    // matches, so a valid first trailer followed by a malformed second one
    // passed silently. Commas are excluded from both fields too: `[^\s]+`
    // alone accepts a comma-separated list that has no space after the
    // comma, contradicting the documented rule that the list fails.
    const assistedByLines = assistedByLinesFromBody(visibleSource);
    const badLine = assistedByLines.find((line) => !isValidAssistedByLine(line));
    if (assistedByLines.length === 0) {
      failures.push(fail(
        'Assisted-by line',
        'missing',
        'Assisted-by: <agent>:<model>',
        'Add Assisted-by: <agent>:<model> in the body.',
      ));
    } else if (badLine) {
      failures.push(fail(
        'Assisted-by line',
        `not in the accepted form: ${badLine.trim()}`,
        'one Assisted-by: <agent>:<model> line per contributor',
        'Write one Assisted-by: <agent>:<model> line per contributor.',
      ));
    }
  }

  // The council used to run on the pull request. It now has to be a second
  // model, and the proof is these two lines. A comment can carry them instead;
  // that path is resolved later, once the conversation has been fetched.
  const review = sectionBody(visibleSource, 'Review');
  if (review === null) {
    failures.push(fail(
      'PR body section',
      'missing ## Review',
      '## Review with Reviewed-by and a Verdict, or the same two lines in a pull request comment',
      'Add a ## Review section, or post the review as a pull request comment.',
    ));
  } else {
    failures.push(...reviewProofFailures(review, authorLabels(visibleSource)));
  }

  return { ok: failures.length === 0, failures };
}

function expandBraces(pattern) {
  const open = pattern.indexOf('{');
  if (open === -1) return [pattern];
  let depth = 0;
  for (let index = open; index < pattern.length; index += 1) {
    if (pattern[index] === '{') depth += 1;
    if (pattern[index] === '}') {
      depth -= 1;
      if (depth === 0) {
        const inside = pattern.slice(open + 1, index);
        const choices = [];
        let choiceStart = 0;
        let choiceDepth = 0;
        for (let choiceIndex = 0; choiceIndex < inside.length; choiceIndex += 1) {
          if (inside[choiceIndex] === '{') choiceDepth += 1;
          if (inside[choiceIndex] === '}') choiceDepth -= 1;
          if (inside[choiceIndex] === ',' && choiceDepth === 0) {
            choices.push(inside.slice(choiceStart, choiceIndex));
            choiceStart = choiceIndex + 1;
          }
        }
        choices.push(inside.slice(choiceStart));
        if (choices.length < 2) return [pattern];
        const before = pattern.slice(0, open);
        const after = pattern.slice(index + 1);
        return choices.flatMap((choice) => expandBraces(`${before}${choice}${after}`));
      }
    }
  }
  return [pattern];
}

function globRegExp(pattern) {
  let source = '^';
  for (let index = 0; index < pattern.length; index += 1) {
    const character = pattern[index];
    if (character === '*') {
      if (pattern[index + 1] === '*') {
        while (pattern[index + 1] === '*') index += 1;
        if (pattern[index + 1] === '/') {
          index += 1;
          source += '(?:.*/)?';
        } else {
          source += '.*';
        }
      } else {
        source += '[^/]*';
      }
    } else {
      source += /[\\^$+?.()|[\]{}]/.test(character) ? `\\${character}` : character;
    }
  }
  return new RegExp(`${source}$`);
}

export function matchesGlob(filename, pattern) {
  const normalizedFilename = String(filename).replaceAll('\\', '/').replace(/^\.\//, '');
  return expandBraces(String(pattern)).some((expanded) => globRegExp(expanded).test(normalizedFilename));
}

// A line removed from one file and added verbatim to another is a RELOCATION,
// not authored work. Counting it on both sides made a pure move cost twice its
// size, so a move could fail the cap while adding nothing -- and no
// decomposition of it could pass, because every section cost double. See
// itsryanarmani/scripts#299: an 8-section move measured 6,981 counted lines while
// its authored content was 25.
//
// The discount is granted only by proving the move: byte equality across the
// whole diff. Change five lines inside a thousand-line move and those five
// still count. That is also the only review question a relocation has -- did
// anything get lost -- so the exemption and the proof are one computation.
export function countMovedLines(files) {
  // Per line content, per-file counts -- a line removed and re-added in the
  // SAME file is a reorder, not a relocation, and must never be matched. The
  // GitHub `patch` field has no file-header lines (the filename is already a
  // separate property), so every `+`/`-` line is real content, including one
  // that happens to start with a second `+` or `-` (e.g. `++i;`, or a Markdown
  // `---` rule/frontmatter delimiter which becomes `----` once diff-prefixed).
  const removed = new Map();
  const added = new Map();
  const bump = (map, key, filename) => {
    if (!map.has(key)) map.set(key, new Map());
    const byFile = map.get(key);
    byFile.set(filename, (byFile.get(filename) || 0) + 1);
  };
  for (const file of files) {
    // GitHub omits `patch` for very large or binary files. Without it we cannot
    // prove a move, so we do not discount one. A checker that silently
    // discounts what it could not read is worse than one that never discounts.
    if (typeof file.patch !== 'string') return { moved: 0, complete: false };
    for (const line of file.patch.split('\n')) {
      if (line.startsWith('+')) bump(added, line.slice(1), file.filename);
      else if (line.startsWith('-')) bump(removed, line.slice(1), file.filename);
    }
  }
  let moved = 0;
  for (const [line, removedByFile] of removed) {
    const addedByFile = added.get(line);
    if (!addedByFile) continue;
    for (const [removedFile, removedCount] of removedByFile) {
      let remaining = removedCount;
      for (const [addedFile, addedCount] of addedByFile) {
        if (remaining <= 0) break;
        if (addedFile === removedFile || addedCount <= 0) continue;
        const take = Math.min(remaining, addedCount);
        remaining -= take;
        addedByFile.set(addedFile, addedCount - take);
        moved += take;
      }
    }
  }
  return { moved, complete: true };
}

// GitHub reports a submodule bump as a one-line patch whose body is the literal
// `Subproject commit <sha>`. That marker is how a gitlink is told apart from a
// vendored file living at the same path, without guessing from the name.
//
// Every changed line must match, not just one: a single matching line would
// let a real edit to a vendored file smuggle itself past the exclusion by
// adding one throwaway `Subproject commit <hex>` line alongside the actual
// change, since the whole file is exempted once any line matches.
function isSubmoduleChange(file) {
  const patch = String(file.patch || '');
  const changedLines = patch.split('\n').filter((line) => line.startsWith('+') || line.startsWith('-'));
  return changedLines.length > 0
    && changedLines.every((line) => /^[-+]Subproject commit [0-9a-f]{7,40}\s*$/.test(line));
}

export function summarizeFiles(files, config = DEFAULT_CONFIG) {
  let rawLines = 0;
  let countedLines = 0;
  let excludedLines = 0;
  let countedFiles = 0;
  let excludedFiles = 0;
  const countedForMove = [];
  const topLevelDirs = new Set();
  for (const file of files) {
    const additions = Number(file.additions) || 0;
    const deletions = Number(file.deletions) || 0;
    const lines = additions + deletions;
    const filename = String(file.filename || '');
    rawLines += lines;
    // A submodule pointer under an excluded path is not vendored source. It is a
    // one-line decision about which upstream commit this repo depends on, and it
    // is the whole change in a bump PR. Excluding it counted such a PR as an
    // empty diff, which no amount of editing could fix: private-repo-b1e6#367 moved
    // vendor/public-skills and failed with 0 counted files on a real 1/1 diff.
    if (!isSubmoduleChange(file)
      && (config.excludeGlobs || []).some((pattern) => matchesGlob(filename, pattern))) {
      excludedLines += lines;
      excludedFiles += 1;
      continue;
    }
    countedLines += lines;
    countedFiles += 1;
    countedForMove.push(file);
    // Only real directories count. Treating a root file as a directory named
    // '.' made README.md plus three directories look like four.
    if (filename.includes('/')) topLevelDirs.add(filename.split('/')[0]);
  }
  const { moved: movedLines, complete: moveProven } = countMovedLines(countedForMove);
  // Both sides of a move were counted above, so remove both.
  const authoredLines = moveProven ? countedLines - 2 * movedLines : countedLines;
  return {
    rawLines,
    countedLines: Math.max(authoredLines, 0),
    grossCountedLines: countedLines,
    movedLines: moveProven ? movedLines : 0,
    excludedLines,
    rawFiles: files.length,
    countedFiles,
    excludedFiles,
    topLevelDirs: [...topLevelDirs].sort(),
  };
}

// The cap has no label escape. Every escape from a design constraint becomes
// the path: an agent told it may ask for a label asks for the label, rather
// than decomposing the work, which is the one thing the cap exists to force.
//
// The remaining escape is the right one and lives outside this checker: a
// person merges past a red check. That takes a deliberate act by a human on a
// named pull request. It cannot be requested in a body, and it leaves a record.
export function checkSize(summary, config) {
  config ??= DEFAULT_CONFIG;
  const failures = [];
  const warnings = [];
  // Exclusions remove files from the size caps, not from the diff. GitHub's
  // changed-file list also includes binary and rename-only changes with no
  // textual lines, so only an empty raw list proves there is no diff.
  if (!summary.rawFiles) {
    failures.push(fail(
      'empty diff',
      '0 raw changed files',
      'at least 1 raw changed file',
      'Either the change was absorbed by a rebase of its stack — close the PR, the work is already on main — or the branch was cut but never committed to, and the work still needs doing.',
    ));
  }
  if (summary.countedLines > config.maxLines) {
    failures.push(fail(
      'PR size',
      `${summary.countedLines.toLocaleString()} counted lines`,
      `${config.maxLines.toLocaleString()} counted lines or fewer`,
      'Split the change. There is no label that clears this.',
    ));
  }
  if (summary.countedFiles > config.maxFiles) {
    failures.push(fail(
      'changed files',
      `${summary.countedFiles} counted files`,
      `${config.maxFiles} counted files or fewer`,
      'Split the change. There is no label that clears this.',
    ));
  }
  if (summary.topLevelDirs.length > config.maxTopLevelDirs) {
    warnings.push(fail(
      'top-level directories',
      summary.topLevelDirs.join(', '),
      `${config.maxTopLevelDirs} or fewer`,
      'Split unrelated directories into separate pull requests.',
    ));
  }
  return { failures, warnings };
}

function repoRoot() {
  try {
    return execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim();
  } catch {
    return process.cwd();
  }
}

export function validateConfig(config) {
  if (!isValidPrefix(config.prefix)) throw new ConfigurationError('prefix must be 2-4 lowercase letters');
  if (typeof config.requireIssue !== 'boolean') throw new ConfigurationError('requireIssue must be true or false');
  if (typeof config.allowChoreEscape !== 'boolean') throw new ConfigurationError('allowChoreEscape must be true or false');
  for (const field of ['maxLines', 'maxFiles', 'maxTopLevelDirs', 'minBodyChars', 'maxBaseCommitsBehind']) {
    if (!Number.isInteger(config[field]) || config[field] < 0) throw new ConfigurationError(`${field} must be a non-negative integer`);
  }
  if (!Array.isArray(config.bannedCommitTrailers) || !config.bannedCommitTrailers.every((value) => typeof value === 'string' && value.length > 0 && value === value.trim())) throw new ConfigurationError('bannedCommitTrailers must be an array of non-empty strings with no leading or trailing whitespace');
  if (!Array.isArray(config.exemptBranches) || !config.exemptBranches.every((value) => typeof value === 'string')) throw new ConfigurationError('exemptBranches must be an array of strings');
  if (!Array.isArray(config.excludeGlobs) || !config.excludeGlobs.every((value) => typeof value === 'string')) throw new ConfigurationError('excludeGlobs must be an array of strings');
  if (typeof config.requireProof !== 'boolean') throw new ConfigurationError('requireProof must be true or false');
  if (typeof config.requireAttributableProof !== 'boolean') throw new ConfigurationError('requireAttributableProof must be true or false');
  if (!Array.isArray(config.uiGlobs) || !config.uiGlobs.every((value) => typeof value === 'string')) throw new ConfigurationError('uiGlobs must be an array of strings');
  if (!Array.isArray(config.uiExcludeGlobs) || !config.uiExcludeGlobs.every((value) => typeof value === 'string')) throw new ConfigurationError('uiExcludeGlobs must be an array of strings');
  return config;
}

export function loadConfig(root = repoRoot(), repoName = repositoryName(root)) {
  const filename = path.join(root, '.github', 'pr-standards.json');
  let overrides = {};
  if (fs.existsSync(filename)) {
    try {
      overrides = JSON.parse(fs.readFileSync(filename, 'utf8'));
    } catch (error) {
      throw new ConfigurationError(`cannot read ${path.relative(root, filename)}: ${error.message}`);
    }
    if (!overrides || Array.isArray(overrides) || typeof overrides !== 'object') {
      throw new ConfigurationError(`${path.relative(root, filename)} must contain a JSON object`);
    }
  }
  const config = { ...DEFAULT_CONFIG, ...overrides };
  let prefixSource = 'config';
  if (!config.prefix) {
    const fallback = resolveFallbackPrefix(repoName);
    config.prefix = fallback.prefix;
    prefixSource = fallback.source;
  }
  validateConfig(config);
  return {
    config,
    path: filename,
    prefixSource,
    provenance: prefixSource === 'config'
      ? 'from .github/pr-standards.json'
      : prefixSource === 'registry'
        ? 'from repo-prefixes.json'
        : 'derived',
    usedDefaultPrefix: !Object.prototype.hasOwnProperty.call(overrides, 'prefix'),
  };
}

// Cached because apiRequest asks on every call, including once per page of a
// paginated file list. The answer cannot change inside one run.
const commandExistsCache = new Map();
function commandExists(command) {
  if (commandExistsCache.has(command)) return commandExistsCache.get(command);
  const result = commandExistsUncached(command);
  commandExistsCache.set(command, result);
  return result;
}

function commandExistsUncached(command) {
  try {
    execFileSync(command, ['--version'], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

async function apiRequest(endpoint, repo) {
  if (commandExists('gh')) {
    try {
      const result = await execFileAsync('gh', ['api', `repos/${repo}/${endpoint}`], { maxBuffer: 20 * 1024 * 1024 });
      return JSON.parse(result.stdout);
    } catch (error) {
      const message = error.stderr?.trim() || error.message;
      throw new ApiError(`gh api failed for ${endpoint}: ${message}`, /\b404\b|not found/i.test(message) ? 404 : null);
    }
  }

  const token = process.env.GITHUB_TOKEN;
  if (!token) throw new ConfigurationError('gh is not on PATH and GITHUB_TOKEN is not set');
  const response = await fetch(`https://api.github.com/repos/${repo}/${endpoint}`, {
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'User-Agent': 'pr-standards',
    },
  });
  if (!response.ok) throw new ApiError(`GitHub API returned ${response.status} for ${endpoint}`, response.status);
  return response.json();
}

// The commit list caps at 250. A check that cannot see every commit must not
// report a pass, which is how the file list beside this one already behaves.
// Issue comments, the review summary, and inline review comments. Any one of
// them can carry the Reviewed-by and Verdict lines. One page is the whole
// conversation for a normal pull request; a review buried past 100 comments
// is not the proof we can see, so it does not count.
async function pullRequestDiscussion(repo, number) {
  const [issueComments, reviewComments, reviews] = await Promise.all([
    apiRequest(`issues/${number}/comments?per_page=100`, repo),
    apiRequest(`pulls/${number}/comments?per_page=100`, repo),
    apiRequest(`pulls/${number}/reviews?per_page=100`, repo),
  ]);
  const chunks = [];
  for (const list of [issueComments, reviewComments, reviews]) {
    if (!Array.isArray(list)) continue;
    for (const item of list) {
      if (item && item.body) chunks.push(item.body);
    }
  }
  return chunks;
}

async function fetchPullCommits(repo, number) {
  const commits = [];
  for (let page = 1; ; page += 1) {
    const pageCommits = await apiRequest(`pulls/${number}/commits?per_page=100&page=${page}`, repo);
    if (!Array.isArray(pageCommits)) throw new ApiError(`GitHub returned an invalid commit list for pull request ${number}`);
    commits.push(...pageCommits);
    if (pageCommits.length < 100) return commits;
  }
}

// Agents append vanity attribution to commit messages. The commits should read
// as the author's own work, so a trailer naming a model or an agent fails the
// PR. This is about the COMMIT trailer only: `Assisted-by:` in the pull request
// body is required by the standard and is a different thing, disclosure rather
// than credit.
const COAUTHOR_LINE_RE = /^\s*co-authored-by:\s*(.*)$/i;
// `Assisted-by:` is the disclosure trailer the standard requires in the pull
// request BODY. A commit that carries the same trailer is not disclosure, it
// is the credit-in-every-commit-message the standard bans, so any occurrence
// here fails regardless of which agent it names.
const ASSISTED_BY_LINE_RE = /^\s*assisted-by:\s*(.*)$/i;
// Anchored to the start of the line: this is an agent's marketing footer
// trailer, not any mention of "generated with X" inside ordinary commit
// prose. The agent name itself is checked against bannedCommitTrailers
// below, so this only recognizes the shape of the line, not a specific
// agent -- otherwise a repo that added Gemini or Codex to its config would
// still pass a "Generated with Gemini" footer because this regex only knew
// about Claude Code.
// The emoji class includes VS16 (️) and ZWJ (‍) because real emoji
// footers are multi-codepoint sequences (a pictograph plus a variation
// selector, or a ZWJ joining several pictographs). `*`, not `?`, so the whole
// sequence is consumed instead of just its first codepoint.
// Captures the remainder of the line so the name check below runs only
// against the disclosed agent, not the whole line -- otherwise a link target
// such as `Generated with Zephyr (https://cursor.example/docs)` fails
// because "cursor" appears in the URL, even though Zephyr is not banned.
const FOOTER_LINE_RE = new RegExp(`^\\s*(?:${EMOJI_RE.source})*\\s*generated (?:with|by)\\b(.*)$`, 'iu');

export function validateCommits(commits, config, truncated = false, baseRef = '') {
  const failures = [];
  if (truncated) {
    failures.push(fail(
      'commit list truncated',
      'the API returned fewer commits than the pull request reports',
      'every commit',
      'GitHub caps the list at 250. A pull request that long cannot be reviewed. Split it.',
    ));
  }
  // A promotion pull request (base `release`) carries the commits that were
  // already judged when they landed on `main`. Re-judging them here fails the
  // promotion on history nobody can change without rewriting the default
  // branch, and it fails on a trailer a squash merge added rather than a
  // person. The trailer rule therefore applies to pull requests into a working
  // branch, which is where a commit is still editable.
  if (baseRef === 'release') return { ok: failures.length === 0, failures };
  const banned = config.bannedCommitTrailers || [];
  // Word boundaries on both sides. Without them `pi` matches inside "Pia" and
  // `GPT` inside "Gupta", and a human co-author gets their PR failed for having
  // the wrong name.
  // `\b` needs a word/non-word transition, so it never matches beside a name
  // that starts or ends with punctuation: a configured `@cursor` could not fire
  // against the space before it, and the trailer passed silently. Choose the
  // boundary per name. Word char at the edge takes `\b`; anything else takes a
  // "not adjacent to a word char" lookaround, which still blocks it embedding
  // in a longer word (mycursor) but -- unlike requiring literal whitespace --
  // also fires beside ordinary punctuation such as the `[` in a markdown
  // footer link: `[@cursor](url)`. The default list is all alphanumeric, so
  // this only shows up once someone uses the documented config, which is
  // exactly when a quiet failure is hardest to notice.
  const bound = (name) => {
    const quoted = escapeRegex(name);
    const left = /^\w/.test(name) ? '\\b' : '(?<!\\w)';
    const right = /\w$/.test(name) ? '\\b' : '(?!\\w)';
    return `${left}${quoted}${right}`;
  };
  const named = banned.length
    ? new RegExp(`(?:${banned.map(bound).join('|')})`, 'i')
    : null;

  for (const entry of commits) {
    const message = entry?.commit?.message || '';
    const sha = (entry?.sha || '').slice(0, 7);
    for (const line of message.split('\n')) {
      const coAuthor = COAUTHOR_LINE_RE.exec(line);
      const assistedBy = ASSISTED_BY_LINE_RE.exec(line);
      const footer = FOOTER_LINE_RE.exec(line);
      if (coAuthor) {
        // Strip complete <...> segments rather than truncating at the first `<`.
        // Matching only the part before it means everything AFTER the email is
        // discarded too, so `vibecodereview <bot@example.com> Claude` reads as
        // the exempt bot and the Claude behind it is never seen. Removing the
        // segments keeps the reason for doing this at all, which is that a human
        // at an @anthropic.com address must not fail for their email domain.
        const name = coAuthor[1].replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
        // The owner's own review bot records what it changed. That is a real
        // author, not a model taking credit, so it stays exempt -- but only
        // when the name is exactly that bot, not a banned name smuggled in
        // alongside it (e.g. "vibecodereview Claude").
        if (/^vibecodereview$/i.test(name)) continue;
        if (!named || !named.test(name)) continue;
      } else if (assistedBy) {
        // No banned-name check: this trailer only exists to disclose an
        // agent, so its mere presence in a commit is the violation.
      } else if (footer) {
        // Strip URL segments before testing so a link target doesn't decide
        // the outcome: a markdown link's visible text is what was disclosed,
        // the parenthetical or bare URL beside it is not.
        const name = footer[1]
          .replace(/\(https?:\/\/[^)]*\)/gi, ' ')
          .replace(/https?:\/\/\S+/gi, ' ')
          .replace(/[[\]]/g, ' ')
          .trim();
        if (!named || !named.test(name)) continue;
      } else {
        continue;
      }
      failures.push(fail(
        `AI attribution in ${sha}`,
        line.trim(),
        'no model or agent named in a commit trailer',
        `Reword the commit: git rebase -i, or amend if it is the only one. Keep Assisted-by in the PR body instead.`,
      ));
      // Keep going. Stopping at the first trailer let a later Co-authored-by
      // hide behind an Assisted-by line that a promotion only warns about.
    }
  }
  return { ok: failures.length === 0, failures };
}

async function fetchPullFiles(repo, number, pull) {
  const files = [];
  for (let page = 1; ; page += 1) {
    const pageFiles = await apiRequest(`pulls/${number}/files?per_page=100&page=${page}`, repo);
    if (!Array.isArray(pageFiles)) throw new ApiError(`GitHub returned an invalid file list for pull request ${number}`);
    files.push(...pageFiles);
    if (pageFiles.length < 100) break;
  }
  await backfillMissingPatches(files, repo, pull);
  return files;
}

// GitHub omits `patch` for a file whose diff is large -- which is exactly the
// file a relocation empties. On itsryanarmani/private-repo-b1e6#170 the one file
// carrying all 3,479 deletions had no patch, so a move could never be proven
// on the change that most needed it.
//
// For those files, ask for the two blobs and derive the changed lines as a
// multiset difference. That needs no diff algorithm: what left the file is
// base minus head, what arrived is head minus base, which is precisely what
// the move check consumes.
async function backfillMissingPatches(files, repo, pull) {
  const baseSha = pull?.base?.sha;
  const headSha = pull?.head?.sha;
  if (!baseSha || !headSha) return;
  for (const file of files) {
    if (typeof file.patch === 'string') continue;
    // The destination of a move can be just as large as the source it
    // emptied, so an `added` (or `removed`) file loses its patch on the same
    // terms a `modified` one does. Its missing side is not unreadable, it is
    // empty: nothing to fetch, not a reason to skip the file.
    const base = file.status === 'added' ? [] : await fetchBlobLines(repo, file.previous_filename || file.filename, baseSha);
    const head = file.status === 'removed' ? [] : await fetchBlobLines(repo, file.filename, headSha);
    if (!base || !head) continue;
    const minus = multisetDifference(base, head).map((line) => `-${line}`);
    const plus = multisetDifference(head, base).map((line) => `+${line}`);
    file.patch = [...minus, ...plus].join('\n');
    file.patchDerived = true;
  }
}

export function multisetDifference(left, right) {
  const counts = new Map();
  for (const line of right) counts.set(line, (counts.get(line) || 0) + 1);
  const out = [];
  for (const line of left) {
    const seen = counts.get(line) || 0;
    if (seen > 0) counts.set(line, seen - 1);
    else out.push(line);
  }
  return out;
}

// text.split('\n') turns a trailing newline into a spurious empty final
// element that is not a real line. Left in, a huge added/removed file whose
// blob ends in a newline (nearly all of them) manufactures a phantom blank
// line that can falsely cancel against an unrelated real blank-line change
// elsewhere in the diff, granting a move discount that was never earned.
export function splitBlobLines(text) {
  if (text === '') return [];
  const lines = text.split('\n');
  if (text.endsWith('\n')) lines.pop();
  return lines;
}

async function fetchBlobLines(repo, path, ref) {
  try {
    const meta = await apiRequest(`contents/${path.split('/').map(encodeURIComponent).join('/')}?ref=${ref}`, repo);
    if (!meta || meta.encoding !== 'base64' || typeof meta.content !== 'string') return null;
    // A lossy decode maps every invalid byte sequence to the same replacement
    // character, so two different binary blobs can decode to identical "text"
    // and be counted as a byte-equal move. A fatal decoder refuses instead of
    // guessing, which is what keeps the move check honest.
    const text = new TextDecoder('utf-8', { fatal: true }).decode(Buffer.from(meta.content, 'base64'));
    return splitBlobLines(text);
  } catch {
    return null;
  }
}

function changedNames(files) {
  return new Set(files.flatMap((file) => [file.filename, file.previous_filename]).filter(Boolean));
}

function commitNames(commits) {
  return commits.map((commit) => {
    const subject = String(commit.commit?.message || '(no commit message)').split('\n')[0];
    return `${String(commit.sha || '').slice(0, 7)} ${subject}`;
  });
}

// A stale branch with no shared files is useful review context, but rebasing it
// on every busy repository adds work without reducing resurrection risk. When
// a stale branch and the base both touch a file, however, a squash merge can
// restore deleted code without a conflict. That case fails deliberately.
export function checkBaseBranchAge(compare, baseChanges, pullFiles, config = DEFAULT_CONFIG) {
  const behind = compare?.behind_by;
  if (!Number.isInteger(behind) || behind < 0) {
    throw new ApiError('GitHub returned an invalid branch comparison');
  }
  if (behind <= config.maxBaseCommitsBehind) return { failures: [], warnings: [] };

  const mergeBase = compare.merge_base_commit?.sha;
  if (typeof mergeBase !== 'string' || !mergeBase) {
    throw new ApiError('GitHub returned no merge base for the branch comparison');
  }
  if (!Array.isArray(baseChanges?.commits) || !Array.isArray(baseChanges?.files)) {
    throw new ApiError('GitHub returned an invalid base branch comparison');
  }
  const commits = commitNames(baseChanges.commits);
  const names = commits.length ? commits.join('; ') : '(GitHub returned no commit names)';
  const baseFiles = changedNames(baseChanges.files);
  const overlaps = [...changedNames(pullFiles)].filter((name) => baseFiles.has(name));
  const got = `${behind} commits behind since ${mergeBase.slice(0, 7)}: ${names}`;

  if (overlaps.length) {
    return {
      failures: [fail(
        'branch point overlaps base changes',
        `${got}; overlapping files: ${overlaps.join(', ')}`,
        'a branch rebased onto the base branch before merge',
        'Rebase this branch, then review the overlapping changes again.',
      )],
      warnings: [],
    };
  }
  return {
    failures: [],
    warnings: [fail(
      'branch point is behind base',
      got,
      `${config.maxBaseCommitsBehind} base commits behind or fewer`,
      'Rebase before merge if the listed base changes affect this work.',
    )],
  };
}

async function checkRemoteBaseBranchAge(repo, pull, pullFiles, config) {
  const base = pull.base?.ref;
  // The head ref name only resolves inside the base repo's own branches. A
  // fork PR's branch lives in the fork, so comparing by name here either
  // 404s or, worse, silently matches an unrelated same-named branch in the
  // base repo. The head SHA is unambiguous and GitHub mirrors it into the
  // base repo's object database via the pull request's refs.
  const headSha = pull.head?.sha;
  if (!base || !headSha) throw new ApiError('GitHub returned a pull request without base or head refs');
  const compare = await apiRequest(`compare/${encodeURIComponent(base)}...${encodeURIComponent(headSha)}`, repo);
  const behind = compare?.behind_by;
  if (!Number.isInteger(behind) || behind < 0) {
    throw new ApiError('GitHub returned an invalid branch comparison');
  }
  if (behind <= config.maxBaseCommitsBehind) {
    return { failures: [], warnings: [] };
  }
  const mergeBase = compare?.merge_base_commit?.sha;
  if (typeof mergeBase !== 'string' || !mergeBase) throw new ApiError('GitHub returned no merge base for the branch comparison');
  const baseChanges = await apiRequest(`compare/${encodeURIComponent(mergeBase)}...${encodeURIComponent(base)}`, repo);
  return checkBaseBranchAge(compare, baseChanges, pullFiles, config);
}

function currentBranch() {
  try {
    return execFileSync('git', ['branch', '--show-current'], { encoding: 'utf8' }).trim();
  } catch {
    throw new ConfigurationError('cannot read the current branch; pass a branch name explicitly');
  }
}

// The directory name is not the repo name. A worktree is checked out to a
// directory the author picked, so `scripts` becomes `scripts-pr-standards` and
// the derived prefix silently changes with it. Ask something that knows: the
// CI environment first, then the remote. The basename is the last resort.
// Split on both `/` and `:` so an SSH remote (git@github.com:owner/repo.git)
// resolves the same as an HTTPS one.
export function repositoryNameWithSource(root) {
  if (process.env.GITHUB_REPOSITORY) {
    return { name: process.env.GITHUB_REPOSITORY.split('/').pop(), source: 'GITHUB_REPOSITORY' };
  }
  try {
    const remote = execFileSync('git', ['-C', root, 'remote', 'get-url', 'origin'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    const name = remote.replace(/\.git$/, '').split(/[/:]/).pop();
    if (name) return { name, source: 'origin remote' };
  } catch {
    // No remote, or not a git repo. Fall through to the directory name.
  }
  // Last resort, and the weakest: a worktree lives in a directory the author
  // named, so this can disagree with the real repo. Callers surface the source
  // so a prefix derived this way is visible rather than assumed.
  return { name: path.basename(root), source: 'directory name' };
}

export function repositoryName(root) {
  return repositoryNameWithSource(root).name;
}

function formatNumber(value) {
  return Number(value).toLocaleString('en-US');
}

function humanFailure(item, prefix = '      ') {
  const diff = item.diff ? `\n${prefix}diff:\n${item.diff}` : '';
  return `${prefix}got:      ${item.got}\n${prefix}expected: ${item.expected}\n${prefix}fix:      ${item.fix}${diff}`;
}

function outputHuman(result) {
  const prefixLine = result.provenance
    ? `Using prefix: ${result.prefix} (${result.provenance})`
    : `Using prefix: ${result.prefix}`;
  const lines = result.prefix ? [prefixLine] : [];
  if (result.mode === 'drift' && result.adopted === false) {
    lines.push('SKIP  repo has not adopted pr-standards (no .github/pr-standards.json)');
  }
  for (const pass of result.passes || []) lines.push(`PASS  ${pass}`);
  for (const item of result.failures || []) lines.push(`FAIL  ${item.check}\n${humanFailure(item)}`);
  for (const item of result.warnings || []) lines.push(`WARN  ${item.check}\n${humanFailure(item)}`);
  if (result.size) {
    // Show every number. A discount nobody can see is one nobody can dispute.
    const parts = [`${formatNumber(result.size.rawLines)} raw`];
    if (result.size.excludedLines) parts.push(`${formatNumber(result.size.excludedLines)} excluded as generated`);
    if (result.size.movedLines) parts.push(`${formatNumber(result.size.movedLines)} moved verbatim`);
    const excluded = ` (${parts.join('; ')})`;
    lines.push(`SIZE  ${formatNumber(result.size.countedLines)} counted lines${excluded}; ${result.size.countedFiles} counted files`);
  }
  if (lines.length === 0) return;
  process.stdout.write(`${lines.join('\n')}\n`);
}

function outputJson(result) {
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

function finish(result, json) {
  result.clean = result.failures.length === 0;
  if (json) outputJson(result);
  else outputHuman(result);
  return result.clean ? 0 : 1;
}

function parseArgs(argv) {
  const args = [...argv];
  const json = args.includes('--json');
  const filtered = args.filter((arg) => arg !== '--json');
  if (filtered.includes('--help') || filtered.includes('-h')) return { help: true };
  if (filtered.includes('--selfcheck')) return { selfcheck: true };
  const mode = filtered.shift();
  if (!mode || !['branch', 'precheck', 'pr', 'drift'].includes(mode)) throw new ConfigurationError('usage: pr-standards branch [name], precheck --branch X, pr --repo owner/name --number N, or drift');
  const options = { mode, json, positional: [] };
  for (let index = 0; index < filtered.length; index += 1) {
    const arg = filtered[index];
    if (arg === '--branch' || arg === '--title' || arg === '--repo' || arg === '--number' || arg === '--prefix') {
      const value = filtered[index + 1];
      if (!value || value.startsWith('--')) throw new ConfigurationError(`${arg} requires a value`);
      options[arg.slice(2)] = value;
      index += 1;
    } else if (arg.startsWith('--')) {
      throw new ConfigurationError(`unknown option: ${arg}`);
    } else {
      options.positional.push(arg);
    }
  }
  return options;
}

function usage() {
  return `Usage:
  pr-standards branch [name]
  pr-standards precheck --branch X [--title Y] [--prefix P]
  pr-standards pr --repo owner/name --number N
  pr-standards drift
  pr-standards --selfcheck

Add --json to any command for machine-readable output.`;
}

async function runBranch(options) {
  const root = repoRoot();
  const named = repositoryNameWithSource(root);
  const { config, prefixSource } = loadConfig(root, named.name);
  // Say where the prefix came from. A prefix guessed from a directory name is
  // the one most likely to be wrong, so it must not look identical to one read
  // from the repo's own config.
  const provenance = prefixSource === 'config'
    ? 'from .github/pr-standards.json'
    : prefixSource === 'registry'
      ? 'from repo-prefixes.json'
      : `derived from ${named.source}`;
  if (options.branch || options.title || options.repo || options.number || options.prefix) throw new ConfigurationError('branch accepts only one optional branch name');
  const branch = options.positional[0] || currentBranch();
  if (options.positional.length > 1) throw new ConfigurationError('branch accepts one optional name');
  const branchResult = validateBranchName(branch, config);
  return finish({
    mode: 'branch',
    prefix: config.prefix,
    provenance,
    failures: branchResult.failures,
    warnings: [],
    passes: branchResult.ok ? [`branch name: ${branch}${branchResult.exempt ? ' (exempt)' : ''}`] : [],
  }, options.json);
}

async function runPrecheck(options) {
  const root = repoRoot();
  const named = repositoryNameWithSource(root);
  const { config, prefixSource } = loadConfig(root, named.name);
  // Say where the prefix came from. A prefix guessed from a directory name is
  // the one most likely to be wrong, so it must not look identical to one read
  // from the repo's own config.
  const provenance = prefixSource === 'config'
    ? 'from .github/pr-standards.json'
    : prefixSource === 'registry'
      ? 'from repo-prefixes.json'
      : `derived from ${named.source}`;
  if (!options.branch) throw new ConfigurationError('precheck requires --branch');
  if (options.positional.length > 0 || options.repo || options.number) throw new ConfigurationError('precheck accepts --branch, --prefix and optional --title only');
  // A caller may be judging a branch for a DIFFERENT repo than the one it is
  // standing in. The PreToolUse guard is exactly that case: it runs in the
  // session's working directory while `gh pr create --repo X` targets X. Without
  // this, the branch is checked against the wrong prefix and a conforming
  // cross-repo PR is refused.
  let effective = config;
  let effectiveProvenance = provenance;
  if (options.prefix) {
    if (!isValidPrefix(options.prefix)) {
      throw new ConfigurationError(`--prefix must be 2-4 lowercase letters, got: ${options.prefix}`);
    }
    effective = { ...config, prefix: options.prefix };
    effectiveProvenance = 'from --prefix';
  }
  const branchResult = validateBranchName(options.branch, effective);
  const failures = [...branchResult.failures];
  const passes = branchResult.ok ? [`branch name: ${options.branch}`] : [];
  if (options.title) {
    if (!branchResult.exempt) {
      if (branchResult.issueNumber !== null || branchResult.choreEscape) {
        const titleResult = validateTitle(options.title, effective.prefix, branchResult.issueNumber);
        failures.push(...titleResult.failures);
        if (titleResult.ok) passes.push('PR title');
      } else {
        failures.push(fail('PR title', options.title, 'a valid branch issue number before checking the title', 'Fix the branch name first.'));
      }
    }
  }
  return finish({ mode: 'precheck', prefix: effective.prefix, provenance: effectiveProvenance, failures, warnings: [], passes }, options.json);
}

function readTemplate(filename) {
  const templatePath = path.join(TEMPLATES_DIR, filename);
  try {
    return fs.readFileSync(templatePath, 'utf8');
  } catch (error) {
    throw new ConfigurationError(`cannot read pr-standards-templates/${filename}: ${error.message}`);
  }
}

function substituteTemplate(template, prefix) {
  return template
    .replaceAll('__PREFIX_UPPER__', prefix.toUpperCase())
    .replaceAll('__PREFIX__', prefix);
}

const MALFORMED_BLOCK = Symbol('malformed-managed-block');

// A marker WRITTEN ABOUT is not a marker. Documenting the block --
// "the `<!-- pr-standards:start -->` block" -- put a second start in the file
// and every drift check then read the whole managed block as malformed, so
// explaining the rule broke the rule. Inline code is already treated as
// not-a-claim by the proof check above; the marker scan needs the same rule.
// A real marker occupies its own line, so requiring the occurrence to be
// outside inline code costs nothing a rollout writes.
function insideInlineCode(line, column) {
  let ticks = 0;
  for (let at = 0; at < column; at += 1) {
    if (line[at] === '`') ticks += 1;
  }
  return ticks % 2 === 1;
}

// Extracting the first start/end pair and ignoring the rest would let a
// correct block followed by a leftover stale one (a hand edit, or a rollout
// repair appended after markers it wouldn't touch, see pr-standards-rollout)
// PASS while the stale duplicate goes unreported. Require exactly one pair.
// Count every marker before looking at any of them. Two rounds of review found
// a new ordering the previous check missed -- a duplicate start, then a trailing
// duplicate end, then a stray end BEFORE the real start -- because each fix
// asked "is there another marker after this one", which can only see forward.
// The guarantee wanted is a property of the whole file: exactly one start and
// exactly one end, in that order. Stating it that way has no next case.
function markerOffsets(content, marker) {
  const offsets = [];
  for (let at = content.indexOf(marker); at !== -1; at = content.indexOf(marker, at + marker.length)) {
    const lineStart = content.lastIndexOf('\n', at) + 1;
    let lineEnd = content.indexOf('\n', at);
    if (lineEnd === -1) lineEnd = content.length;
    if (!insideInlineCode(content.slice(lineStart, lineEnd), at - lineStart)) offsets.push(at);
  }
  return offsets;
}

function managedBlock(content) {
  const starts = markerOffsets(content, AGENTS_BLOCK_START);
  const ends = markerOffsets(content, AGENTS_BLOCK_END);
  // No markers at all is a file that never had the block, which is missing
  // rather than malformed -- the rollout has simply not run here.
  if (starts.length === 0 && ends.length === 0) return null;
  if (starts.length !== 1 || ends.length !== 1) return MALFORMED_BLOCK;
  // An end before its start is malformed, not missing: the markers are present
  // and wrong, which is a different thing to answer than absent.
  if (ends[0] < starts[0] + AGENTS_BLOCK_START.length) return MALFORMED_BLOCK;
  return content.slice(starts[0] + AGENTS_BLOCK_START.length, ends[0]);
}

function unifiedDiff(expected, actual, expectedLabel, actualLabel) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'pr-standards-drift-'));
  const expectedPath = path.join(directory, 'expected');
  const actualPath = path.join(directory, 'actual');
  try {
    fs.writeFileSync(expectedPath, expected);
    fs.writeFileSync(actualPath, actual);
    const result = spawnSync('diff', [
      '-u', '--label', expectedLabel, '--label', actualLabel, expectedPath, actualPath,
    ], { encoding: 'utf8' });
    if (result.status === 1) return result.stdout.trimEnd();
    if (result.status === 0) return '';
    throw new ConfigurationError(`cannot create diff: ${result.error?.message || result.stderr.trim()}`);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

function staleFailure(check, expected, actual, expectedLabel, actualLabel) {
  return {
    ...fail(
      check,
      'stale',
      `match ${expectedLabel}`,
      `Replace it with ${expectedLabel}.`,
    ),
    diff: unifiedDiff(expected, actual, expectedLabel, actualLabel),
  };
}

async function runDrift(options) {
  if (options.positional.length > 0 || options.branch || options.title || options.repo || options.number) {
    throw new ConfigurationError('drift accepts no options');
  }
  const root = repoRoot();
  const configPath = path.join(root, '.github', 'pr-standards.json');
  // A repository without the config has not adopted this standard. Do not make
  // its unrelated AGENTS.md or pull request template look like drift.
  if (!fs.existsSync(configPath)) {
    return finish({ mode: 'drift', adopted: false, failures: [], warnings: [], passes: [] }, options.json);
  }
  const { config } = loadConfig(root);
  const failures = [];
  const passes = [];
  const expectedAgents = managedBlock(substituteTemplate(readTemplate('agents-block.md'), config.prefix));
  if (expectedAgents === null || expectedAgents === MALFORMED_BLOCK) {
    throw new ConfigurationError('pr-standards-templates/agents-block.md has no managed block');
  }
  const agentsPath = path.join(root, 'AGENTS.md');
  const installedAgents = fs.existsSync(agentsPath) ? managedBlock(fs.readFileSync(agentsPath, 'utf8')) : null;
  if (installedAgents === null) {
    failures.push(fail(
      'managed AGENTS.md block',
      'missing',
      'a managed block between pr-standards markers',
      'Run pr-standards-rollout to install the managed block.',
    ));
  } else if (installedAgents === MALFORMED_BLOCK) {
    failures.push(fail(
      'managed AGENTS.md block',
      'malformed',
      'exactly one pr-standards:start/end marker pair',
      'Remove the duplicate markers, then run pr-standards-rollout to reinstall the managed block.',
    ));
  } else if (installedAgents !== expectedAgents) {
    failures.push(staleFailure(
      'managed AGENTS.md block', expectedAgents, installedAgents,
      'pr-standards-templates/agents-block.md', 'AGENTS.md managed block',
    ));
  } else {
    passes.push('managed AGENTS.md block');
  }

  const templatePath = path.join(root, '.github', 'pull_request_template.md');
  const expectedTemplate = substituteTemplate(readTemplate('pull_request_template.md'), config.prefix);
  if (!fs.existsSync(templatePath)) {
    failures.push(fail(
      'pull request template',
      'missing',
      'match pr-standards-templates/pull_request_template.md',
      'Run pr-standards-rollout to install the pull request template.',
    ));
  } else {
    const installedTemplate = fs.readFileSync(templatePath, 'utf8');
    if (installedTemplate !== expectedTemplate) {
      failures.push(staleFailure(
        'pull request template', expectedTemplate, installedTemplate,
        'pr-standards-templates/pull_request_template.md', '.github/pull_request_template.md',
      ));
    } else {
      passes.push('pull request template');
    }
  }
  return finish({ mode: 'drift', adopted: true, prefix: config.prefix, failures, warnings: [], passes }, options.json);
}

async function fetchRemoteConfig(repo, repoName, ref) {
  const fallback = resolveFallbackPrefix(repoName);
  try {
    const query = ref ? `?ref=${encodeURIComponent(ref)}` : '';
    const response = await apiRequest(`contents/.github/pr-standards.json${query}`, repo);
    if (response.encoding === 'base64' && typeof response.content === 'string') {
      const content = Buffer.from(response.content, 'base64').toString('utf8');
      // An empty file is a broken config, not an absent one. The local path
      // already errors on it; the remote path used to fall through to defaults,
      // so the same mistake produced different rules depending on the caller.
      if (!content.trim()) {
        throw new ConfigurationError(`${repo} .github/pr-standards.json is empty`);
      }
      const overrides = JSON.parse(content);
      if (!overrides || Array.isArray(overrides) || typeof overrides !== 'object') {
        throw new ConfigurationError(`${repo} .github/pr-standards.json must contain a JSON object`);
      }
      const config = { ...DEFAULT_CONFIG, ...overrides };
      const prefixSource = config.prefix ? 'config' : fallback.source;
      if (!config.prefix) config.prefix = fallback.prefix;
      validateConfig(config);
      const provenance = prefixSource === 'config'
        ? `from ${repo} .github/pr-standards.json${ref ? ` @ ${ref}` : ''}`
        : prefixSource === 'registry'
          ? 'from repo-prefixes.json'
          : `derived; ${repo} has no config prefix`;
      return { config, provenance };
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      // Fallback to default
    } else if (error instanceof SyntaxError) {
      throw new ConfigurationError(`${repo} .github/pr-standards.json contains invalid JSON: ${error.message}`);
    } else {
      throw error;
    }
  }
  const config = { ...DEFAULT_CONFIG, prefix: fallback.prefix };
  validateConfig(config);
  const provenance = fallback.source === 'registry'
    ? `from repo-prefixes.json; ${repo} has no config`
    : `derived; ${repo} has no config`;
  return { config, provenance };
}

// A release promotion merges the repository's default branch into a long-lived
// branch such as `release`. Its diff is not new work: it is every pull request
// merged since the last promotion, added together, and each of those already
// passed the size cap under its own issue and its own review. Counting those
// lines a second time measures the wrong thing, and it leaves no route at all
// -- `release` is protected, so a direct push is refused, a pull request is the
// only way in, and the cap fails it. itsryanarmani/private-repo-4a88#271 sat there at
// 792 counted lines with nothing to split.
//
// Every term below comes from GitHub's response for the pull request, not from
// anything the author writes. A title, a body or a label is author-controlled
// text; where the branches actually point is not. That is what stops this from
// becoming the label escape this standard deleted: there is no way to ask for
// it, and no field in a pull request body that turns it on.
//
//   - the head ref is the repository's own default branch, so every line in the
//     diff is already merged and already reviewed;
//   - the head repository is the base repository, because a fork's default
//     branch is also called `main` and holds whatever its owner put there;
//   - the base ref is not the default branch, so the ordinary main-bound pull
//     request that the cap exists to bound is untouched.
//
// Not required: that every commit in the diff is a merge commit. That is what a
// promotion looks like in a repository that merges with merge commits, and this
// fleet squash-merges -- the commits #271 carried are squashes with one parent
// each. The stricter test would never fire here, so it would read as a
// safeguard while doing nothing, which is worse than not writing it.
export function isReleasePromotion(pull) {
  const defaultBranch = pull?.base?.repo?.default_branch;
  const headRepo = pull?.head?.repo?.full_name;
  const baseRepo = pull?.base?.repo?.full_name;
  if (!defaultBranch || !headRepo || !baseRepo) return false;
  if (headRepo !== baseRepo) return false;
  return pull?.head?.ref === defaultBranch && pull?.base?.ref !== defaultBranch;
}

async function runPr(options) {
  if (options.positional.length > 0 || options.branch || options.title || options.prefix) throw new ConfigurationError('pr accepts --repo and --number only');
  if (!options.repo || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(options.repo)) throw new ConfigurationError('pr requires --repo owner/name');
  if (!options.number || !/^[0-9]+$/.test(options.number) || Number(options.number) < 1) throw new ConfigurationError('pr requires a positive --number');
  const repoName = options.repo.split('/').pop();
  let config;
  let provenance;
  
  // In CI, GITHUB_REPOSITORY is the local checkout which is the target repo, so we can use loadConfig
  const number = Number(options.number);
  const pull = await apiRequest(`pulls/${number}`, options.repo);

  // Read the config from the BASE branch, never from the checkout. In CI the
  // checkout is the pull request's own head, so a PR that edits
  // .github/pr-standards.json would be judged by the rules it just wrote: set
  // excludeGlobs to ["**"], or maxLines to a million, and the check that exists
  // to catch exactly that change waves it through. The base branch holds the
  // last rules that survived review, so it is the only honest thing to judge
  // against.
  const baseRef = pull.base?.ref;
  const loaded = await fetchRemoteConfig(options.repo, repoName, baseRef);
  config = loaded.config;
  provenance = loaded.provenance;
  const branch = pull.head?.ref || '';
  const branchResult = validateBranchName(branch, config);
  const failures = [...branchResult.failures];
  const warnings = [];
  const passes = [];
  if (branchResult.ok) passes.push(`branch name: ${branch}`);

  if (branchResult.issueNumber !== null && config.requireIssue) {
    try {
      const issue = await apiRequest(`issues/${branchResult.issueNumber}`, options.repo);
      if (issue.pull_request) {
        failures.push(fail('branch issue', `#${branchResult.issueNumber} is a pull request`, 'an existing open issue', `Create or select an open issue, then rename the branch.`));
      } else if (issue.state !== 'open') {
        failures.push(fail('branch issue', `#${branchResult.issueNumber} is ${issue.state}`, 'an existing open issue', `Reopen #${branchResult.issueNumber}, or create a new branch for an open issue.`));
      } else {
        passes.push(`issue #${branchResult.issueNumber} is open`);
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        failures.push(fail('branch issue', `#${branchResult.issueNumber} was not found`, 'an existing open issue', `Create or select an open issue, then rename the branch.`));
      } else {
        throw error;
      }
    }
  }
  // Files are needed before the body check so proof can be verified against
  // the actual diff. There is no proof override label -- see checkProof.
  const [commits, files] = await Promise.all([
    fetchPullCommits(options.repo, number),
    fetchPullFiles(options.repo, number, pull),
  ]);
  const commitsTruncated = typeof pull.commits === 'number' && commits.length < pull.commits;
  const commitResult = validateCommits(commits, config, commitsTruncated);
  // A promotion carries commits that are already on the default branch. A
  // squash merge copies the pull request body into the commit, so the commit
  // carries the Assisted-by line the body must have; some CLIs also add a
  // Co-authored-by for the agent. Rewriting the default branch is the only way
  // to remove either, and that is not a thing a pull request can do. A
  // promotion warns for every AI-attribution trailer and fails on nothing
  // here; the same commit fails the rule on the pull request that introduced
  // it.
  const releasePromotion = isReleasePromotion(pull);
  let commitFailures = 0;
  for (const item of commitResult.failures) {
    const disclosure = item.got.trim();
    if (releasePromotion && item.check.startsWith('AI attribution in ')) {
      warnings.push(fail(
        'release promotion: commit disclosure not applied',
        disclosure,
        'no Assisted-by trailer in a commit on ordinary work',
        `This line is the disclosure the pull request body must carry. A squash merge copies the body into the commit, and rewriting ${pull.base.repo.default_branch} is the only way to remove it.`,
      ));
      continue;
    }
    failures.push(item);
    commitFailures += 1;
  }
  if (commitFailures === 0) passes.push(`${commits.length} commit messages`);
  // GitHub's pull-request files endpoint stops at 3000 entries and gives no
  // signal that it did. Comparing against the count the pull request itself
  // reports is the only way to notice, and a size check that silently measured
  // part of a diff would be worse than one that admits it cannot.
  // A size gate that cannot see the whole diff must not report a pass. Passing
  // on a partial list is the one outcome that is actively wrong: the unseen
  // remainder is exactly where the size-triggering change would be.
  const truncated = typeof pull.changed_files === 'number' && files.length < pull.changed_files;
  if (truncated) {
    failures.push(fail(
      'diff too large to measure',
      `the API returned ${files.length} of ${pull.changed_files} changed files`,
      'a diff small enough to read in full',
      'GitHub caps the file list at 3000. A pull request this size cannot be reviewed or measured. Split it.',
    ));
  }
  if (files.some((file) => file.filename === '.github/pr-standards.json')) {
    warnings.push(fail(
      'PR edits the standard itself',
      '.github/pr-standards.json is in this diff',
      'rules that already survived review',
      `Judged against ${baseRef || 'the base branch'}, not this PR's copy. Review the config change on its own merits.`,
    ));
  }
  const summary = summarizeFiles(files, config);
  if (!branchResult.exempt) {
    const titleResult = validateTitle(pull.title || '', config.prefix, branchResult.issueNumber);
    failures.push(...titleResult.failures);
    if (titleResult.ok) passes.push('PR title');
    const bodyResult = validateBody(pull.body || '', branchResult.issueNumber, config);
    const authors = authorLabels(pull.body || '');
    let reviewFailures = bodyResult.failures.filter(isReviewCheck);
    const otherFailures = bodyResult.failures.filter((item) => !isReviewCheck(item));
    if (reviewFailures.length > 0) {
      const comments = await pullRequestDiscussion(options.repo, number);
      reviewFailures = unresolvedReviewFailures(bodyResult.failures, comments, authors);
      if (reviewFailures.length === 0) passes.push('review proof in a pull request comment');
    }
    failures.push(...otherFailures, ...reviewFailures);
    if (otherFailures.length === 0 && reviewFailures.length === 0) passes.push('PR body');
    // Same exemption as title and body: a branch exempt from the `## How I
    // verified` convention (release, refactor, gh-pages, dependabot/*,
    // renovate/*) has no reason to carry a section it was never asked to
    // write, so proof of work rides with the checks it depends on.
    const proofResult = checkProof(pull.body || '', files, config);
    failures.push(...proofResult.failures);
    warnings.push(...proofResult.warnings);
    if (proofResult.failures.length === 0) passes.push('proof of work');
  }
  const sizeResult = checkSize(summary, config);
  // The line cap and the file cap are lifted, and only for a promotion.
  // checkSize stays a pure function of the diff and the config: it is the
  // wrong place to teach about pull requests, and its arity is guarded
  // precisely so a third input cannot quietly become the next escape hatch.
  // The exemption therefore lives here, where the refs are, and drops only
  // the failures the evidence allows. The empty-diff check and the directory
  // warning stay -- an exemption wider than the evidence for it is how the
  // last escape hatch got out of hand. The file cap deadlocked
  // itsryanarmani/usegeoaeo#142 at 90 counted files.
  const promotion = isReleasePromotion(pull);
  for (const item of sizeResult.failures) {
    // Never silent. A skipped cap that prints nothing is a hole nobody can
    // audit, so the run still names the number it would have failed on.
    if (promotion && item.check === 'PR size') {
      warnings.push(fail(
        'release promotion: size cap not applied',
        item.got,
        `${config.maxLines.toLocaleString()} counted lines or fewer for ordinary work`,
        `Every line here is already merged into ${pull.base.repo.default_branch}, each under its own issue and its own review. The cap applies to the pull requests that put it there, not to the promotion that ships them.`,
      ));
      continue;
    }
    if (promotion && item.check === 'changed files') {
      warnings.push(fail(
        'release promotion: file cap not applied',
        item.got,
        `${config.maxFiles} counted files or fewer for ordinary work`,
        `Every file here is already merged into ${pull.base.repo.default_branch}, each under its own issue and its own review. The cap applies to the pull requests that put it there, not to the promotion that ships them.`,
      ));
      continue;
    }
    failures.push(item);
  }
  warnings.push(...sizeResult.warnings);
  const baseAgeResult = await checkRemoteBaseBranchAge(options.repo, pull, files, config);
  failures.push(...baseAgeResult.failures);
  warnings.push(...baseAgeResult.warnings);

  return finish({
    mode: 'pr',
    repo: options.repo,
    number,
    prefix: config.prefix,
    provenance,
    branch,
    issue: branchResult.issueNumber,
    failures,
    warnings,
    passes,
    size: summary,
  }, options.json);
}

export async function main(argv = process.argv.slice(2)) {
  let options;
  try {
    options = parseArgs(argv);
    if (options.help) {
      process.stdout.write(`${usage()}\n`);
      return 0;
    }
    if (options.selfcheck) {
      const testFile = fileURLToPath(new URL('./pr-standards.test.mjs', import.meta.url));
      const result = spawnSync(process.execPath, ['--test', testFile], { stdio: 'inherit' });
      return result.status ?? 1;
    }
    if (options.mode === 'branch') return await runBranch(options);
    if (options.mode === 'precheck') return await runPrecheck(options);
    if (options.mode === 'drift') return await runDrift(options);
    return await runPr(options);
  } catch (error) {
    const result = {
      clean: false,
      failures: [fail(error.name === 'ConfigurationError' ? 'configuration' : 'GitHub API', error.message, 'a valid configuration and accessible repository', 'Fix the command, configuration, or GitHub authentication.')],
      warnings: [],
    };
    const json = options?.json || argv.includes('--json');
    if (json) outputJson(result);
    else {
      const item = result.failures[0];
      process.stderr.write(`FAIL  ${item.check}\n${humanFailure(item)}\n`);
    }
    return error.name === 'ConfigurationError' ? 2 : 1;
  }
}
