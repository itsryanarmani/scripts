#!/usr/bin/env python3
"""E2E for thumbnail-dataset against a fake YouTube API on 127.0.0.1.

The fake serves search, videos, channels, a token endpoint and thumbnails
(one id has no maxresdefault, so the hqdefault fallback runs). Checks: rows,
views_per_day, outlier (only for 1,000+ subscribers), a Short skipped, one id
found by two queries stored once with both queries, the token refresh path,
a rerun that calls no videos or channels endpoint again, --dry-run quota with
no network, and the usage and auth errors. It also covers: a quota 403 mid-run (exit 1, the work so far is saved), a failed thumbnail that a rerun retries, a live-stream duration (kept), a week duration, hidden subscribers, missing likes (null), a hostile video id (ignored), a title with comma, quote, newline and unicode, and a failed token refresh, the search cache after a quota stop, a repeated query, a partial videos failure (no row without subscribers; the rerun completes it), a malformed item, a deleted video, --no-images then a normal run, the 3-try cap on a failing thumbnail, and a cut-off jsonl line. Prints an evidence JSON line.
"""
import csv, datetime as dt, json, os, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

TOOL = str(Path(__file__).with_name('thumbnail-dataset'))
NOW = dt.datetime.now(dt.timezone.utc)
PUB = (NOW - dt.timedelta(days=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
VIDEOS = {
    'AAAAAAAAAAA': dict(title='Big one', ch='C1', dur='PT10M5S', views=1000000, likes=40000, comments=900),
    'BBBBBBBBBBB': dict(title='A short', ch='C1', dur='PT30S', views=5000, likes=10, comments=1),
    'CCCCCCCCCCC': dict(title='Small channel', ch='C2', dur='PT5M', views=5000, likes=100, comments=5),
}
VIDEOS.update({
    'DDDDDDDDDDD': dict(title='Hello, "\u4e16\u754c"\nline two', ch='C1', dur='PT7M', views=2000, likes=None, comments=None),
    'EEEEEEEEEEE': dict(title='Hidden subs', ch='C3', dur='PT9M', views=3000, likes=1, comments=1),
    'FFFFFFFFFFF': dict(title='Live stream', ch='C1', dur='P0D', views=4000, likes=1, comments=1),
    'GGGGGGGGGGG': dict(title='Week long', ch='C1', dur='P1W', views=6000, likes=1, comments=1),
})
CHANNELS = {'C1': 100000, 'C2': 500, 'C3': None}
SEARCH = {'q one': ['AAAAAAAAAAA', 'BBBBBBBBBBB'], 'q two': ['AAAAAAAAAAA', 'CCCCCCCCCCC'],
          'q three': ['DDDDDDDDDDD', 'EEEEEEEEEEE', 'FFFFFFFFFFF', 'GGGGGGGGGGG', '../../x']}
calls = {'videos': 0, 'channels': 0, 'token': 0, 'search': 0}
state = {'hq_fail': False, 'videos_fail': False}
SEARCH.update({'q many': ['MMMMMMMMM%02d' % i for i in range(60)], 'q gone': ['AAAAAAAAAAA', 'XXXXXXXXXXX'], 'q bad': ['HHHHHHHHHHH']})


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        if self.path.startswith('/badtoken'):
            return self.send(401, {'error': 'invalid_grant'})
        calls['token'] += 1
        self.send(200, {'access_token': 'fake-token'})

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path.startswith('/vi/'):
            vid, name = u.path.split('/')[2], u.path.split('/')[3]
            if name.startswith('maxresdefault') and vid == 'CCCCCCCCCCC':
                return self.send(404, b'no')
            if state['hq_fail'] and vid == 'CCCCCCCCCCC':
                return self.send(404, b'no')
            return self.send(200, b'\xff\xd8' + b'x' * 3000, 'image/jpeg')
        if self.headers.get('Authorization') != 'Bearer fake-token':
            return self.send(401, {'error': 'no token'})
        if u.path.endswith('/search'):
            calls['search'] += 1
            if q['q'] == 'q boom':
                return self.send(403, {'error': {'errors': [{'reason': 'quotaExceeded'}], 'message': 'The request cannot be completed because you have exceeded your quota.'}})
            return self.send(200, {'items': [{'id': {'videoId': v}} for v in SEARCH.get(q['q'], [])]})
        if u.path.endswith('/videos'):
            calls['videos'] += 1
            items = []
            ids = q['id'].split(',')
            if state['videos_fail'] and 'MMMMMMMMM59' in ids:
                return self.send(500, {'error': 'backend'})
            for v in ids:
                if v.startswith('MMMMMMMMM'):
                    d = dict(title='Many ' + v, ch='C1', dur='PT5M', views=1000, likes=1, comments=1)
                elif v == 'HHHHHHHHHHH':
                    items.append({'id': v, 'snippet': {'channelId': 'C1'}, 'statistics': {}, 'contentDetails': {'duration': 'PT5M'}})  # no title
                    continue
                elif v in VIDEOS:
                    d = VIDEOS[v]
                else:
                    continue  # deleted or private: the API omits it
                stats = {'viewCount': str(d['views'])}
                if d['likes'] is not None:
                    stats.update(likeCount=str(d['likes']), commentCount=str(d['comments']))
                items.append({'id': v, 'snippet': {'title': d['title'], 'channelId': d['ch'], 'channelTitle': d['ch'] + ' name',
                                                    'publishedAt': PUB},
                              'statistics': stats, 'contentDetails': {'duration': d['dur']}})
            return self.send(200, {'items': items})
        if u.path.endswith('/channels'):
            calls['channels'] += 1
            return self.send(200, {'items': [{'id': c, 'statistics': ({'subscriberCount': str(CHANNELS[c])} if CHANNELS[c] is not None else {'hiddenSubscriberCount': True})} for c in q['id'].split(',')]})
        self.send(404, {})


def main():
    srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%d' % srv.server_address[1]
    env = dict(os.environ, YOUTUBE_API_BASE=base + '/youtube/v3', YOUTUBE_TOKEN_URL=base + '/token', YOUTUBE_THUMB_BASE=base + '/vi',
               YOUTUBE_CLIENT_ID='id', YOUTUBE_CLIENT_SECRET='secret', YOUTUBE_REFRESH_TOKEN='refresh')
    for k in ('YOUTUBE_ACCESS_TOKEN',):
        env.pop(k, None)
    ev, fails = {}, []

    def check(name, cond, detail=''):
        ev[name] = bool(cond)
        if not cond:
            fails.append('%s %s' % (name, detail))

    def run(*args, e=None):
        return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=e or env)

    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, 'ds')
        r = run('--out', out, '--query', 'q one', '--query', 'q two', '--max', '10')
        rows = {x['id']: x for x in map(json.loads, open(os.path.join(out, 'dataset.jsonl')))} if os.path.exists(os.path.join(out, 'dataset.jsonl')) else {}
        check('run_ok', r.returncode == 0, r.stdout + r.stderr)
        check('token_refreshed', calls['token'] == 1, str(calls))
        check('short_skipped', 'BBBBBBBBBBB' not in rows and json.loads(r.stdout)['shorts_skipped'] == 1, r.stdout)
        a, c = rows.get('AAAAAAAAAAA', {}), rows.get('CCCCCCCCCCC', {})
        check('dedupe_two_queries', a.get('queries') == ['q one', 'q two'], str(a))
        check('views_per_day', abs(a.get('views_per_day', 0) - 100000) < 5000, str(a.get('views_per_day')))
        check('outlier_big_channel', a.get('outlier') == 10.0, str(a.get('outlier')))
        check('outlier_none_under_1000_subs', c.get('outlier') is None and c.get('subscribers') == 500, str(c))
        check('thumb_maxres', a.get('thumb') == 'maxresdefault' and os.path.getsize(os.path.join(out, 'thumbs', 'AAAAAAAAAAA.jpg')) > 2000)
        check('thumb_fallback_hq', c.get('thumb') == 'hqdefault')
        check('csv_written', len(list(csv.DictReader(open(os.path.join(out, 'dataset.csv'))))) == 2)
        before = dict(calls)
        r2 = run('--out', out, '--query', 'q one', '--query', 'q two', '--max', '10')
        check('rerun_no_refetch', r2.returncode == 0 and calls['videos'] == before['videos'] and calls['channels'] == before['channels'], str(calls))
        d = run('--out', out, '--query', 'x', '--dry-run', e={k: v for k, v in env.items() if not k.startswith('YOUTUBE_')})
        check('dry_run_quota_no_auth', d.returncode == 0 and json.loads(d.stdout)['estimated_quota_units'] == 102, d.stdout + d.stderr)
        noauth = {k: v for k, v in env.items() if not k.startswith('YOUTUBE_') or k.startswith('YOUTUBE_API') or k.startswith('YOUTUBE_TOKEN') or k.startswith('YOUTUBE_THUMB')}
        check('missing_auth_exit_2', run('--out', out, '--query', 'x', e=noauth).returncode == 2)
        check('no_query_exit_2', run('--out', out).returncode == 2)
        check('bad_date_exit_2', run('--out', out, '--query', 'x', '--published-after', 'yesterday').returncode == 2)
        check('bad_max_exit_2', run('--out', out, '--query', 'x', '--max', '99').returncode == 2)
        # quota error mid-run: exit 1, work so far saved
        qd = os.path.join(t, 'quota')
        r = run('--out', qd, '--query', 'q one', '--query', 'q boom', '--max', '10')
        qrows = [json.loads(x) for x in open(os.path.join(qd, 'dataset.jsonl'))] if os.path.exists(os.path.join(qd, 'dataset.jsonl')) else []
        check('quota_403_exit_1_partial_saved', r.returncode == 1 and [x['id'] for x in qrows] == ['AAAAAAAAAAA'], r.stdout + r.stderr)
        # a failed thumbnail is retried by a rerun, with no videos or channels call
        fd = os.path.join(t, 'retry')
        state['hq_fail'] = True
        r = run('--out', fd, '--query', 'q two', '--max', '10')
        check('failed_download_exit_1', r.returncode == 1 and 'CCCCCCCCCCC' in json.loads(r.stdout)['download_failed'], r.stdout)
        state['hq_fail'] = False
        before = dict(calls)
        r = run('--out', fd, '--query', 'q two', '--max', '10')
        row = {x['id']: x for x in map(json.loads, open(os.path.join(fd, 'dataset.jsonl')))}
        check('rerun_retries_thumbnail', r.returncode == 0 and row['CCCCCCCCCCC']['thumb'] == 'hqdefault' and calls['videos'] == before['videos'], r.stdout)
        # odd data
        od = os.path.join(t, 'odd')
        r = run('--out', od, '--query', 'q three', '--max', '10')
        orow = {x['id']: x for x in map(json.loads, open(os.path.join(od, 'dataset.jsonl')))}
        check('odd_run_ok', r.returncode == 0 and set(orow) == {'DDDDDDDDDDD', 'EEEEEEEEEEE', 'FFFFFFFFFFF', 'GGGGGGGGGGG'}, r.stdout + r.stderr)
        check('hostile_id_ignored', not os.path.exists(os.path.join(t, 'x.jpg')) and not any('..' in k for k in orow))
        check('hidden_subscribers_null', orow['EEEEEEEEEEE']['subscribers'] is None and orow['EEEEEEEEEEE']['outlier'] is None)
        check('missing_likes_null', orow['DDDDDDDDDDD']['likes'] is None and orow['DDDDDDDDDDD']['comments'] is None)
        check('live_duration_kept_as_null', orow['FFFFFFFFFFF']['duration_s'] is None)
        check('week_duration_parsed', orow['GGGGGGGGGGG']['duration_s'] == 604800)
        check('unicode_title_roundtrip', orow['DDDDDDDDDDD']['title'] == 'Hello, "\u4e16\u754c"\nline two'
              and [x for x in csv.DictReader(open(os.path.join(od, 'dataset.csv'), encoding='utf-8')) if x['id'] == 'DDDDDDDDDDD'][0]['title'] == 'Hello, "\u4e16\u754c"\nline two')
        # search cache: after the quota stop, a rerun repeats only the search that failed
        s0 = calls['search']
        r = run('--out', qd, '--query', 'q one', '--query', 'q boom', '--max', '10')
        check('search_cache_reused', r.returncode == 1 and calls['search'] - s0 == 1, str(calls))
        s0 = calls['search']
        run('--out', os.path.join(t, 'dup'), '--query', 'q one', '--query', ' q one ', '--max', '10')
        check('repeated_query_searched_once', calls['search'] - s0 == 1, str(calls))
        # partial videos failure: no row without subscribers, and a rerun completes it
        pd = os.path.join(t, 'partial')
        state['videos_fail'] = True
        r = run('--out', pd, '--query', 'q many', '--max', '50')
        prow = [json.loads(x) for x in open(os.path.join(pd, 'dataset.jsonl'))] if os.path.exists(os.path.join(pd, 'dataset.jsonl')) else []
        check('partial_failure_exit_2_rows_complete', r.returncode == 2 and len(prow) == 50 and all(x['subscribers'] == 100000 for x in prow), r.stdout + r.stderr)
        state['videos_fail'] = False
        v0 = calls['videos']
        r = run('--out', pd, '--query', 'q many', '--max', '50')
        check('partial_rerun_fetches_only_missing', r.returncode == 0 and calls['videos'] - v0 == 1 and len(open(os.path.join(pd, 'dataset.jsonl')).readlines()) == 60, r.stdout + calls.__repr__())
        # a malformed item and a deleted video
        gd = os.path.join(t, 'gone')
        r = run('--out', gd, '--query', 'q gone', '--query', 'q bad', '--max', '10')
        check('malformed_item_skipped_run_ok', r.returncode == 0 and json.loads(r.stdout)['malformed_items'] == 1 and json.loads(r.stdout)['total'] == 1, r.stdout)
        check('deleted_video_recorded', 'XXXXXXXXXXX' in open(os.path.join(gd, 'gone.txt')).read())
        v0 = calls['videos']
        run('--out', gd, '--query', 'q gone', '--query', 'q bad', '--max', '10')
        check('deleted_video_not_requested_again', calls['videos'] - v0 == 1, str(calls))
        # --no-images then a normal run
        nd = os.path.join(t, 'noimg')
        run('--out', nd, '--query', 'q one', '--max', '10', '--no-images')
        check('no_images_leaves_no_thumbs', not os.listdir(os.path.join(nd, 'thumbs')))
        r = run('--out', nd, '--query', 'q one', '--max', '10')
        check('later_run_downloads_thumbs', r.returncode == 0 and os.path.exists(os.path.join(nd, 'thumbs', 'AAAAAAAAAAA.jpg')), r.stdout)
        # a thumbnail that keeps failing is tried 3 times in all
        td = os.path.join(t, 'tries')
        state['hq_fail'] = True
        for _ in range(5):
            run('--out', td, '--query', 'q two', '--max', '10')
        trow = {x['id']: x for x in map(json.loads, open(os.path.join(td, 'dataset.jsonl')))}
        check('failed_thumb_capped_at_3_tries', trow['CCCCCCCCCCC']['thumb_tries'] == 3, str(trow['CCCCCCCCCCC']))
        state['hq_fail'] = False
        # a line cut short by an earlier kill does not stop the run
        with open(os.path.join(nd, 'dataset.jsonl'), 'a') as f:
            f.write('{"id": "brok')
        check('cut_jsonl_line_tolerated', run('--out', nd, '--query', 'q one', '--max', '10').returncode == 0)
        badtok = dict(env, YOUTUBE_TOKEN_URL=base + '/badtoken')
        check('failed_token_refresh_exit_2', run('--out', os.path.join(t, 'bt'), '--query', 'q one', e=badtok).returncode == 2)
    print(json.dumps({'evidence': ev, 'failures': fails}))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
