#!/usr/bin/env python3
"""E2E for youtube-thumbnail-set against a local fake YouTube API.

Covers: dry run (no network, checks files), refusal without --yes, a missing image
(exit 2 before any upload), --only, two good uploads with the right bytes and
header, a 500 on one video (the run goes on, exit 1), and a 403 (the run stops).
A control: the dry run must leave the fake server's hit list empty.
A typo in --only, a duplicate id and an image over 2 MB exit 2 before any upload.
Prints one evidence JSON line.
"""
import json, os, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TOOL = str(Path(__file__).parent / 'youtube-thumbnail-set')
HITS = []


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        vid = self.path.split('videoId=')[1]
        HITS.append((vid, body, self.headers.get('Authorization'), self.headers.get('Content-Type')))
        code = 500 if vid == 'bad500' else 403 if vid == 'bad403' else 200
        b = json.dumps({'items': [{'default': {'url': 'http://x/' + vid}}]}).encode()
        self.send_response(code); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def log_message(self, *a):
        pass


def run(*args):
    env = {**os.environ, 'YOUTUBE_ACCESS_TOKEN': 'tok'}
    p = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=env)
    return p.returncode, p.stdout, p.stderr


def main():
    srv = HTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_port}'
    d = Path(tempfile.mkdtemp())
    ids = ['aaa', 'bad500', 'bbb', 'bad403', 'ccc']
    for i, v in enumerate(ids, 1):
        (d / f'{i:02d}-{v}.jpg').write_bytes(b'\xff\xd8jpeg-' + v.encode())
    m = d / 'map.json'
    m.write_text(json.dumps([{'item': i, 'video': v} for i, v in enumerate(ids, 1)]))
    only = lambda *v: ['--only', *v]

    rc, out, err = run('--map', str(m), '--dir', str(d), '--dry-run')
    assert rc == 0 and len(out.splitlines()) == 5 and not HITS            # control: no network call
    rc, out, err = run('--map', str(m), '--dir', str(d), '--api-base', base)
    assert rc == 2 and 'add --yes' in err and not HITS
    (d / '03-bbb.jpg').rename(d / 'x.tmp')
    rc, out, err = run('--map', str(m), '--dir', str(d), '--yes', '--api-base', base)
    assert rc == 2 and 'missing image' in err and not HITS
    (d / 'x.tmp').rename(d / '03-bbb.jpg')

    rc, out, err = run('--map', str(m), '--dir', str(d), '--yes', '--api-base', base, *only('typo'))
    assert rc == 2 and 'not in the map' in err and not HITS
    rc, out, err = run('--map', str(m), '--dir', str(d), '--yes', '--api-base', base + '/', *only('aaa', 'bbb'))   # trailing slash
    rows = [json.loads(l) for l in out.splitlines()]
    assert rc == 0 and all(r['ok'] for r in rows) and len(rows) == 2, out
    assert HITS[0] == ('aaa', b'\xff\xd8jpeg-aaa', 'Bearer tok', 'image/jpeg'), HITS[0]

    HITS.clear()
    rc, out, err = run('--map', str(m), '--dir', str(d), '--yes', '--api-base', base)
    rows = [json.loads(l) for l in out.splitlines()]
    assert rc == 1 and [r['video'] for r in rows] == ['aaa', 'bad500', 'bbb', 'bad403'], out   # ccc never sent
    assert [r['ok'] for r in rows] == [True, False, True, False] and len(HITS) == 4
    (d / '05-ccc.jpg').write_bytes(b'x' * 2_000_001)
    rc, out, err = run('--map', str(m), '--dir', str(d), '--dry-run')
    assert rc == 2 and 'over 2 MB' in err
    (d / 'dup.json').write_text(json.dumps([{'item': 1, 'video': 'aaa'}, {'item': 2, 'video': 'aaa'}]))
    rc, out, err = run('--map', str(d / 'dup.json'), '--dir', str(d), '--dry-run')
    assert rc == 2 and 'twice' in err
    print(json.dumps({'test': 'youtube-thumbnail-set', 'ok': True, 'uploads': len(HITS)}))


if __name__ == '__main__':
    main()
