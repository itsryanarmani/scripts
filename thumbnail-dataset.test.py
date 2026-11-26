#!/usr/bin/env python3
"""E2E for thumbnail-dataset against a fake YouTube API on 127.0.0.1 (no quota).

Covers rows, outlier, Shorts, thumbnail fallback and retry, dedupe, token refresh,
reruns, the search cache, quota stop, partial failure, malformed, null and deleted
items, odd durations, a hostile id, unicode, --no-images. Prints evidence JSON.
"""
import csv, datetime as dt, json, os, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

TOOL = str(Path(__file__).with_name('thumbnail-dataset'))
PUB = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
V = lambda ch, dur, views, likes=1, title='t': dict(title=title, ch=ch, dur=dur, views=views, likes=likes)
TITLE = 'Hello, "世界"\nline two'
VIDEOS = {'AAAAAAAAAAA': V('C1', 'PT10M5S', 1000000), 'BBBBBBBBBBB': V('C1', 'PT30S', 5000), 'CCCCCCCCCCC': V('C2', 'PT5M', 5000),
          'DDDDDDDDDDD': V('C1', 'PT7M', 2000, None, TITLE), 'EEEEEEEEEEE': V('C3', 'PT9M', 3000), 'FFFFFFFFFFF': V('C1', 'P0D', 4000),
          'GGGGGGGGGGG': V('C1', 'P1W', 6000), 'JJJJJJJJJJJ': V('C1', 'PT5M', 0, None)}
CHANNELS = {'C1': 100000, 'C2': 500, 'C3': None}  # None = hidden
MANY = ['MMMMMMMMM%02d' % i for i in range(60)]
SEARCH = {'q one': ['AAAAAAAAAAA', 'BBBBBBBBBBB'], 'q two': ['AAAAAAAAAAA', 'CCCCCCCCCCC'], 'q many': MANY, 'q bad': ['HHHHHHHHHHH'],
          'q three': ['DDDDDDDDDDD', 'EEEEEEEEEEE', 'FFFFFFFFFFF', 'GGGGGGGGGGG', '../../x'], 'q gone': ['XXXXXXXXXXX']}
calls, asked, state = dict(videos=0, channels=0, token=0, search=0), [], dict(hq_fail=False, videos_fail=False, odd=False)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype='application/json'):
        self.send_response(code); self.send_header('Content-Type', ctype); self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        if self.path.startswith('/badtoken'):
            return self.send(401, {'error': 'invalid_grant'})
        calls['token'] += 1
        self.send(200, {'access_token': 'fake-token'})

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path.startswith('/vi/'):
            vid, name = u.path.split('/')[2:4]
            if vid == 'CCCCCCCCCCC' and (name.startswith('maxres') or state['hq_fail']):
                return self.send(404, b'no')
            return self.send(200, b'\xff\xd8' + b'x' * 3000, 'image/jpeg')
        if self.headers.get('Authorization') != 'Bearer fake-token':
            return self.send(401, {'error': 'no token'})
        if u.path.endswith('/search'):
            calls['search'] += 1
            if q['q'] == 'q boom':
                return self.send(403, {'error': {'errors': [{'reason': 'quotaExceeded'}], 'message': 'exceeded your quota'}})
            items = [{'id': {'videoId': v}} for v in SEARCH.get(q['q'], [])]
            return self.send(200, {'items': items + ([None, {'id': 'str'}, {'id': {'videoId': 'AAAAAAAAAAA'}}] if q['q'] == 'q odd' else [])})
        if u.path.endswith('/videos'):
            calls['videos'] += 1
            ids, items = q['id'].split(','), []
            asked.extend(ids)
            if state['videos_fail'] and 'MMMMMMMMM59' in ids:
                return self.send(500, {'error': 'backend'})
            for v in ids:
                d = V('C1', 'PT5M', 1000) if v.startswith('MMMMMMMMM') else VIDEOS.get(v)
                if v == 'HHHHHHHHHHH':  # malformed: no title
                    items.append({'id': v, 'snippet': {'channelId': 'C1'}, 'statistics': {}, 'contentDetails': {'duration': 'PT5M'}})
                elif d:  # a deleted video is simply omitted
                    st = {'viewCount': str(d['views'])} if d['likes'] is not None or v != 'JJJJJJJJJJJ' else None
                    if st and d['likes'] is not None:
                        st.update(likeCount='1', commentCount='1')
                    items.append({'id': v, 'snippet': {'title': d['title'], 'channelId': d['ch'], 'channelTitle': d['ch'], 'publishedAt': PUB},
                                  'statistics': st, 'contentDetails': {'duration': d['dur']}})
            return self.send(200, {'items': items})
        if u.path.endswith('/channels'):
            calls['channels'] += 1
            ch = [{'id': c, 'statistics': {'subscriberCount': str(CHANNELS[c])} if CHANNELS[c] is not None else {'hiddenSubscriberCount': True}} for c in q['id'].split(',')]
            return self.send(200, {'items': ch + [{'statistics': {}}, None]})
        self.send(404, {})

