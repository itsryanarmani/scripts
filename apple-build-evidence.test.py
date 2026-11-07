#!/usr/bin/env python3
"""Exercise the CLI through real subprocesses and isolated fake Xcode tools."""
import fcntl
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

CLI = Path(__file__).with_name('apple-build-evidence')
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    repo = root / 'repo'
    repo.mkdir()
    (repo / 'App.xcodeproj').mkdir()
    (repo / 'source.swift').write_text('import SwiftUI\n')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True)
    git('init', '-q')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Seed')
    tools = root / 'bin'
    tools.mkdir()
    fake = tools / 'xcodebuild'
    fake.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
with open(os.environ['TRACE'],'a') as f:f.write(('test' if 'test' in sys.argv else 'archive')+'\\n')
with open(os.environ['ARGV_TRACE'],'a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')
if os.environ.get('FAIL_TEST') and 'test' in sys.argv:sys.exit(9)
for flag in ['-resultBundlePath','-archivePath']:
 if flag in sys.argv:Path(sys.argv[sys.argv.index(flag)+1]).mkdir()
''')
    fake.chmod(0o755)
    config = root / 'config.json'
    config.write_text(json.dumps({'repository': str(repo), 'project': 'App.xcodeproj', 'scheme': 'App', 'inputs': ['source.swift'], 'destinations': ['platform=iOS Simulator,id=fixture']}))
    trace = root / 'trace'
    output = root / 'proof'
    argv_trace = root / 'argv-trace'
    env = {**os.environ, 'PATH': str(tools)+os.pathsep+os.environ['PATH'], 'TRACE': str(trace), 'ARGV_TRACE': str(argv_trace)}
    def run(*args, expected=0, extra=None):
        p = subprocess.run([sys.executable, str(CLI), str(config), '--output', str(output), *args], env={**env, **(extra or {})}, capture_output=True, text=True)
        assert p.returncode == expected, (p.returncode, p.stdout, p.stderr)
        assert 'private-sentinel' not in p.stdout + p.stderr
        return json.loads(p.stdout) if p.stdout else None
    plan = run()
    assert plan['status'] == 'planned' and not output.exists() and not trace.exists()
    run('--execute', expected=1, extra={'FAIL_TEST':'1'})
    assert trace.read_text().splitlines() == ['test']
    assert not (output / 'success.json').exists()
    trace.unlink()
    passed = run('--execute')
    assert passed['status'] == 'passed' and len(passed['phases']) == 2
    assert trace.read_text().splitlines() == ['test','archive']
    assert Path(passed['artifactDirectory'], 'app.xcarchive').is_dir()
    skipped = run('--execute')
    assert skipped['status'] == 'unchanged'
    assert trace.read_text().splitlines() == ['test','archive']
    shutil.rmtree(Path(passed['artifactDirectory']) / 'app.xcarchive')
    restored = run('--execute')
    assert restored['status'] == 'passed'
    assert restored['destinations'] == ['platform=iOS Simulator,id=fixture']
    lock = (output / '.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    run('--execute', expected=1)
    lock.close()
    original_config = json.loads(config.read_text())
    settings = {'MARKETING_VERSION': '1.0', 'CURRENT_PROJECT_VERSION': '2'}
    config.write_text(json.dumps({**original_config, 'buildSettings': settings}))
    identity = run('--execute')
    assert identity['status'] == 'passed' and identity['buildSettings'] == settings
    commands = [json.loads(line) for line in argv_trace.read_text().splitlines()[-2:]]
    assert 'test' in commands[0] and 'archive' in commands[1]
    for argv in commands:
        assert argv.count('CURRENT_PROJECT_VERSION=2') == 1
        assert argv.count('MARKETING_VERSION=1.0') == 1
        assert argv.count('CODE_SIGNING_ALLOWED=NO') == 1
    count = len(argv_trace.read_text().splitlines())
    assert run('--execute')['status'] == 'unchanged'
    assert len(argv_trace.read_text().splitlines()) == count
    config.write_text(json.dumps({**original_config, 'buildSettings': {**settings, 'CURRENT_PROJECT_VERSION': '3'}}))
    new_build = run('--execute')
    assert new_build['status'] == 'passed' and new_build['sourceHash'] != identity['sourceHash']
    config.write_text(json.dumps({**original_config, 'buildSettings': {**settings, 'MARKETING_VERSION': '1.1'}}))
    new_version = run('--execute')
    assert new_version['status'] == 'passed' and new_version['sourceHash'] != identity['sourceHash']
    count = len(argv_trace.read_text().splitlines())
    for invalid in [None, [], '2', {'CODE_SIGNING_ALLOWED': 'YES'},
                    {'CURRENT_PROJECT_VERSION': 2}, {'CURRENT_PROJECT_VERSION': True},
                    {'CURRENT_PROJECT_VERSION': '0'}, {'CURRENT_PROJECT_VERSION': '-1'},
                    {'CURRENT_PROJECT_VERSION': '2 CODE_SIGNING_ALLOWED=YES'},
                    {'CURRENT_PROJECT_VERSION': '1000000000'},
                    {'MARKETING_VERSION': '1.0\n'}, {'MARKETING_VERSION': '1.2.3.4'},
                    {'MARKETING_VERSION': '$(private-sentinel)'}, {'MARKETING_VERSION': '-sdk'}]:
        config.write_text(json.dumps({**original_config, 'buildSettings': invalid}))
        run('--execute', expected=1)
        run(expected=1)
    assert len(argv_trace.read_text().splitlines()) == count
    config.write_text(json.dumps(original_config))
    (repo / 'source.swift').write_text('changed\n')
    run('--execute', expected=1)
    assert len(argv_trace.read_text().splitlines()) == count
    report = {'scenarios': ['plan has no writes', 'failed test stops archive', 'failure has no success stamp', 'success stores artifacts and timing', 'unchanged skips tools', 'concurrent lock fails', 'dirty source fails', 'missing retained archive rebuilds', 'explicit identity reaches both unsigned phases', 'same identity reuses artifacts', 'changed build rebuilds', 'changed marketing version rebuilds', 'invalid identities reject plan and execute before tools'], 'passed': 13, 'rejectedIdentityConfigs': 14, 'appleUploadExecuted': False}
    proof = Path(os.environ.get('APPLE_BUILD_TEST_PROOF', str(root / 'cli-proof.json')))
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
