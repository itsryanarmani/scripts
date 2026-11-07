#!/usr/bin/env python3
"""Check runner tiers and visibility without live GitHub calls."""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
LEGACY = 'ubi' + 'cloud-standard-2'
WORKFLOW = '''name: tiers
on: push
jobs:
  default:
    runs-on: boat
  large:
    runs-on: boat-8
  list:
    runs-on:
      - boat
  group:
    runs-on:
      group: pool
      labels: [boat-8]
  old:
    runs-on: LEGACY
  hosted:
    runs-on: ubuntu-latest
  other:
    runs-on: boat-builder
'''.replace('LEGACY', LEGACY)


class BoatCI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        gh = self.base / 'gh'
        gh.write_text('''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args[0] == 'auth': pass
elif args[0] == 'repo': print('[{"name":"example"}]')
elif args[0] == 'api':
    endpoint = next(a for a in args[1:] if a.startswith('repos/'))
    if endpoint.endswith('/workflows'):
        print('[{"name":"ci.yml","type":"file"}]')
    elif endpoint.endswith('/ci.yml'):
        print(json.dumps({'content': os.environ['WORKFLOW_B64']}))
    elif '/actions/runs?' in endpoint:
        print('1\\tCI\\t2026-10-11T00:00:00Z')
    elif '/jobs?' in endpoint:
        for label in ['boat', 'boat-8', 'self-hosted|boat', os.environ['LEGACY'], 'ubuntu-latest', 'boat-builder']:
            print(f'1\\t{label}\\t2026-10-11T00:00:00Z\\t2026-10-11T00:00:10Z\\t{label}')
    else: sys.exit(2)
else: sys.exit(2)
''')
        gh.chmod(0o755)
        self.env = dict(os.environ, PATH=f'{self.base}:{os.environ["PATH"]}',
                        WORKFLOW_B64=base64.b64encode(WORKFLOW.encode()).decode(),
                        LEGACY=LEGACY)

    def run_tool(self, tool, *args):
        return subprocess.run([str(ROOT / tool), *args], env=self.env,
                              check=True, capture_output=True, text=True).stdout

    def test_audit_tiers_and_legacy_finding(self):
        rows = json.loads(self.run_tool('ci-runner-audit', 'fixture', '--json'))
        by_job = {row['job']: row for row in rows}
        for job in ('default', 'large', 'list', 'group'):
            self.assertEqual(by_job[job]['tier'], 'boat')
        self.assertEqual(by_job['old']['tier'], 'cloud')
        self.assertIn('legacy', by_job['old']['warnings'][0])
        for job in ('hosted', 'other'):
            self.assertEqual(by_job[job]['tier'], 'hosted')
            self.assertEqual(by_job[job]['warnings'], [])
        self.assertIn('legacy', self.run_tool('ci-runner-audit', 'fixture'))

    def test_latency_counts_jit_labels(self):
        data = json.loads(self.run_tool('ci-pr-latency', 'fixture/example', '--json'))
        self.assertEqual(data['machine_seconds_by_tier'],
                         {'boat': 30, 'cloud': 10, 'hosted': 20})

    def test_templates_keep_public_repos_hosted(self):
        templates = [*ROOT.glob('pr-standards-templates/*.yml'),
                     ROOT / 'repo-standards-templates/repo-standards.yml']
        selector = "${{ github.event.repository.private == true && 'boat' || 'ubuntu-latest' }}"
        for path in templates:
            self.assertIn(f'runs-on: {selector}', path.read_text(), path)
        for path in ROOT.glob('.github/workflows/*.yml'):
            text = path.read_text()
            expected = 'runs-on: ubuntu-latest'
            if path.name in frozenset({'tsc-rs-fleet-rollout.yml', 'deps-fleet-rollout.yml'}):
                # Manual fleet rollouts run on boat, not GitHub-hosted ubuntu.
                self.assertIn('  workflow_dispatch:', text)
                self.assertNotIn('  pull_request:', text)
                self.assertNotIn('  push:', text)
                self.assertIn("if: github.ref == 'refs/heads/main' && github.repository_owner == 'itsryanarmani'", text)
                expected = 'runs-on: self-hosted'
            for line in text.splitlines():
                if line.strip().startswith('runs-on:'):
                    self.assertEqual(line.strip(), expected, path)

    def test_fanout_uses_visibility_in_both_shapes(self):
        subprocess.run(['git', 'init', '-q', str(self.base)], check=True)
        for preview in (False, True):
            if preview:
                path = self.base / '.github/workflows/worker-preview.yml'
                path.parent.mkdir(parents=True)
                path.write_text('name: preview\n')
            output = self.run_tool('fanout-api-gate', str(self.base), '--spec', 'openapi.json')
            self.assertIn("runs-on: ${{ github.event.repository.private == true && 'boat' || 'ubuntu-latest' }}", output)
            self.assertNotIn(LEGACY, output)
            self.assertIn('needs: lifecycle' if preview else "github.ref == 'refs/heads/main'", output)


if __name__ == '__main__':
    unittest.main()