def main():
    srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%d' % srv.server_address[1]
    env = {k: v for k, v in os.environ.items() if not k.startswith('YOUTUBE_')}
    env.update(YOUTUBE_API_BASE=base + '/youtube/v3', YOUTUBE_TOKEN_URL=base + '/token', YOUTUBE_THUMB_BASE=base + '/vi')
    auth = dict(YOUTUBE_CLIENT_ID='id', YOUTUBE_CLIENT_SECRET='secret', YOUTUBE_REFRESH_TOKEN='refresh')
    ev, fails = {}, []

    def check(name, cond, detail=''):
        ev[name] = bool(cond)
        if not cond:
            fails.append('%s %s' % (name, detail))

    def run(*args, e=None):
        return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=dict(e or env, **({} if e else auth)))

    def rows(d):
        p = os.path.join(d, 'dataset.jsonl')
        return {x['id']: x for x in map(json.loads, open(p))} if os.path.exists(p) else {}

    with tempfile.TemporaryDirectory() as t:
        P = lambda n: os.path.join(t, n)
        r = run('--out', P('ds'), '--query', 'q one', '--query', 'q two', '--max', '10')
        rw = rows(P('ds')); a, c = rw.get('AAAAAAAAAAA', {}), rw.get('CCCCCCCCCCC', {})
        check('run_ok_token_refreshed_once', r.returncode == 0 and calls['token'] == 1, r.stdout + r.stderr + str(calls))
        check('short_skipped', 'BBBBBBBBBBB' not in rw and json.loads(r.stdout)['shorts_skipped'] == 1, r.stdout)
        check('dedupe_two_queries', a.get('queries') == ['q one', 'q two'], str(a))
        check('views_per_day_and_outlier', abs(a.get('views_per_day', 0) - 100000) < 5000 and a.get('outlier') == 10.0, str(a))
        check('outlier_none_under_1000_subs', c.get('outlier') is None and c.get('subscribers') == 500, str(c))
        check('thumb_maxres_and_hq_fallback', a.get('thumb') == 'maxresdefault' and os.path.getsize(P('ds/thumbs/AAAAAAAAAAA.jpg')) > 2000 and c.get('thumb') == 'hqdefault')
        check('csv_written', len(list(csv.DictReader(open(P('ds/dataset.csv'))))) == 2)
        before = dict(calls)
        r2 = run('--out', P('ds'), '--query', 'q one', '--query', 'q two', '--max', '10')
        check('rerun_no_refetch', r2.returncode == 0 and calls['videos'] == before['videos'] and calls['channels'] == before['channels'], str(calls))
        d = run('--out', P('ds'), '--query', 'x', '--dry-run', e=dict(env))
        check('dry_run_quota_no_auth', d.returncode == 0 and json.loads(d.stdout)['estimated_quota_units'] == 102, d.stdout + d.stderr)
        check('missing_auth_exit_2', run('--out', P('ds'), '--query', 'x', e=dict(env)).returncode == 2)
        check('failed_token_refresh_exit_2', run('--out', P('bt'), '--query', 'q one', e=dict(env, YOUTUBE_TOKEN_URL=base + '/badtoken', **auth)).returncode == 2)
        for name, args in (('no_query', []), ('bad_date', ['--query', 'x', '--published-after', 'yesterday']), ('bad_max', ['--query', 'x', '--max', '99'])):
            check(name + '_exit_2', run('--out', P('ds'), *args).returncode == 2)
        r = run('--out', P('quota'), '--query', 'q one', '--query', 'q boom', '--max', '10')  # quota stop: exit 1, work saved
        check('quota_403_exit_1_partial_saved', r.returncode == 1 and list(rows(P('quota'))) == ['AAAAAAAAAAA'], r.stdout + r.stderr)
        s0 = calls['search']
        r = run('--out', P('quota'), '--query', 'q one', '--query', 'q boom', '--max', '10')
        check('search_cache_reused', r.returncode == 1 and calls['search'] - s0 == 1, str(calls))
        s0 = calls['search']
        run('--out', P('dup'), '--query', 'q one', '--query', ' q one ', '--max', '10')
        check('repeated_query_searched_once', calls['search'] - s0 == 1, str(calls))
        state['hq_fail'] = True  # a failing thumbnail: exit 1, retried by a rerun with no videos call, capped at 3 tries
        r = run('--out', P('retry'), '--query', 'q two', '--max', '10')
        check('failed_download_exit_1', r.returncode == 1 and 'CCCCCCCCCCC' in json.loads(r.stdout)['download_failed'], r.stdout)
        state['hq_fail'] = False
        v0 = calls['videos']
        r = run('--out', P('retry'), '--query', 'q two', '--max', '10')
        check('rerun_retries_thumbnail', r.returncode == 0 and rows(P('retry'))['CCCCCCCCCCC']['thumb'] == 'hqdefault' and calls['videos'] == v0, r.stdout)
        state['hq_fail'] = True
        for _ in range(5):
            run('--out', P('tries'), '--query', 'q two', '--max', '10')
        check('failed_thumb_capped_at_3_tries', rows(P('tries'))['CCCCCCCCCCC']['thumb_tries'] == 3)
        state['hq_fail'] = False
        r = run('--out', P('odd'), '--query', 'q three', '--max', '10')  # hostile id, hidden subs, null likes, live and week durations
        o = rows(P('odd'))
        check('odd_run_ok', r.returncode == 0 and set(o) == {'DDDDDDDDDDD', 'EEEEEEEEEEE', 'FFFFFFFFFFF', 'GGGGGGGGGGG'}, r.stdout + r.stderr)
        check('hostile_id_never_requested', '../../x' not in asked and not os.path.exists(P('x.jpg')), str(asked[-3:]))
        check('hidden_subscribers_and_missing_likes_null', o['EEEEEEEEEEE']['subscribers'] is None and o['EEEEEEEEEEE']['outlier'] is None
              and o['DDDDDDDDDDD']['likes'] is None and o['DDDDDDDDDDD']['comments'] is None)
        check('live_null_and_week_parsed', o['FFFFFFFFFFF']['duration_s'] is None and o['GGGGGGGGGGG']['duration_s'] == 604800)
        check('unicode_title_roundtrip', o['DDDDDDDDDDD']['title'] == TITLE and
              [x for x in csv.DictReader(open(P('odd/dataset.csv'), encoding='utf-8')) if x['id'] == 'DDDDDDDDDDD'][0]['title'] == TITLE)
        r = run('--out', P('null'), '--query', 'q odd', '--query', 'q one', '--max', '10')  # null items, null statistics, channel without id
        check('null_items_no_crash', r.returncode == 0 and 'Traceback' not in r.stderr and 'AAAAAAAAAAA' in rows(P('null')), r.stdout + r.stderr)
        VIDEOS['JJJJJJJJJJJ'] = V('C1', 'PT5M', 0, None); SEARCH['q null'] = ['JJJJJJJJJJJ']
        r = run('--out', P('null'), '--query', 'q null', '--max', '10')
        check('null_statistics_no_crash', r.returncode == 0 and rows(P('null')).get('JJJJJJJJJJJ', {}).get('views') == 0, r.stdout + r.stderr)
        state['videos_fail'] = True  # partial videos failure: no row without subscribers; the rerun fetches only the missing page
        r = run('--out', P('part'), '--query', 'q many', '--max', '50')
        pr = rows(P('part'))
        check('partial_failure_exit_2_rows_complete', r.returncode == 2 and len(pr) == 50 and all(x['subscribers'] == 100000 for x in pr.values()), r.stdout + r.stderr)
        state['videos_fail'] = False
        v0 = calls['videos']
        r = run('--out', P('part'), '--query', 'q many', '--max', '50')
        check('partial_rerun_fetches_only_missing', r.returncode == 0 and calls['videos'] - v0 == 1 and len(rows(P('part'))) == 60, r.stdout + str(calls))
        r = run('--out', P('gone'), '--query', 'q gone', '--query', 'q bad', '--max', '10')  # malformed and deleted items
        check('malformed_item_skipped_run_ok', r.returncode == 0 and json.loads(r.stdout)['malformed_items'] == 1 and json.loads(r.stdout)['total'] == 0, r.stdout)
        check('deleted_video_recorded', 'XXXXXXXXXXX' in open(P('gone/gone.txt')).read())
        run('--out', P('gone'), '--query', 'q gone', '--max', '10', '--refresh-searches')
        check('deleted_video_not_requested_again', asked.count('XXXXXXXXXXX') == 1, str(asked.count('XXXXXXXXXXX')))
        run('--out', P('noimg'), '--query', 'q one', '--max', '10', '--no-images')
        none_yet = not os.listdir(P('noimg/thumbs'))
        r = run('--out', P('noimg'), '--query', 'q one', '--max', '10')
        check('no_images_then_later_run_downloads', none_yet and r.returncode == 0 and os.path.exists(P('noimg/thumbs/AAAAAAAAAAA.jpg')), r.stdout)
        open(P('noimg/dataset.jsonl'), 'a').write('{"id": "brok')
        check('cut_jsonl_line_tolerated', run('--out', P('noimg'), '--query', 'q one', '--max', '10').returncode == 0)
    print(json.dumps({'evidence': ev, 'failures': fails}))
    sys.exit(1 if fails else 0)

if __name__ == '__main__':
    main()
