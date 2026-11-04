#!/usr/bin/env python3
"""Offline tests for social-profile: no network, no Playwright, no real account."""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

PATH = str(Path(__file__).with_name('social-profile'))
spec = importlib.util.spec_from_loader('social_profile', importlib.machinery.SourceFileLoader('social_profile', PATH))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)
try:
    from PIL import Image
except ImportError:
    Image = None
X_ENV = {'X_API_KEY': 'key-abc', 'X_API_SECRET': 'xsecret-123', 'X_ACCESS_TOKEN': 'tok-abc', 'X_ACCESS_TOKEN_SECRET': 'toksecret-abc'}


def run(argv, env=None):
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'SOCIAL_PROFILE_CONFIG': f'{d}/no.toml', **(env or {})}, clear=True), \
            mock.patch.object(sp.shutil, 'which', return_value=None), contextlib.redirect_stdout(out), \
            mock.patch('urllib.request.urlopen', side_effect=AssertionError('network call')):
        code = sp.main(argv)
    return code, out.getvalue()


class Tests(unittest.TestCase):
    def test_args(self):
        self.assertEqual(sp.parse_args(['set', '--platform', 'all', '--bio', 'hi']).platform, 'all')
        self.assertRegex(run(['list'])[1], r'github\s+api\s+bio\s+GITHUB_TOKEN')
        for argv in (['set', '--platform', 'x'], ['set', '--platform', 'myspace', '--bio', 'x'],
                     ['set', '--platform', 'x', '--avatar', '/nope.png']):
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
                sp.parse_args(argv)
            self.assertEqual(cm.exception.code, 2)

    @unittest.skipUnless(Image, 'Pillow not installed')
    def test_crop_resize_exact(self):
        with tempfile.TemporaryDirectory() as d:
            for src_size in ((3000, 1000), (600, 2000)):  # wide, tall
                Image.new('RGB', src_size).save(f'{d}/in.png')
                for size in ((400, 400), (1500, 500), (2560, 1440)):
                    with Image.open(sp.prep_image(f'{d}/in.png', size, f'{d}/out.jpg')) as im:
                        self.assertEqual(im.size, size)

    def test_bio_limit(self):
        self.assertEqual(sp.check_bio('x', 'a' * 160), '160/160 chars')
        with self.assertRaisesRegex(RuntimeError, '161 chars; x allows 160'):
            sp.check_bio('x', 'a' * 161)
        code, out = run(['set', '--platform', 'tiktok', '--bio', 'a' * 81, '--dry-run', '--browser-profile', '/p'])
        self.assertEqual((code, out.split()[:2]), (1, ['FAIL', 'tiktok']))

    def test_oauth1_twitter_documented_vector(self):
        header = sp.oauth1_header(
            'POST', 'https://api.twitter.com/1.1/statuses/update.json',
            {'include_entities': 'true', 'status': 'Hello Ladies + Gentlemen, a signed OAuth request!'},
            'xvz1evFS4wEEPTGEFPHBog', 'kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw',
            '370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb', 'LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE',
            nonce='kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg', timestamp=1318622958)
        self.assertIn('oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"', header)

    def test_config_0600_and_env_wins(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'SOCIAL_PROFILE_CONFIG': f'{d}/c.toml'}, clear=True):
            Path(d, 'c.toml').write_text('[github]\nGITHUB_TOKEN = "from-file"\n')
            Path(d, 'c.toml').chmod(0o640)
            with self.assertRaisesRegex(SystemExit, 'chmod 600'):
                sp.load_config()
            Path(d, 'c.toml').chmod(0o600)
            self.assertEqual(sp.creds('github', sp.load_config())['GITHUB_TOKEN'], 'from-file')
            os.environ['GITHUB_TOKEN'] = 'from-env'
            self.assertEqual(sp.creds('github', sp.load_config())['GITHUB_TOKEN'], 'from-env')

    def test_dry_run_offline_and_all_skips_unconfigured(self):
        with tempfile.TemporaryDirectory() as d:
            argv = ['set', '--platform', 'all', '--bio', 'hello', '--dry-run']
            if Image:
                Image.new('RGB', (900, 300)).save(f'{d}/a.png')
                argv += ['--avatar', f'{d}/a.png']
            code, out = run(argv, X_ENV)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r'OK +x +dry-run, would set: .*bio 5/160 chars')
        self.assertRegex(out, r'SKIP bluesky +not configured: set BSKY_HANDLE')
        self.assertRegex(out, r'SKIP instagram +not configured')
        code, out = run(['set', '--platform', 'mastodon', '--bio', 'hi', '--dry-run'])
        self.assertEqual((code, out.split()[:2]), (1, ['FAIL', 'mastodon']))
        with mock.patch.object(sp, 'set_x', side_effect=RuntimeError('boom xsecret-123')):
            code, out = run(['set', '--platform', 'x', '--bio', 'hi'], X_ENV)
        self.assertEqual((code, 'boom ***' in out, 'xsecret-123' in out), (1, True, False))


if __name__ == '__main__':
    unittest.main()
