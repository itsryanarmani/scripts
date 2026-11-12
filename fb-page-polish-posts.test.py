#!/usr/bin/env python3
"""CLI E2E for post, hide-autoposts and verify: real script, fake `browse` on PATH. No Pillow needed.

The fake cannot run Facebook's page. It answers each step from a plan, so this test proves the order,
the retries, the skips and the switch-back. Only a live run proves the selectors.

Failure modes, written before the code:
  1. The Post button is not ready after Next: the first clicks leave the dialog open, so publish must retry.
  2. The Post button never works: the run stops after --tries clicks and does not report "posted".
  3. The "What's on your mind?" box is missing: the step names it, no Post click, the run switches back.
  4. The text is already on the Page once: it is skipped with no composer. Twice: skipped and the run fails.
  5. The session stays a Page: the run fails before any post and says so.
     Switch Now is missing: the run stops before the composer, so nothing posts as the owner.
  6. verify sees a doubled post and a missing post: it reports both and exits 1.
  7. hide-autoposts on a Page with no auto-posts: one look, nothing clicked, exit 0.
  8. No --approved: refused before the browser. A first line that repeats the Page name: refused.
  9. browse prints a secret: it never reaches the output; nor does the owner name.
The step order of each case is printed, so the output is the transcript.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SCRIPT = Path(__file__).with_name('fb-page-polish')
SECRET = 'EAAB-fake-secret-token'
OWNER = 'Alex Example Owner'
# Each step takes the next answer from FAKE_PLAN[step]; the last answer repeats. "lost:<name>" fails the step.
FAKE_BROWSE = r'''#!/usr/bin/env python3
import json, os, re, sys
code = open(sys.argv[sys.argv.index('--file') + 1]).read()
step = re.search(r'// step: (\w+)', code).group(1)
log = os.environ['FAKE_LOG']
done = sum(1 for l in open(log) if json.loads(l)['step'] == step) if os.path.exists(log) else 0
with open(log, 'a') as f:
    f.write(json.dumps({'step': step, 'code': code}) + '\n')
default = {'personal': {'state': 'personal'}, 'switch': {'switched': True}}.get(step, {})
answers = json.loads(os.environ['FAKE_PLAN']).get(step, [default])
answer = answers[min(done, len(answers) - 1)]
if answer == 'crash':
    print('cookie=' + os.environ['FAKE_SECRET']); sys.exit(1)
if isinstance(answer, str) and answer.startswith('lost:'):
    print(json.dumps({'ok': False, 'error': {'message': 'Error: Control not found: ' + answer[5:],
                                             'stack': 'token=' + os.environ['FAKE_SECRET']}})); sys.exit(1)
print(json.dumps({'ok': True, 'value': answer, 'logs': []}))
'''
PAGE = {'name': 'Example Sheds', 'about': 'Sturdy backyard sheds, built to order.', 'website': 'https://example.test',
        'color': '#2f5d50', 'link': 'https://www.facebook.com/profile.php?id=1', 'slug': 'example-sheds'}
POSTS = [{'page': 'example-sheds', 'text': 'Our cedar sheds now ship with a ten year roof warranty.\nAsk us how.'},
         {'page': 'example-sheds', 'text': 'Spring build slots are open for garden sheds of every size.'}]
failures = []

def check(cond, label, detail=''):
    print(('ok   ' if cond else 'FAIL ') + label + ('' if cond else '\n     ' + detail[-600:]))
    failures.extend([] if cond else [label])

def run(command, plan, posts=POSTS, extra=()):
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, 'spec.json').write_text(json.dumps({'pages': [PAGE]}))
        Path(tmp, 'posts.json').write_text(json.dumps({'posts': posts}))
        Path(tmp, 'bin').mkdir()
        Path(tmp, 'bin/browse').write_text(FAKE_BROWSE)
        Path(tmp, 'bin/browse').chmod(0o755)
        env = dict(os.environ, PATH=f'{tmp}/bin:{os.environ["PATH"]}', FAKE_PLAN=json.dumps(plan), FAKE_SECRET=SECRET,
                   FAKE_LOG=f'{tmp}/log.jsonl', FB_OWNER_NAME=OWNER)
        args = [sys.executable, str(SCRIPT), command, '--spec', f'{tmp}/spec.json', '--session', 'test-session']
        if command != 'hide-autoposts':
            args += ['--posts', f'{tmp}/posts.json']
        r = subprocess.run(args + [*extra, *(['--approved', '--settle', '0'] if command == 'post' else [])],
                           capture_output=True, text=True, env=env)
        log = [json.loads(l) for l in Path(tmp, 'log.jsonl').read_text().splitlines()] if Path(tmp, 'log.jsonl').exists() else []
    out = r.stdout + r.stderr
    print(f'     {command}: exit {r.returncode}, steps {[s["step"] for s in log]}')
    check(SECRET not in out and OWNER not in out and 'token=' not in out, f'  no secret or owner name ({command})', out)
    reports = [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]
    return r.returncode, out, [s['step'] for s in log], log, reports

def statuses(reports):
    return [p.get('status') for p in reports[0].get('posts', [])] if reports else []

def main():
    code, out, order, log, rep = run('post', {'count': [{'counts': [0, 0]}, {'counts': [1]}],
                                              'publish': [{'open': True}, {'open': True}, {'open': False}]})
    check(code == 0 and order == ['personal', 'count', 'switch', 'compose', 'publish', 'publish', 'publish', 'count',
                                  'compose', 'publish', 'count', 'personal'] and statuses(rep) == ['posted', 'posted'],
          '1. Post button not ready: publish retries until the dialog closes', out)
    key = 'Our cedar sheds now ship with a ten year roof'
    check(json.dumps(key) in log[1]['code'] and 'Ask us how' not in log[1]['code'], '   count key is the 45-character first line')
    check('"text": "Our cedar' in log[3]['code'] and OWNER in log[0]['code'], '   text and owner name go to browse only')

    code, out, order, _, rep = run('post', {'count': [{'counts': [0, 0]}], 'publish': [{'open': True}]}, extra=['--tries', '3'])
    check(code == 1 and order.count('publish') == 3 and 'compose' == order[3] and order.count('compose') == 1
          and order[-1] == 'personal' and 'posted' not in statuses(rep), '2. Post never works: stops after --tries', out)

    code, out, order, _, rep = run('post', {'count': [{'counts': [0, 0]}], 'compose': ["lost:What's on your mind? box"]})
    check(code == 1 and "Control not found: What's on your mind? box" in out and 'publish' not in order
          and order[-1] == 'personal' and rep[0]['back'] == 'personal profile', '3. composer box missing: named, switched back', out)

    code, out, order, _, rep = run('post', {'count': [{'counts': [1, 1]}]})
    check(code == 0 and 'compose' not in order and 'switch' not in order
          and statuses(rep) == ['already on the Page'] * 2, '4a. text already posted once: skipped, no composer', out)
    code, out, order, _, rep = run('post', {'count': [{'counts': [2, 1]}]})
    check(code == 1 and 'compose' not in order and statuses(rep)[0] == 'doubled (2), not posted',
          '4b. text posted twice: skipped and the run fails', out)

    code, out, order, _, _ = run('post', {'personal': [{'state': 'page'}]})
    check(code == 1 and 'session still acts as a Page' in out and 'compose' not in order and 'count' not in order,
          '5. session left acting as a Page: fails before any post', out)

    code, out, order, _, _ = run('post', {'count': [{'counts': [0, 0]}], 'switch': [{'switched': False}]})
    check(code == 1 and 'Switch Now not found' in out and 'compose' not in order and order[-1] == 'personal',
          '5b. Switch Now missing: no post as the owner', out)

    code, out, order, log, rep = run('verify', {'count': [{'counts': [2, 0]}]}, extra=['--scrolls', '9'])
    check('"scrolls": 9' in log[0]['code'], '   --scrolls reaches the count step')
    check(code == 1 and order == ['count'] and [p['status'] for p in rep[0]['posts']] == ['doubled', 'missing'],
          '6a. verify reports a doubled and a missing post, exit 1', out)
    code, out, _, _, rep = run('verify', {'count': [{'counts': [1, 1]}]})
    check(code == 0 and [p['status'] for p in rep[0]['posts']] == ['ok', 'ok'], '6b. verify passes when each post shows once', out)

    code, out, order, _, rep = run('hide-autoposts', {'hide': [{'hidden': False}]})
    check(code == 0 and order == ['personal', 'switch', 'hide', 'personal'] and rep[0]['hidden'] == 0
          and rep[0]['autoposts'] == 'none left', '7a. hide-autoposts with no auto-posts: nothing clicked', out)
    code, out, order, _, rep = run('hide-autoposts', {'hide': [{'hidden': True}, {'hidden': True}, {'hidden': False}]})
    check(code == 0 and order.count('hide') == 3 and rep[0]['hidden'] == 2, '7b. hide-autoposts repeats until none are left', out)
    code, out, order, _, rep = run('hide-autoposts', {'hide': ['lost:Hide from Page']})
    check(code == 1 and 'Control not found: Hide from Page' in out and order[-1] == 'personal', '7c. missing menu item is named', out)

    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, 'spec.json').write_text(json.dumps({'pages': [PAGE]}))
        Path(tmp, 'posts.json').write_text(json.dumps({'posts': POSTS}))
        r = subprocess.run([sys.executable, str(SCRIPT), 'post', '--spec', f'{tmp}/spec.json', '--posts', f'{tmp}/posts.json'],
                           capture_output=True, text=True, env=dict(os.environ, FB_OWNER_NAME=OWNER))
        check(r.returncode == 1 and '--approved' in r.stderr, '8a. post without --approved is refused', r.stderr)
    code, out, order, _, _ = run('post', {}, posts=[{'page': 'example-sheds', 'text': 'Example Sheds'}])
    check(code == 1 and 'cannot be counted' in out and not order, '8b. a first line that repeats the Page name is refused', out)

    code, out, _, _, rep = run('verify', {'count': ['crash']})
    check(code == 1 and 'output withheld' in rep[0].get('error', ''), '9. browse crash withholds output', out)
    print(f'{len(failures)} failures')
    sys.exit(1 if failures else 0)

main()
