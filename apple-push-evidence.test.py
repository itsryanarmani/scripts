#!/usr/bin/env python3
"""CLI E2E: real Git pushes with fake XcodeGen and evidence runner."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

TOOL = Path(__file__).with_name('apple-push-evidence')
proof = {'passed': False, 'scenarios': [], 'realAppleUploads': 0}

def call(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()

try:
    with tempfile.TemporaryDirectory(prefix='apple-push-e2e-') as temp:
        root = Path(temp)
        remote, author, repo = [root / n for n in ('remote.git', 'author', 'dedicated')]
        call(['git', 'init', '--bare', '-q', str(remote)])
        call(['git', 'init', '-q', '-b', 'main', str(author)])
        call(['git', 'config', 'user.email', 'test@example.invalid'], author)
        call(['git', 'config', 'user.name', 'Fixture'], author)
        (author/'project.yml').write_text('name: Fixture\n')
        (author/'source.txt').write_text('first\n')
        call(['git', 'add', '.'], author)
        call(['git', 'commit', '-qm', 'Initial fixture'], author)
        call(['git', 'remote', 'add', 'origin', str(remote)], author)
        call(['git', 'push', '-q', 'origin', 'main'], author)
        call(['git', 'clone', '-q', '--branch', 'main', str(remote), str(repo)])
        bin_dir = root/'bin'; bin_dir.mkdir()
        shutil.copy2(TOOL, bin_dir/'apple-push-evidence')
        generator = bin_dir/'xcodegen'
        generator.write_text('#!/usr/bin/env python3\nimport os,sys\nfrom pathlib import Path\nPath(os.environ["TRACE"]).open("a").write("generate\\n")\nsys.exit(1 if Path("fail-generator").exists() else 0)\n')
        runner = bin_dir/'apple-build-evidence'
        runner.write_text('''#!/usr/bin/env python3
import json,os,subprocess,sys
from pathlib import Path
config=json.loads(Path(sys.argv[1]).read_text())
repo=Path(config['repository'])
source=(repo/'source.txt').read_text()
stamp=Path(os.environ['STAMP'])
status='unchanged' if stamp.exists() and stamp.read_text()==source else 'passed'
stamp.write_text(source)
Path(os.environ['TRACE']).open('a').write('runner\\n')
print(json.dumps({'status':status,'sourceCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'uploadExecuted':False}))
''')
        for p in (generator, runner): p.chmod(0o755)
        evidence = root/'evidence-config.json'
        evidence.write_text(json.dumps({'repository': str(repo)}))
        output = root/'output'
        config = root/'config.json'
        config.write_text(json.dumps({'repository':str(repo),'branch':'main','projectSpec':'project.yml','evidenceConfig':str(evidence),'output':str(output)}))
        env={**os.environ,'PATH':str(bin_dir)+os.pathsep+os.environ['PATH'],'TRACE':str(root/'trace'),'STAMP':str(root/'stamp')}
        def invoke(execute=False, ok=True):
            result=subprocess.run([sys.executable,str(bin_dir/'apple-push-evidence'),str(config)]+(['--execute'] if execute else []),env=env,capture_output=True,text=True)
            assert (result.returncode==0)==ok, (result.returncode,result.stdout,result.stderr)
            return json.loads(result.stdout) if result.stdout else None
        invoke(ok=False)
        assert not output.exists()
        proof['scenarios'].append('unowned-checkout-rejected')
        marker=repo/'.git/apple-push-evidence-owned'
        marker.write_text('apple-push-evidence\n')
        assert invoke()['status']=='planned'
        assert not output.exists() and not (root/'trace').exists()
        proof['scenarios'].append('plan-does-not-fetch-build-or-write')
        original=json.loads(config.read_text())
        for patch in ({'branch':'--upload'}, {'projectSpec':'../outside.yml'}, {'output':str(repo/'proof')}, {'unexpected':True}):
            config.write_text(json.dumps({**original,**patch}))
            invoke(ok=False)
        config.write_text(json.dumps(original))
        proof['scenarios'].append('invalid-config-rejected-before-tools')
        (repo/'source.txt').write_text('dirty')
        invoke(True,False)
        assert not (root/'trace').exists()
        call(['git','checkout','--','source.txt'],repo)
        proof['scenarios'].append('dirty-source-rejected')
        assert invoke(True)['evidence']['status']=='passed'
        proof['scenarios'].append('real-git-source-build-orchestration')
        assert invoke(True)['evidence']['status']=='unchanged'
        proof['scenarios'].append('unchanged-evidence-delegated-to-retained-artifact-guard')
        (author/'source.txt').write_text('second\n')
        call(['git','commit','-qam','Change source'],author)
        call(['git','push','-q','origin','main'],author)
        result=invoke(True)
        assert result['evidence']['status']=='passed'
        assert (repo/'source.txt').read_text()=='second\n'
        assert result['sourceCommit']==call(['git','rev-parse','HEAD'],author)
        proof['scenarios'].append('remote-push-reaches-exact-build-commit')
        # A tracked generator failure must not call the evidence runner.
        (author/'fail-generator').touch()
        call(['git','add','.'],author); call(['git','commit','-qm','Fail generator'],author)
        call(['git','push','-q','origin','main'],author)
        before=(root/'trace').read_text().count('runner')
        invoke(True,False)
        assert (root/'trace').read_text().count('runner')==before
        proof['scenarios'].append('generation-failure-stops-evidence')
        with (output/'.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            before=(root/'trace').read_text()
            invoke(True,False)
            assert (root/'trace').read_text()==before
        proof['scenarios'].append('concurrent-run-rejected')
        assert output.stat().st_mode & 0o077==0
        proof['scenarios'].append('private-output-permissions')
        proof['passed']=True
except Exception as error:
    proof['error']=str(error)
finally:
    content=json.dumps(proof,indent=2)+'\n'
    if os.environ.get('APPLE_PUSH_TEST_PROOF'):
        Path(os.environ['APPLE_PUSH_TEST_PROOF']).write_text(content)
    print(content,end='')
sys.exit(0 if proof['passed'] else 1)
