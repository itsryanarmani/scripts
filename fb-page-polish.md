# fb-page-polish

`fb-page-polish` brands a Facebook Page that already exists: profile picture,
cover photo, bio, and website link. It also publishes text posts as the Page,
hides Facebook's automatic photo posts, and counts the posts. Use it after [`fb-page`](fb-page.md)
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

## Posts

```sh
FB_OWNER_NAME="<your profile name>" fb-page-polish post --spec spec.json --posts posts.json --approved
FB_OWNER_NAME="<your profile name>" fb-page-polish hide-autoposts --spec spec.json
fb-page-polish verify --spec spec.json --posts posts.json
```

The posts file lists text posts in posting order. `page` is a spec slug:

```json
{"posts": [{"page": "example-sheds", "text": "Our cedar sheds now ship with a ten year roof warranty.\nAsk us how."}]}
```

Each post has a key: its first line, with whitespace normalised, cut to 45
characters. A key under 20 characters, a key inside the Page name or bio, or
two posts with one key for the same Page stop the run before any work.

- `post` publishes each text as the Page. The Page is the author, not the
  owner. Posts are public, so `post` refuses to run without `--approved`.
  Pass it only after the owner approved every text. Before it posts, `post`
  counts each key on the Page. A key seen once is skipped as already posted.
  A key seen twice or more is skipped and fails the run. After each post,
  `post` counts the key again and reports `posted` only for exactly one.
  Flags: `--settle` (seconds before each Post click, default 6) and `--tries`
  (Post clicks, default 4).
- `hide-autoposts` hides the "updated their profile picture" and "updated
  their cover photo" posts that Facebook publishes by itself. It repeats
  until none are left, at most `--max-rounds` (default 10) per Page.
- `verify` is read-only. It counts each key on the Page after `--scrolls`
  scrolls (default 6, also used by `post` and `hide-autoposts`).
  Exactly 1 is `ok`, 0 is `missing`, 2 or more is `doubled`. Any problem
  exits 1. It does not need `FB_OWNER_NAME`.

### Post order

1. Switch to the personal profile, and count the keys.
2. Open the Page link and press **Switch Now**. The composer then shows the
   Page as the author, with the audience Public.
3. Wait up to 30 s for the **What's on your mind?** box, then click it.
4. Type the text and press **Next**.
5. Wait `--settle` seconds, press **Post**, and repeat until the dialog closes.
6. Count the key again.
7. Switch to the personal profile again, even when a step failed.

### Post traps

- The final **Post** button is not ready right after **Next**. A click that
  fires too early publishes nothing and gives no error. Three posts were lost
  this way. `post` waits, then clicks again until the dialog closes.
- A fixed wait sometimes found no composer. `post` waits for the box with
  `waitForFunction` and fails with `Control not found: What's on your mind? box`.
- A 25-character key matched the Page name and gave a false count of 10. Keys
  use 45 characters of the whole first line.
- Six scrolls load only the recent posts. A key from an old post counts 0,
  and `post` would post it again. Raise `--scrolls` for a Page with many posts.
- The count reads the text of the whole page, not post boxes. A comment that
  quotes a key also counts.
- Without **Switch Now** the composer posts as the owner. `post` and
  `hide-autoposts` stop with `Switch Now not found` instead.
- The only menu option on an automatic photo post is **Hide from Page**. There
  is no delete and no confirm. `hide-autoposts` finds the header text, climbs
  to the control labelled `Actions for this post by <Page>`, opens it, and
  clicks **Hide from Page**. The photo stays; the post leaves the timeline.
- Admins see `Published by <owner>` and `Comment as <owner>` on Page posts.
  The public never sees these lines, so they do not mean the post is wrong.

## Test

`python3 fb-page-polish.test.py` runs `assets` on a made-up logo, then `apply`
against a fake `browse` on `PATH`. It checks sizes, step order, skips, each
failure mode, and that no secret reaches the output. Needs Pillow and rsvg-convert.

`python3 fb-page-polish-posts.test.py` runs `post`, `hide-autoposts` and
`verify` against a fake `browse` that answers each step from a plan. It checks
the Post retry, the composer that is missing, the skip of a post already on the
Page, the session left as a Page, a doubled post, and a Page with no automatic
posts. It prints the step order of each case, so its output is the transcript.
The fake cannot run Facebook's page, so only a live run proves the selectors.
