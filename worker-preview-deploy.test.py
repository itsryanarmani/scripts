#!/usr/bin/env python3
"""Offline subprocess checks. Optional argument saves a private JSON result."""
import copy
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
PLAN = runpy.run_path(str(ROOT / 'worker-preview-plan'))
ACCESS = runpy.run_path(str(ROOT / 'worker-preview-access'))
RESULTS = []
SECRET = 'fake-secret-must-never-appear'
SHA = 'a' * 40

def write(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)

def case(label, change=None, success=False, pending=False, credentials=True):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        intake, state, output = (root / name for name in ('intake', 'state', 'output'))
        for directory in (intake, state, output, intake / 'bundle', intake / 'bundle/worker'):
            directory.mkdir(mode=0o700)
        worker = intake / 'bundle/worker/worker.js'
        worker.write_text("throw new Error('LOCAL_WORKER_EXECUTION_IS_FORBIDDEN'); export default {};\n")
        worker.chmod(0o600)
        pin = dict(schema=1, repository='example/demo', pull_request=7, branch='scr-7-example',
                   head_sha=SHA, workflow='Worker Preview Build', run_id=8,
                   artifact='worker-preview-bundle', artifact_id=9, artifact_digest='sha256:' + 'b' * 64)
        write(intake / 'intake.json', pin)
        manifest = {key: pin[key] for key in ('schema', 'repository', 'pull_request', 'head_sha', 'branch')}
        manifest['files'] = {'worker/worker.js': 'sha256:' + hashlib.sha256(worker.read_bytes()).hexdigest()}
        write(intake / 'bundle/artifact-manifest.json', manifest)
        plan = PLAN['plan'](pin, dict(schema=1, repository=pin['repository'], prefix='scr',
            worker_name='example-worker', workers_dev=False, preview_domain='preview.example.test',
            bindings=dict(d1=['DB'], kv=['CACHE'], r2=['FILES'])))
        write(root / 'plan', plan)
        ac = dict(schema=1, repository=pin['repository'], account_id='c' * 32,
                  preview_domain='preview.example.test', preview_urls=False,
                  reviewer_emails=['reviewer@example.test'], identity_provider_id='identity123')
        write(root / 'access-config', ac)
        desired = ACCESS['validate'](plan, ac)
        ast = ACCESS['initial_state'](plan['owner'], ACCESS['identity'](desired))
        ast['access'] = {key: key.replace('_', '-') + '-123' for key in ACCESS['STATE_IDS']}
        _, access_path, _ = ACCESS['scope_paths'](state, ac['account_id'], plan['owner'])
        write(access_path, ast)
        scope = f"{ac['account_id']}-{hashlib.sha256(pin['repository'].encode()).hexdigest()[:16]}-pr-7"
        data_path = state / (scope + '.json')
        data = copy.deepcopy(plan)
        for kind, value in [('d1', '1' * 8 + '-1111-1111-1111-' + '1' * 12), ('kv', '2' * 32), ('r2', plan['intended']['r2'][0]['name'])]:
            data['acquired'][kind][plan['intended'][kind][0]['binding']] = {'name' if kind == 'r2' else 'id': value}
        write(data_path, data)
        desired['service_policy']['include'][0]['service_token']['token_id'] = ast['access']['service_token_id']
        dep = dict(id='deployment123', preview_id='preview123', preview_name=pin['branch'],
                   annotations={'workers/commit_sha': SHA}, urls=['https://unique-deployment.example.test'])
        preview = dict(id='preview123', name=pin['branch'], worker_name='example-worker', urls=['https://' + plan['intended']['preview']['hostname']])
        fixture = dict(pr=dict(state='open', head=dict(sha=SHA, ref=pin['branch'], repo=dict(full_name=pin['repository'])),
                              base=dict(repo=dict(full_name=pin['repository']))),
                       preview=preview, deployment=dep, mode='ok', data=data, desired=desired, access=ast['access'])
        fake = root / 'wrangler'
        fake.write_text('#!' + sys.executable + '\n' + '''import json, os, pathlib, sys
r = pathlib.Path(__file__).parent
f = json.loads((r / 'fixture').read_text())
if sys.argv[1:] == ['--version']:
    print('4.135.0'); raise SystemExit()
a = sys.argv[1:]
assert a[0] == 'preview' and '--ignore-base-config' in a and '--json' in a
assert 'upload' not in a and '--no-bundle' not in a
assert 'fake-secret-must-never-appear' not in str(a)
c = json.loads(pathlib.Path(a[a.index('--config') + 1]).read_text())
assert c['no_bundle'] is True and c['workers_dev'] is False and c['preview_urls'] is False
assert not any(k in c for k in ('vars','d1_databases','kv_namespaces','r2_buckets'))
assert c['previews']['vars'] == {'MODE':'preview'} and c['compatibility_flags'] == ['nodejs_compat']
if f.get('assets'):
    assert c['assets']['binding'] == 'ASSETS'
    assert pathlib.Path(c['assets']['directory'], 'index.html').read_text() == 'asset fixture'
    assert pathlib.Path(c['main']).with_name('module.mjs').read_text() == 'export const value = 1;'
assert c['previews']['d1_databases'][0]['database_id'] == '11111111-1111-1111-1111-111111111111'
assert os.environ['GITHUB_SHA'] == 'a' * 40 and 'NODE_OPTIONS' not in os.environ
assert pathlib.Path.cwd() != r and not (pathlib.Path.cwd() / '.git').exists()
assert 'LOCAL_WORKER_EXECUTION_IS_FORBIDDEN' in pathlib.Path(c['main']).read_text()
with (r / 'events').open('a') as out: out.write('upload\\n')
if f['mode'] == 'crash': os._exit(9)
if f['mode'] == 'malformed': print('fake-secret-must-never-appear'); raise SystemExit()
print(json.dumps(dict(version=1, preview=f['preview'], deployment=f['deployment'])))
''')
        fake.chmod(0o700)
        gh = root / 'gh'
        gh.write_text('#!' + sys.executable + '\nimport json,pathlib\nr=pathlib.Path(__file__).parent\nf=json.loads((r/"fixture").read_text())\nn=int((r/"gh-count").read_text())+1 if (r/"gh-count").exists() else 1\n(r/"gh-count").write_text(str(n))\nif n >= f.get("head_changes_at",99): f["pr"]["head"]["sha"]="e"*40\nprint(json.dumps(f["pr"]))\n')
        gh.chmod(0o700)
        cfg = dict(github_cli=str(gh), github_cli_sha256=hashlib.sha256(gh.read_bytes()).hexdigest(), artifact_manifest_sha256=hashlib.sha256((intake / 'bundle/artifact-manifest.json').read_bytes()).hexdigest(), wrangler=str(fake), wrangler_sha256=hashlib.sha256(fake.read_bytes()).hexdigest(),
                   compatibility_date='2026-01-01', compatibility_flags=['nodejs_compat'], asset_binding=None, vars={'MODE': 'preview'}, secret_names=['SESSION_KEY'])
        write(root / 'config', cfg)
        write(root / 'credentials', {'account_id': ac['account_id'], 'api_token': SECRET})
        write(root / 'secrets', {'SESSION_KEY': SECRET})
        context = locals()
        if change:
            change(context)
        write(root / 'fixture', fixture)
        shim = root / 'shim.py'
        shim.write_text('''import io,json,pathlib,runpy,sys,urllib.request,urllib.error
r=pathlib.Path(__file__).parent
f=json.loads((r/'fixture').read_text())
original=pathlib.Path.read_bytes
def read(p):
    if p.name in {'credentials','secrets'}:
        with (r/'events').open('a') as out: out.write(p.name+'\\n')
    return original(p)
pathlib.Path.read_bytes=read
def api(request, timeout=30):
    p=request.full_url
    assert p.startswith('https://api.cloudflare.com/client/v4/') and request.method=='GET'
    if p.endswith('/previews/scr-7-example') and not f.get('existing_preview'): raise urllib.error.HTTPError(p,404,'missing',{},None)
    if f.get('readback_failure') and '/deployments/' in p: raise OSError('fake-secret-must-never-appear')
    if '/deployments/' in p: value=f.get('readback',f['deployment'])
    elif '/previews/' in p: value=f['preview']
    elif '/subdomain' in p: value=dict(enabled=f.get('public_worker',False),previews_enabled=False)
    elif '/d1/database' in p: value=[dict(uuid=f['data']['acquired']['d1']['DB']['id'],name=f['data']['intended']['d1'][0]['name'])]
    elif '/storage/kv/' in p: value=[dict(id=f['data']['acquired']['kv']['CACHE']['id'],title=f['data']['intended']['kv'][0]['name'])]
    elif '/r2/buckets' in p: value=dict(buckets=[dict(name=f['data']['acquired']['r2']['FILES']['name'])])
    elif '/policies' in p: value=[dict(f['desired'][k],id=f['access'][k+'_id']) for k in ['human_policy','service_policy']]
    elif '/access/apps' in p: value=[dict(f['desired']['application'],id=f['access']['application_id'])]
    elif '/service_tokens' in p: value=[dict(f['desired']['service_token'],id=f['access']['service_token_id'])]
    else: value=dict(id='example-worker')
    pages=2 if f.get('paginated') and '/access/' in p else 1
    if pages == 2:
        if '/policies' in p: value=value[1:] if 'page=2&' in p else value[:1]
        elif 'page=2&' not in p: value=[dict(id='unrelated',domain='other.example.test')]
    return io.BytesIO(json.dumps(dict(success=True,result=value,result_info=dict(total_count=len(value),total_pages=pages))).encode())
urllib.request.urlopen=api
urllib.request.OpenerDirector.open=lambda self, request, timeout=30: api(request,timeout)
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
''')
        command = [sys.executable, str(shim), str(ROOT / 'worker-preview-deploy'), str(intake),
                   str(root / 'plan'), str(root / 'config'), str(root / 'access-config'),
                   str(state), str(output), str(root / 'credentials'), str(root / 'secrets')]
        env = dict(PATH=str(root) + ':/usr/bin:/bin', NODE_OPTIONS='--poison-parent', HOME=str(root))
        run = subprocess.run(command, capture_output=True, text=True, env=env)
        events = (root / 'events').read_text().splitlines() if (root / 'events').exists() else []
        assert (run.returncode == 0) == success, (label, run.returncode, run.stdout, run.stderr)
        assert ('credentials' in events) == credentials, (label, events)
        assert bool(list(state.glob('.deploy-*.pending'))) == pending, (label, list(output.iterdir()))
        assert SECRET not in run.stdout + run.stderr
        if not success:
            assert ('upload-incomplete-reconcile-pending' if pending else 'preflight-rejected-no-upload') in run.stderr
        receipts = [p for p in state.glob('.deploy-*.receipt.json') if '-old-head.' not in p.name]
        assert bool(receipts) == success
        if success:
            receipt = json.loads(receipts[0].read_text())
            assert receipt['deployment_id'] == 'deployment123' and receipt['owner'] == plan['owner']
            assert json.loads(data_path.read_text())['acquired']['preview']['version_id'] is None
        if pending:
            alternate = root / 'alternate'
            alternate.mkdir(mode=0o700)
            command[8] = str(alternate)
            again = subprocess.run(command, capture_output=True, text=True, env=env)
            assert again.returncode and (root / 'events').read_text().splitlines().count('upload') == 1
        for path in [*output.iterdir(), *state.iterdir()]:
            assert path.stat().st_mode & 0o077 == 0 and SECRET not in path.read_text()
        RESULTS.append(dict(case=label, status='passed', exit_code=run.returncode, credentials_loaded='credentials' in events, pending=pending))

