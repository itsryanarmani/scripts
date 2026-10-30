# social-profile

Set your avatar, banner and bio on many social platforms with one command. API
platforms use stdlib `urllib`. Browser platforms drive a Playwright profile you
have already signed in to. Images are center-cropped to each platform's aspect
ratio, then resized.

```sh
pip install pillow                                  # required
pip install playwright && playwright install chromium   # only for browser platforms
social-profile list
social-profile set --platform all --avatar me.png --banner wide.png --bio "Builder." --dry-run
social-profile set --platform instagram --avatar me.png --browser-profile ~/.cache/sp-chrome --headful
```

`all` runs every configured platform, prints `OK`/`SKIP`/`FAIL` for each and exits 1 if any fail.
`--dry-run` writes the resized images, checks the bio length and makes no network calls.

| Platform | Method | Avatar | Banner | Bio limit | Env vars |
|---|---|---|---|---|---|
| x | api | 400x400 | 1500x500 | 160 | `X_API_KEY` `X_API_SECRET` `X_ACCESS_TOKEN` `X_ACCESS_TOKEN_SECRET` |
| bluesky | api | 1000x1000 | 3000x1000 | 256 | `BSKY_HANDLE` `BSKY_APP_PASSWORD` (`BSKY_PDS`) |
| mastodon | api | 400x400 | 1500x500 | 500 | `MASTODON_INSTANCE` `MASTODON_TOKEN` |
| github | api | no API | none | 160 | `GITHUB_TOKEN`, else `gh auth token` |
| reddit | api, unverified | browser only, not automated (256x256) | browser only, not automated (1920x384) | 200 | `REDDIT_CLIENT_ID` `REDDIT_CLIENT_SECRET` `REDDIT_USERNAME` `REDDIT_PASSWORD` |
| youtube | api | no API (800x800) | 2560x1440 | 1000 | `YOUTUBE_ACCESS_TOKEN` |
| instagram | browser | 320x320 | none | 150 | browser profile |
| linkedin | browser | 400x400 | 1584x396 | 220 (headline) | browser profile |
| tiktok | browser | 200x200 | none | 80 | browser profile |
| facebook | browser | 720x720 | 1640x624 | 101 | browser profile |
| pinterest | browser | 280x280 | 1600x900 | 500 | browser profile |
| tumblr | browser, unverified | 512x512 | 3000x1055 | 500 | browser profile, `TUMBLR_BLOG` |

## Setup

- **x**: create a developer app with Read and Write permission, then generate the user access token and secret. Uses OAuth 1.0a.
- **bluesky**: Settings → App passwords. Never use your main password.
- **mastodon**: Preferences → Development → New application with the `write:accounts` scope.
- **github**: a fine-grained token with the Profile write permission, or `gh auth login`.
- **reddit** (unverified): create a "script" app at reddit.com/prefs/apps. The bio goes to `public_description` of `u_<name>` through `/api/site_admin`.
- **youtube**: in the [OAuth Playground](https://developers.google.com/oauthplayground), authorize `https://www.googleapis.com/auth/youtube` and copy the access token. It expires after an hour.
- **browser platforms**: run once with `--headful` and sign in by hand in that profile. The tool never types a password. If it lands on a login page it fails with "not signed in in this browser profile". These flows are **best-effort, selectors may break**. Fix them in the `BROWSER` dict.

**Config file.** Env vars win over `~/.config/social-profile/config.toml` (path override: `SOCIAL_PROFILE_CONFIG`).

```toml
[bluesky]
BSKY_HANDLE = "you.example.com"
BSKY_APP_PASSWORD = "xxxx-xxxx-xxxx-xxxx"
```

**Security.** The tool stores no passwords; browser sign-in lives only in your Playwright profile.
It refuses to read a config file whose mode is not `0600`. Secrets are never printed and error text
is redacted. Never commit tokens or the config file.
