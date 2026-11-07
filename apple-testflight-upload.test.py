#!/usr/bin/env python3
"""End-to-end CLI guard scenarios; fake Xcode never contacts Apple."""
import json,os,plistlib,subprocess,sys,tempfile,fcntl
from pathlib import Path
CLI=Path(__file__).with_name('apple-testflight-upload')
with tempfile.TemporaryDirectory() as temp:
 r=Path(temp);archive=r/'evidence/app.xcarchive';app=archive/'Products/Applications/Fixture.app';app.mkdir(parents=True)
 (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'example.fixture','CFBundleShortVersionString':'1.0','CFBundleVersion':'2'}));(app/'Fixture').write_bytes(b'fixture')
 summary=r/'summary.json';passed={'status':'passed','sourceHash':'a'*64,'sourceCommit':'b'*40,'artifactDirectory':str(archive.parent),'phases':[{'name':'test-0','exitCode':0},{'name':'archive','exitCode':0}]};summary.write_text(json.dumps(passed))
 key=r/'key.p8';key.write_text('FAKE_SECRET_SENTINEL');key.chmod(0o600)
 config=r/'config.json';config.write_text(json.dumps({'keyId':'KEY1234567','issuerId':'00000000-0000-0000-0000-000000000001','privateKeyPath':str(key)}));config.chmod(0o600)
 options=r/'options.plist';options.write_bytes(plistlib.dumps({'method':'app-store-connect','signingStyle':'automatic','teamID':'FAKETEAM'}))
 tools=r/'bin';tools.mkdir();trace=r/'trace';fake=tools/'xcodebuild'
 fake.write_text('''#!/usr/bin/env python3
import sys,os,plistlib
with open(sys.argv[sys.argv.index('-exportOptionsPlist')+1],'rb') as f:o=plistlib.load(f)
assert o['testFlightInternalTestingOnly'] is True and o['destination']=='upload'
assert o['manageAppVersionAndBuildNumber'] is False
with open(os.environ['TRACE'],'a') as f:f.write('upload\\n')
print('FAKE_SECRET_SENTINEL')
sys.exit(7 if os.environ.get('FAIL_UPLOAD') else 0)
''');fake.chmod(0o755)
 state=r/'state/receipt.json';env={**os.environ,'PATH':str(tools)+os.pathsep+os.environ['PATH'],'TRACE':str(trace)}
 def run(*extra,expected=0,fail=False,state_path=state):
  p=subprocess.run([sys.executable,str(CLI),str(summary),'--bundle-id','example.fixture','--signing-config',str(config),'--export-options',str(options),'--state',str(state_path),'--known-build-floor','1',*extra],env={**env,**({'FAIL_UPLOAD':'1'} if fail else {})},capture_output=True,text=True)
  assert p.returncode==expected,(p.returncode,p.stdout,p.stderr)
  assert 'FAKE_SECRET_SENTINEL' not in p.stdout+p.stderr
  return json.loads(p.stdout) if p.stdout else None
 assert run()['status']=='planned' and not state.parent.exists() and not trace.exists()
 summary.write_text(json.dumps({**passed,'status':'failed'}));run('--execute',expected=1);assert not trace.exists();summary.write_text(json.dumps(passed))
 run('--execute','--bundle-id','example.other',expected=1);assert not trace.exists()
 run('--execute','--known-build-floor','2',expected=1);assert not trace.exists()
 options.write_bytes(plistlib.dumps({'method':'app-store-connect','testFlightInternalTestingOnly':False}));run('--execute',expected=1);assert not trace.exists();options.write_bytes(plistlib.dumps({'method':'app-store-connect'}))
 assert run('--execute')['status']=='uploaded';assert trace.read_text().splitlines()==['upload']
 assert run('--execute')['status']=='unchanged';assert trace.read_text().splitlines()==['upload']
 (app/'Fixture').write_bytes(b'modified');run('--execute',expected=1);(app/'Fixture').write_bytes(b'fixture')
 failure_state=r/'failed/receipt.json';assert run('--execute',expected=1,fail=True,state_path=failure_state)['status']=='upload-unknown'
 assert run('--execute',expected=2,state_path=failure_state)['status']=='blocked-pending'
 assert len(trace.read_text().splitlines())==2
 with (state.parent/'.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);run('--execute',expected=1)
 report={'passedScenarios':11,'realAppleUploads':0,'cases':['plan writes nothing','failed evidence stops','bundle identity checked','build floor enforced','public options rejected','internal-only upload forced','duplicate skipped','mutated candidate rejected','failure pending','pending retry blocked','concurrent run blocked'],'secretSentinelExcludedFromConsole':True}
 proof=Path(os.environ.get('APPLE_UPLOAD_TEST_PROOF',str(r/'proof.json')));proof.parent.mkdir(parents=True,exist_ok=True);proof.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
