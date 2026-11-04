#!/usr/bin/env python3
"""Run ci-runner-indirect on a throwaway repo and check each rewrite and each skip."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "ci-runner-indirect"
STD = "${{ vars.CI_RUNNER || 'boat' }}"
LARGE = "${{ vars.CI_RUNNER_LARGE || 'boat-8' }}"
WORKFLOW = """name: t
on: push
jobs:
  a:
    runs-on: boat
  b:
    runs-on: "boat-8"
  c:
    runs-on: ubuntu-latest # keep comment
  d:
    runs-on: ubuntu-24.04
  e:
    runs-on: macos-latest
  f:
    runs-on: ${{ matrix.os }}
  g:
    runs-on:
      - boat
  h:
    runs-on: ${{ vars.CI_RUNNER || 'boat' }}
  i:
    runs-on: ubuntu-latest
    steps:
      - run: |
          cat <<EOF
          runs-on: boat
          EOF
      - run: |2-
          runs-on: boat
  j:
    runs-on: ubuntu-24.04-arm
"""


def run(repo, *flags):
    return subprocess.run(
        ["python3", str(SCRIPT), *flags, str(repo)], capture_output=True, text=True, check=True
    )


class CiRunnerIndirect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        wf = self.repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        self.file = wf / "t.yml"
        self.file.write_text(WORKFLOW)

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_changes_nothing(self):
        out = run(self.repo)
        self.assertEqual(self.file.read_text(), WORKFLOW)
        self.assertIn("\t5", out.stdout)

    def test_write_rewrites_only_literal_linux_labels(self):
        run(self.repo, "--write")
        text = self.file.read_text()
        self.assertIn(f"  a:\n    runs-on: {STD}\n", text)
        self.assertIn(f"  b:\n    runs-on: {LARGE}\n", text)
        self.assertIn(f"runs-on: {STD} # keep comment", text)
        self.assertIn(f"  d:\n    runs-on: {STD}\n", text)
        self.assertIn(f"  i:\n    runs-on: {STD}\n", text)

    def test_write_leaves_macos_matrix_list_expression_and_block_scalar(self):
        run(self.repo, "--write")
        text = self.file.read_text()
        self.assertIn("runs-on: macos-latest", text)
        self.assertIn("runs-on: ${{ matrix.os }}", text)
        self.assertIn("    runs-on:\n      - boat\n", text)
        self.assertIn("          runs-on: boat\n", text)
        self.assertEqual(text.count("          runs-on: boat\n"), 2)
        self.assertIn("runs-on: ubuntu-24.04-arm", text)

    def test_second_run_is_a_no_op(self):
        run(self.repo, "--write")
        first = self.file.read_text()
        run(self.repo, "--write")
        self.assertEqual(self.file.read_text(), first)


if __name__ == "__main__":
    unittest.main()
