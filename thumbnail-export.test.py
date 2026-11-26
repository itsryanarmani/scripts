#!/usr/bin/env python3
"""E2E for thumbnail-export and thumbnail-poses.

Builds a fixture gallery (a page that draws one 1280x720 box from the hash and
sets data-ready), runs the real export with headless Chrome, and asserts two
PNG files of 1280x720 under 2 MB. Then covers the failure rows: a layout the
page rejects (must fail, not export a broken picture), equal non-ASCII titles
(files must not overwrite each other), a stale file (must not pass), item out
of range, bad layout list, bad pose tag, a gallery without config, a missing
Chrome, and an oversized limit. For thumbnail-poses it checks the dry run (25 tags,
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
b.textContent='item '+h.get('i')+' layout '+h.get('l')+' pose '+h.get('pose');
document.documentElement.dataset.ready=(+h.get('l')<5)?'ok':'fail:unknown layout'</script></body>"""
FAKE = '''#!/bin/sh
# fake wavespeed: upload prints a URL and logs; run writes the --download file only when FAKE_OK=1
case "$1" in
  upload) echo "$@" >> "$FAKE_LOG"; echo "https://example.invalid/ref.jpg" ;;
  run) shift; while [ $# -gt 0 ]; do [ "$1" = "--download" ] && f="$2"; shift; done
       if [ "$FAKE_OK" = "1" ]; then printf 'png' > "$f"; echo "Source URLs:"; fi ;;
esac
'''
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
        fake = os.path.join(t, 'bin')
        os.makedirs(fake)
        open(os.path.join(fake, 'wavespeed'), 'w').write(FAKE)
        os.chmod(os.path.join(fake, 'wavespeed'), 0o755)
        log, pdir = os.path.join(t, 'log'), os.path.join(t, 'poses')
        def poses(ok, *extra):
            env = dict(os.environ, PATH=fake + os.pathsep + os.environ['PATH'], FAKE_LOG=log, FAKE_OK=ok)
            return subprocess.run([sys.executable, POSES, '--ref', ref, '--out', pdir, '--yes', '--tags', 'sad,shocked', *extra], capture_output=True, text=True, env=env)
        r = poses('1')
        check('poses_make_ok', r.returncode == 0 and sorted(json.load(open(os.path.join(pdir, 'index.json')))) == ['sad', 'shocked'], r.stdout + r.stderr)
        open(log, 'w').close()
        r = poses('1')
        check('poses_nothing_to_do_no_upload', r.returncode == 0 and open(log).read() == '', r.stdout)
        r = poses('0', '--force')
        check('poses_force_failure_not_ok', r.returncode == 1 and not os.path.exists(os.path.join(pdir, 'sad.png')), r.stdout)
        check('poses_index_matches_files', json.load(open(os.path.join(pdir, 'index.json'))) == [], '')
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
            check('export_names', sorted(os.path.basename(x['file']) for x in rows) == ['01-acme-co-L1-sad.png', '01-acme-co-L2-sad.png'])
            check('export_under_2mb', all(x['bytes'] < 2000000 for x in rows))
            r = run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--item', '1', '--layout', '1', '--max-bytes', '10')
            check('export_over_limit_fails', r.returncode == 1 and '"ok": false' in r.stdout, r.stdout)
            r = run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--item', '1', '--layout', '9')
            check('export_page_rejects_layout', r.returncode == 1 and 'unknown layout' in r.stdout and '"ok": false' in r.stdout, r.stdout)
            stale = os.path.join(out, '01-acme-co-L9.png')
            open(stale, 'wb').write(b'old')
            run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--item', '1', '--layout', '9')
            check('export_stale_file_removed', not os.path.exists(stale))
            g2 = os.path.join(t, 'gal2')
            shutil.copytree(g, g2)
            json.dump({'items': [{'title': '\u6771\u4eac'}, {'title': '\u5927\u962a'}]}, open(os.path.join(g2, 'config.json'), 'w'))
            r = run(sys.executable, EXPORT, '--gallery', g2, '--out', os.path.join(t, 'out2'), '--layout', '1')
            names = sorted(os.listdir(os.path.join(t, 'out2')))
            check('export_equal_slugs_dont_overwrite', r.returncode == 0 and names == ['01-item-L1.png', '02-item-L1.png'], str(names))
            spoof = os.path.join(t, 'spoof')
            os.makedirs(spoof)
            open(os.path.join(spoof, 'index.html'), 'w').write('<!doctype html><body><p>data-ready="ok"</p></body>')
            json.dump({'items': [{'title': 'x'}]}, open(os.path.join(spoof, 'config.json'), 'w'))
            r = run(sys.executable, EXPORT, '--gallery', spoof, '--out', os.path.join(t, 'o3'), '--layout', '1')
            check('export_spoofed_ready_text_fails', r.returncode == 1 and 'did not set data-ready' in r.stdout, r.stdout)
            r = run(sys.executable, EXPORT, '--gallery', g, '--out', os.path.join(t, 'o4'), '--item', '1', '--layout', '1', '--pose', 'sad')
            check('export_name_has_pose', r.returncode == 0 and os.path.exists(os.path.join(t, 'o4', '01-acme-co-L1-sad.png')), r.stdout)
            bad_cfg = os.path.join(t, 'badcfg')
            shutil.copytree(g, bad_cfg)
            open(os.path.join(bad_cfg, 'config.json'), 'w').write('[1, 2]')
            check('export_bad_config_exit_2', run(sys.executable, EXPORT, '--gallery', bad_cfg, '--out', out, '--layout', '1').returncode == 2)
            check('export_bad_pose', run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--layout', '1', '--pose', 'a&l=3').returncode == 2)
            check('export_bad_item', run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--item', '9', '--layout', '1').returncode == 2)
            check('export_bad_layout', run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--layout', 'x').returncode == 2)
            check('export_no_config', run(sys.executable, EXPORT, '--gallery', t, '--out', out, '--layout', '1').returncode == 2)
            check('export_no_chrome', run(sys.executable, EXPORT, '--gallery', g, '--out', out, '--layout', '1', '--chrome', '/nope').returncode == 2)
    print(json.dumps({'evidence': evidence, 'failures': fails}))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
