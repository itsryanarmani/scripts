#!/usr/bin/env python3
"""E2E for address-verify against a local fake PostGrid server.

Covers: dry run (no network, counts lookups), refusal without --yes, refusal without a
key, verified / corrected / failed answers with the canonical line, the note in
brackets cut from the input, a sheet JSON with a header row and an empty cell,
an HTTP 500 (row marked error, run continues), and an HTTP 403 (run stops, exit 1).
The TEST key is refused, a bracket inside an address is kept, and a refused connection marks
the row error. A control proves the test can fail: the fake server counts hits, and the dry run must
leave the count at zero. Prints one evidence JSON line.
"""
import json, os, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TOOL = str(Path(__file__).parent / 'address-verify')
HITS = []


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        a = json.loads(self.rfile.read(int(self.headers['Content-Length'])))['address']
        HITS.append((a, self.headers.get('User-Agent'), self.headers.get('x-api-key')))
        if 'EXPLODE' in a:
            return self._send(500, {})
        if 'FORBID' in a:
            return self._send(403, {})
        st = 'failed' if 'NOWHERE' in a else 'corrected' if 'Pkwy' in a else 'verified'
        d = {'status': st, 'line1': a.upper().split(',')[0], 'city': 'TOWN', 'provinceOrState': 'CA',
             'postalOrZip': '94043', 'errors': {'generic': ['no match']} if st == 'failed' else {}}
        self._send(200, {'data': d})

    def _send(self, code, body):
        b = json.dumps(body).encode()
        self.send_response(code); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def log_message(self, *a):
        pass


def run(*args, key='k'):
    env = {k: v for k, v in os.environ.items() if not k.startswith('POSTGRID')}
    if key:
        env['POSTGRID_ADDVER_LIVE_API_KEY'] = key
    p = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=env)
    return p.returncode, p.stdout, p.stderr


def main():
    srv = HTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{srv.server_port}/v'
    d = Path(tempfile.mkdtemp())
    f = d / 'a.txt'
    f.write_text('# comment\n1 Main St, Town (HQ; role is remote)\n\n9 Hidden Rd, NOWHERE\n1600 Amphitheatre Pkwy, Town\n')

    rc, out, err = run('--file', str(f), '--dry-run')
    assert rc == 0 and '3 lookups' in err and not HITS, (rc, err, HITS)          # control: no network call
    rc, out, err = run('--file', str(f), '--url', url)
    assert rc == 2 and 'add --yes' in err and not HITS
    rc, out, err = run('--file', str(f), '--yes', '--url', url, key='')
    assert rc == 2 and 'POSTGRID_ADDVER_LIVE_API_KEY' in err and not HITS

    rc, out, err = run('--file', str(f), '--yes', '--url', url)
    rows = [json.loads(l) for l in out.splitlines()]
    assert rc == 0 and [r['status'] for r in rows] == ['verified', 'failed', 'corrected'], out
    assert rows[0]['input'] == '1 Main St, Town' and rows[0]['canonical'] == '1 MAIN ST TOWN CA 94043'
    assert rows[1]['canonical'] is None and rows[1]['errors']
    assert HITS[0][1] == 'address-verify/1.0' and HITS[0][2] == 'k'

    sheet = d / 's.json'
    sheet.write_text(json.dumps({'values': [['Company', 'Address 1'], ['A', '1 Main St, Town'], ['B', ''], ['C', '2 EXPLODE St']]}))
    rc, out, err = run('--sheet-json', str(sheet), '--column', '1', '--header', '--yes', '--url', url)
    st = [json.loads(l)['status'] for l in out.splitlines()]
    assert rc == 0 and st == ['verified', 'error', 'error'], (rc, out)

    # the TEST key is refused; a bracket inside the address is kept; bad input is exit 2
    rc, out, err = run('--file', str(f), '--yes', '--url', url, key='test_sk_abc')
    assert rc == 2 and 'live key' in err
    f3 = d / 'c.txt'
    f3.write_text('Suite 200 (Rear Bldg), 100 Main St, Springfield IL 62701\n3 Oak St, Town 94043 (HQ (old); remote)\n'
                  'PO Box 12345 (Station A) Toronto ON M5V 2T6\n10200 (Unit 5) 102 Ave NW, Edmonton AB T5J 0K2\n')
    n = len(HITS)
    rc, out, err = run('--file', str(f3), '--yes', '--url', url)
    assert rc == 0 and [h[0] for h in HITS[n:]] == ['Suite 200 (Rear Bldg), 100 Main St, Springfield IL 62701', '3 Oak St, Town 94043',
                                                  'PO Box 12345 (Station A) Toronto ON M5V 2T6', '10200 (Unit 5) 102 Ave NW, Edmonton AB T5J 0K2'], HITS[n:]
    rc, out, err = run('--file', str(d / 'nope.txt'), '--yes', '--url', url)
    assert rc == 2 and 'cannot read the input' in err
    rc, out, err = run('--sheet-json', str(f), '--yes', '--url', url)                 # a text file is not JSON
    assert rc == 2
    rc, out, err = run('--file', str(f3), '--yes', '--url', 'http://127.0.0.1:9/none')   # nothing listens: rows error, run finishes
    assert rc == 0 and [json.loads(l)['status'] for l in out.splitlines()] == ['error'] * 4, out

    rc, out, err = run('--file', str(f3), '--yes', '--url', url, '--out', str(d / 'no-dir' / 'o.json'))   # a failed --out write
    assert rc == 2 and 'could not write' in err

    rc, out, err = run('--sheet-json', str(sheet), '--column', '7', '--yes', '--url', url)   # wrong column: no paid call
    assert rc == 2 and 'is --column right' in err

    f2 = d / 'b.txt'
    f2.write_text('1 FORBID St\n2 Main St\n')
    n = len(HITS)
    rc, out, err = run('--file', str(f2), '--yes', '--url', url)
    assert rc == 1 and len(out.splitlines()) == 1 and len(HITS) == n + 1, (rc, out)   # stopped after the 403
    print(json.dumps({'test': 'address-verify', 'ok': True, 'hits': len(HITS)}))


if __name__ == '__main__':
    main()
