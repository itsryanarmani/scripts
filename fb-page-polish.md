# fb-page-polish

`fb-page-polish` brands a Facebook Page that already exists: profile picture,
cover photo, bio, and website link. Use it after [`fb-page`](fb-page.md)
creates the Page. The script holds no owner name, Page ID, site, or token.

```sh
fb-page-polish assets --spec spec.json --assets-dir ./page-assets
FB_OWNER_NAME="<your profile name>" fb-page-polish apply --spec spec.json --assets-dir ./page-assets
```

- `assets` writes `<slug>/profile.png` (1024x1024, logo inside the circle crop)
  and `<slug>/cover.png` (1640x720, logo left, name and bio right, inside the
  area that desktop and mobile crops keep). It is local only and needs Pillow
  (`python3 -m pip install Pillow`). An SVG logo also needs `rsvg-convert`
  (`brew install librsvg` or `apt install librsvg2-bin`).
- `apply` sets the four parts in the logged-in Chrome and prints one JSON line
  per Page. It needs the `browse` CLI paired with that Chrome (`browse install`).
  Each step is one `browse execute -s <session> --file` call. `fb-page` still
  uses the old `browser-personal` shell function, which no longer works.

`apply` flags: `--session` (`FB_POLISH_SESSION`, default `personal`), `--stage-dir`
(default `/tmp/fb-page-polish`), `--parts` (default `cover,profile,bio,website`).
## Spec

```json
{"pages": [{"name": "Example Sheds", "about": "Sturdy backyard sheds, built to order.",
  "website": "https://example.test", "logo": "brand/logo.svg", "color": "#2f5d50",
  "link": "https://www.facebook.com/profile.php?id=<page id>", "slug": "example-sheds"}]}
```

`about` is the bio and the cover line: 101 characters or fewer, the Facebook
limit. `website` starts with `https://`. `logo` is SVG or PNG, relative to the
spec. `color` is `#rrggbb`. `link` is the Page profile link (`apply` only).
`slug` is optional. A wrong field stops the run before any work.

## Safe order

1. Switch to the personal profile.
2. Open the Page link and press **Switch Now**.
3. Cover: **Add cover photo** > **Upload photo** > **Save changes**.
4. Profile: **Profile picture actions** > **Choose profile picture** > **Save**.
5. Bio: **About** > **About you** > **Save**.
6. Website: **About** > **Links** > **Websites, blogs, portfolios** > **Save**.
7. Switch to the personal profile again, even when a step failed.

A part that has a value is skipped. The profile picture has no "set" sign, so
`apply` always uploads it and reports `uploaded, verify by screenshot`.

## Traps

- The browse sandbox reads files only under `/tmp`, so `apply` copies the images
  to `--stage-dir` and refuses one outside `/tmp`. The sandbox cannot set
  cookies for other hosts, and `files.write` needs `files.dir`.
- A failed run leaves Chrome acting as the Page. The next Page then looks like a
  visitor view with no controls. `apply` switches back first and last, and fails
  with `session still acts as a Page` when that does not work.
- "Welcome to your new Page" blocks clicks until **Use Page**. Each step presses it.
- Facebook ignores clicks on a hidden tab, so each step brings the tab to the
  front. Menu items need an in-page `element.click()`.
- `page.goto` with the default load wait timed out. Steps use
  `waitUntil: "domcontentloaded"` with a 60 s timeout.
- Selectors use Facebook's page text. When a label changes, the step fails with
  `Control not found: <name>`. Fix the label in `STEPS`.
- Check the cover with `Edit cover photo`. Other text gave a false failure.
- Meta's public picture endpoint shows a silhouette for a real photo. Use a
  screenshot of the Page instead.
- Meta limits Page creation, not edits. The personal-profile check looks for
  "Friends" in the page text; it is a heuristic, so screenshot the end state.

`apply` never prints raw browser output. An error names only a control this file defines.

## Test

`python3 fb-page-polish.test.py` runs `assets` on a made-up logo, then `apply`
against a fake `browse` on `PATH`. It checks sizes, step order, skips, each
failure mode, and that no secret reaches the output. Needs Pillow and rsvg-convert.
