#!/usr/bin/env python3
"""E2E for thumbnail-export and thumbnail-poses.

Builds a fixture gallery (a page that draws one 1280x720 box from the hash),
runs the real export with headless Chrome, and asserts two PNG files of
1280x720 under 2 MB. Then covers the failure rows: item out of range, bad
layout list, a gallery without config, a missing Chrome, and an oversized
limit forcing a failure. For thumbnail-poses it checks the dry run (25 tags,
cost, no network) and the guards (no --yes, no ref, unknown tag). Prints an
evidence JSON line. SKIPs the export part when no Chrome is installed.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
EXPORT, POSES = str(HERE / 'thumbnail-export'), str(HERE / 'thumbnail-poses')
PAGE = """<!doctype html><body style="margin:0"><div id=b style="width:1280px;height:720px;
font:80px Arial;background:#2447ff;color:#fff;padding:40px;box-sizing:border-box"></div>
<script>const h=new URLSearchParams(location.hash.slice(1));
b.textContent='item '+h.get('i')+' layout '+h.get('l')+' pose '+h.get('pose')</script></body>"""
evidence, fails = {}, []


def run(*cmd):
    return subprocess.run(list(cmd), capture_output=True, text=True)


def check(name, cond, detail=''):
    evidence[name] = bool(cond)
    if not cond:
        fails.append('%s %s' % (name, detail))


def main():
    p = run(sys.executable, POSES, '--dry-run', '--out', '/nonexistent')
    last = json.loads(p.stdout.strip().splitlines()[-1])
    check('poses_dry_run_lists_25', p.returncode == 0 and len(last['would_make']) == 25, p.stderr)
    check('poses_dry_run_cost', last['estimated_cost_usd'] == 1.75, str(last))
    check('poses_needs_ref', run(sys.executable, POSES, '--out', '/tmp/x', '--yes').returncode == 2)
    with tempfile.TemporaryDirectory() as t:
        ref = os.path.join(t, 'r.jpg')
        open(ref, 'wb').write(b'x')
        check('poses_needs_yes', run(sys.executable, POSES, '--ref', ref, '--out', t).returncode == 2)
        check('poses_unknown_tag', run(sys.executable, POSES, '--ref', ref, '--out', t, '--tags', 'nope', '--yes').returncode == 2)
        chrome = next((c for c in ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', 'google-chrome', 'chromium']
                       if os.path.isfile(c) or shutil.which(c)), None)
        if not chrome:
            print('SKIP export: no Chrome')
        else:
            g = os.path.join(t, 'gal')
            os.makedirs(g)
            open(os.path.join(g, 'index.html'), 'w').write(PAGE)
            json.dump({'items': [{'title': 'Acme Co'}, {'title': 'Beta'}]}, open(os.path.join(g, 'config.json'), 'w'))
            out = os.path.join(t, 'out')
            r = run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--item', '1', '--layout', '1,2', '--pose', 'sad')
            rows = [json.loads(x) for x in r.stdout.splitlines()]
            check('export_ok', r.returncode == 0 and len(rows) == 2 and all(x['ok'] for x in rows), r.stdout + r.stderr)
            check('export_names', sorted(os.path.basename(x['file']) for x in rows) == ['acme-co-L1.png', 'acme-co-L2.png'])
            check('export_under_2mb', all(x['bytes'] < 2000000 for x in rows))
            r = run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--item', '1', '--layout', '1', '--max-bytes', '10')
            check('export_over_limit_fails', r.returncode == 1 and '"ok": false' in r.stdout, r.stdout)
            check('export_bad_item', run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--item', '9', '--layout', '1').returncode == 2)
            check('export_bad_layout', run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--layout', 'x').returncode == 2)
            check('export_no_config', run(sys.executable, EXPORT, '--gallery', t, '--out', out, '--layout', '1').returncode == 2)
            check('export_no_chrome', run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--layout', '1', '--chrome', '/nope').returncode == 2)
    print(json.dumps({'evidence': evidence, 'failures': fails}))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