def assets(c):
    for name, text in [('worker/module.mjs', 'export const value = 1;'), ('assets/index.html', 'asset fixture')]:
        path=c['intake'] / 'bundle' / name
        path.parent.mkdir(mode=0o700, exist_ok=True)
        path.write_text(text); path.chmod(0o600)
        c['manifest']['files'][name]='sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
    write(c['intake'] / 'bundle/artifact-manifest.json', c['manifest'])
    c['cfg'].update(asset_binding='ASSETS', artifact_manifest_sha256=hashlib.sha256((c['intake'] / 'bundle/artifact-manifest.json').read_bytes()).hexdigest())
    write(c['root'] / 'config', c['cfg']); c['fixture']['assets']=True

case('existing-preview-rejected', lambda c: c['fixture'].update(existing_preview=True))
case('public-worker-rejected', lambda c: c['fixture'].update(public_worker=True))
case('positive', success=True)
case('modules-and-assets', assets, success=True)
case('paginated-access', lambda c: c['fixture'].update(paginated=True), success=True)
case('prior-head-receipt', lambda c: write(c['state'] / ('.deploy-' + c['scope'] + '-old-head.receipt.json'), {}), success=True)
case('invalid-flags', lambda c: (c['cfg'].update(compatibility_flags='nodejs_compat'), write(c['root'] / 'config',c['cfg'])), credentials=False)
case('asset-binding-collision', lambda c: (c['cfg'].update(asset_binding='DB'), write(c['root'] / 'config',c['cfg'])), credentials=False)
case('head-changed-before-upload', lambda c: c['fixture'].update(head_changes_at=2), credentials=True)
case('head-changed-after-upload', lambda c: c['fixture'].update(head_changes_at=3), credentials=True, pending=True)
case('foreign-head', lambda c: c['fixture']['pr']['head'].update(sha='d' * 40), credentials=False)
case('payload-and-manifest-change', lambda c: (c['worker'].write_text('changed'), c['manifest']['files'].update({'worker/worker.js': 'sha256:' + hashlib.sha256(c['worker'].read_bytes()).hexdigest()}), write(c['intake'] / 'bundle/artifact-manifest.json', c['manifest'])), credentials=False)
case('hash-change', lambda c: c['worker'].write_text('changed'), credentials=False)
case('extra-config', lambda c: write(c['intake'] / 'bundle/wrangler.json', {}), credentials=False)
case('missing-data', lambda c: write(c['data_path'], c['plan']), credentials=False)
case('foreign-access', lambda c: (c['ast']['owner'].update(head_sha='d' * 40), write(c['access_path'], c['ast'])), credentials=False)
case('wrong-github-hash', lambda c: (c['cfg'].update(github_cli_sha256='0' * 64), write(c['root'] / 'config', c['cfg'])), credentials=False)
case('wrong-cli-hash', lambda c: (c['cfg'].update(wrangler_sha256='0' * 64), write(c['root'] / 'config', c['cfg'])), credentials=False)
case('bad-secret', lambda c: write(c['root'] / 'secrets', {'PRODUCTION_KEY': SECRET}), credentials=False)
case('foreign-url', lambda c: c['fixture']['preview'].update(urls=['https://foreign.example.test']), pending=True)
case('api-readback-failure', lambda c: c['fixture'].update(readback_failure=True), pending=True)
case('foreign-readback', lambda c: c['fixture'].update(readback=dict(c['dep'], id='foreign123')), pending=True)
case('malformed-output', lambda c: c['fixture'].update(mode='malformed'), pending=True)
case('crash', lambda c: c['fixture'].update(mode='crash'), pending=True)
case('foreign-intake', lambda c: (c['pin'].update(artifact_id=99), write(c['intake'] / 'intake.json', c['pin'])), credentials=False)
case('foreign-data', lambda c: (c['data']['owner'].update(head_sha='e' * 40), write(c['data_path'], c['data'])), credentials=False)
case('unsafe-plan-permission', lambda c: (c['root'] / 'plan').chmod(0o644), credentials=False)
case('symlink-input', lambda c: ((c['root'] / 'plan').rename(c['root'] / 'real-plan'), (c['root'] / 'plan').symlink_to(c['root'] / 'real-plan')), credentials=False)
case('duplicate-json', lambda c: (c['root'] / 'config').write_text('{"vars":{},"vars":{}}'), credentials=False)
case('extra-config-key', lambda c: (c['cfg'].update(build='execute'), write(c['root'] / 'config', c['cfg'])), credentials=False)
case('foreign-remote-data', lambda c: c['fixture']['data']['acquired']['kv']['CACHE'].update(id='3' * 32), credentials=True)
case('foreign-remote-access', lambda c: c['fixture']['desired']['application'].update(domain='foreign.example.test'), credentials=True)
case('pending-acquisition', lambda c: write(c['state'] / (c['scope'] + '.pending'), {}), credentials=False)
case('pending-access', lambda c: (c['ast'].update(pending='application'), write(c['access_path'], c['ast'])), credentials=False)
case('foreign-preview', lambda c: c['fixture']['preview'].update(worker_name='foreign-worker'), pending=True)
case('foreign-commit', lambda c: c['fixture']['deployment']['annotations'].update({'workers/commit_sha': 'e' * 40}), pending=True)
case('bad-unique-url-schema', lambda c: c['fixture']['deployment'].update(urls=123), pending=True)
case('missing-native-id', lambda c: c['fixture']['deployment'].pop('id'), pending=True)
print(json.dumps(dict(schema=1, cases=RESULTS), sort_keys=True))
if len(sys.argv) == 2:
    write(Path(sys.argv[1]), dict(schema=1, cases=RESULTS))
