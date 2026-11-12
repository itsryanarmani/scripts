#!/usr/bin/env python3
"""CLI E2E: real script, real images, fake `browse` on PATH. No Facebook account is touched.

Failure modes, written before the code:
  1. A bio over 101 characters: refused before any image or browser work.
  2. A logo path that does not exist: assets stops and names the file.
  3. Pillow missing: assets stops and says what to install.
  4. A Page with no link: apply refuses the spec.
  5. A control not found: the step fails with the control name, and the run still switches back.
  6. The session stays a Page after switch-back: the run fails and says so.
  7. browse crashes and prints a secret: the secret never reaches the output.
Success cases: assets writes a 1024x1024 profile and a 1640x720 cover; apply runs the steps in
order with switch-back first and last; parts that already have a value are skipped; the owner
name and tokens never reach the output.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SCRIPT = Path(__file__).with_name('fb-page-polish')
SECRET = 'EAAB-fake-secret-token'
OWNER = 'Alex Example Owner'
FAKE_BROWSE = r'''#!/usr/bin/env python3
import json, os, re, sys
code = open(sys.argv[sys.argv.index('--file') + 1]).read()
step = re.search(r'// step: (\w+)', code).group(1)
with open(os.environ['FAKE_LOG'], 'a') as log:
    log.write(json.dumps({'step': step, 'args': sys.argv[1:4], 'code': code}) + '\n')
mode = os.environ['FAKE_MODE']
if mode == 'crash':
    print('cookie=' + os.environ['FAKE_SECRET']); sys.exit(1)
if mode == 'nocontrol' and step == 'cover':
    print(json.dumps({'ok': False, 'error': {'message': 'Error: Control not found: Add cover photo token=x',
                                             'stack': 'token=' + os.environ['FAKE_SECRET']}})); sys.exit(1)
value = {'personal': {'state': 'page' if mode == 'stuck' else 'personal'}, 'switch': {'switched': True},
         'profile': {'profile': 'uploaded'}}.get(step, {step: 'already set' if mode == 'set' else 'saved'})
print(json.dumps({'ok': True, 'value': value, 'logs': []}))
'''
LOGO = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="120"><rect width="200" height="120" fill="#f4e9d8"/></svg>'
PAGE = {'name': 'Example Sheds', 'about': 'Sturdy backyard sheds, built to order and delivered.',
        'website': 'https://example.test', 'logo': 'logo.svg', 'color': '#2f5d50',
        'link': 'https://www.facebook.com/profile.php?id=1'}
failures = []

def check(cond, label, detail=''):
    print(('ok   ' if cond else 'FAIL ') + label + ('' if cond else '\n     ' + detail[-600:]))
    failures.extend([] if cond else [label])

def setup(tmp, pages):
    Path(tmp, 'logo.svg').write_text(LOGO)
    Path(tmp, 'spec.json').write_text(json.dumps({'pages': pages}))
    Path(tmp, 'bin').mkdir(exist_ok=True)
    Path(tmp, 'bin/browse').write_text(FAKE_BROWSE)
    Path(tmp, 'bin/browse').chmod(0o755)

def run(tmp, args, mode='ok', python=(sys.executable,)):
    env = dict(os.environ, PATH=f'{tmp}/bin:{os.environ["PATH"]}', FAKE_MODE=mode, FAKE_SECRET=SECRET,
               FAKE_LOG=str(Path(tmp) / 'log.jsonl'), FB_OWNER_NAME=OWNER)
    cmd = [*python, str(SCRIPT), args[0], '--spec', f'{tmp}/spec.json', '--assets-dir', f'{tmp}/out', *args[1:]]
    Path(tmp, 'log.jsonl').unlink(missing_ok=True)
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    out = result.stdout + result.stderr
    check(SECRET not in out and OWNER not in out, f'no secret or owner name in output ({args[0]} {mode})', out)
    return result, out

def steps(tmp):
    return [json.loads(l) for l in Path(tmp, 'log.jsonl').read_text().splitlines()] if Path(tmp, 'log.jsonl').exists() else []

def main():
    stage = tempfile.mkdtemp(prefix='fbpp-test-', dir='/tmp')
    apply_args = ['apply', '--stage-dir', stage, '--session', 'test-session']
    try:
        no_link = {k: v for k, v in PAGE.items() if k != 'link'}
        for label, page, args, python, expect in (
                ('1. bio over 101 characters refused', dict(PAGE, about='x' * 102), ['assets'], (), 'Facebook allows 101'),
                ('2. missing logo named', dict(PAGE, logo='missing.svg'), ['assets'], (), 'logo not found: missing.svg'),
                ('3. missing Pillow says what to install', PAGE, ['assets'], ('-S',), 'pip install Pillow'),  # -S: no site-packages
                ('4. Page link missing refused', no_link, apply_args, (), 'missing "link"')):
            with tempfile.TemporaryDirectory() as tmp:
                setup(tmp, [page])
                r, out = run(tmp, args, python=(sys.executable, *python))
                check(r.returncode == 1 and expect in out and not steps(tmp), label, out)
        with tempfile.TemporaryDirectory() as tmp:
            setup(tmp, [PAGE])
            r, out = run(tmp, ['assets'])
            check(r.returncode == 0, 'assets runs for real', out)
            from PIL import Image
            sizes = [Image.open(Path(tmp) / 'out/example-sheds' / n).size for n in ('profile.png', 'cover.png')]
            check(sizes == [(1024, 1024), (1640, 720)], f'image sizes {sizes}')
            r, out = run(tmp, apply_args)
            order = [s['step'] for s in steps(tmp)]
            check(r.returncode == 0, 'apply succeeds', out)
            check(order == ['personal', 'switch', 'cover', 'profile', 'bio', 'website', 'personal'],
                  f'step order {order}')
            first = steps(tmp)[0]
            check(first['args'] == ['execute', '-s', 'test-session'] and OWNER in first['code'], 'owner name sent to browse only')
            check(f'{stage}/example-sheds/cover.png' in steps(tmp)[2]['code'], 'cover staged under /tmp')
            report = json.loads(out.splitlines()[0])
            check(report.get('cover') == 'saved' and report.get('back') == 'personal profile', 'report says saved')
            r, out = run(tmp, apply_args, mode='set')
            report = json.loads(r.stdout.splitlines()[0])
            check(r.returncode == 0 and [report[k] for k in ('cover', 'bio', 'website')] == ['already set'] * 3,
                  'parts that have a value are skipped', out)
            r, out = run(tmp, apply_args, mode='nocontrol')
            order = [s['step'] for s in steps(tmp)]
            check(r.returncode == 1 and 'Control not found: Add cover photo' in out and 'token=x' not in out and order[-1] == 'personal',
                  '5. control not found is named and the run switches back', out)
            r, out = run(tmp, apply_args, mode='stuck')
            check(r.returncode == 1 and 'session still acts as a Page' in out, '6. session left as a Page fails', out)
            r, out = run(tmp, apply_args, mode='crash')
            check(r.returncode == 1 and 'output withheld' in out, '7. browse crash withholds output', out)
            r, out = run(tmp, ['apply', '--stage-dir', str(SCRIPT.parent)])  # the repo is never under /tmp
            check(r.returncode == 1 and 'under /tmp' in out, 'stage dir outside /tmp refused', out)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    print(f'{len(failures)} failures')
    sys.exit(1 if failures else 0)

main()
