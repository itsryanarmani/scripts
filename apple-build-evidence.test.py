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
import os,sys
from pathlib import Path
with open(os.environ['TRACE'],'a') as f:f.write(('test' if 'test' in sys.argv else 'archive')+'\\n')
if os.environ.get('FAIL_TEST') and 'test' in sys.argv:sys.exit(9)
for flag in ['-resultBundlePath','-archivePath']:
 if flag in sys.argv:Path(sys.argv[sys.argv.index(flag)+1]).mkdir()
''')
    fake.chmod(0o755)
    config = root / 'config.json'
    config.write_text(json.dumps({'repository': str(repo), 'project': 'App.xcodeproj', 'scheme': 'App', 'inputs': ['source.swift'], 'destinations': ['platform=iOS Simulator,id=fixture']}))
    trace = root / 'trace'
    output = root / 'proof'
    env = {**os.environ, 'PATH': str(tools)+os.pathsep+os.environ['PATH'], 'TRACE': str(trace)}
    def run(*args, expected=0, extra=None):
        p = subprocess.run([sys.executable, str(CLI), str(config), '--output', str(output), *args], env={**env, **(extra or {})}, capture_output=True, text=True)
        assert p.returncode == expected, (p.returncode, p.stdout, p.stderr)
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
    (repo / 'source.swift').write_text('changed\n')
    run('--execute', expected=1)
    assert trace.read_text().splitlines() == ['test','archive','test','archive']
    report = {'scenarios': ['plan has no writes', 'failed test stops archive', 'failure has no success stamp', 'success stores artifacts and timing', 'unchanged skips tools', 'concurrent lock fails', 'dirty source fails', 'missing retained archive rebuilds'], 'passed': 8, 'appleUploadExecuted': False}
    proof = Path(os.environ.get('APPLE_BUILD_TEST_PROOF', str(root / 'cli-proof.json')))
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
