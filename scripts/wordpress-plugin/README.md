# wordpress-plugin — build, test, and submit a WordPress plugin

A WordPress plugin is plain PHP with a header-comment manifest — no build step,
no push CLI. Submission is a manual zip upload; hosting is SVN (trunk + tags).
This is the playbook: from `integrations/wordpress-plugin/` to listed in the
WordPress.org directory, plus the traps that each cost a manual-review
round-trip. The concept-level skill is `wordpress-plugin` in `itsryanarmani/skills`.

## Flow

```bash
cd integrations/wordpress-plugin   # plugin source (main .php, includes/, readme.txt)

# Local dev — wp-env maps this folder as a plugin (needs .wp-env.json)
npm install -g @wordpress/env
npx wp-env start                   # open the printed URL → Plugins → Activate

# Pre-flight the same greps the reviewers run
composer global require wp-coding-standards/wpcs
phpcs --standard=WordPress .

# Build the zip reviewers see (respect .distignore; folder name = slug)
rsync -a --exclude-from .distignore . /tmp/<slug>/
cd /tmp && zip -r <slug>.1.0.0.zip <slug>
```

Submission (manual review — days–weeks; each bounce re-queues):

```bash
# 1. Upload the zip at wordpress.org/plugins/developers/add/ → request slug <slug>.
#    Wait for the approval email. Do NOT touch SVN before approval.
# 2. First import (trunk = the snapshot the directory serves for development):
svn checkout https://plugins.svn.wordpress.org/<slug>/ <slug>-svn
rsync -a --delete --exclude-from integrations/wordpress-plugin/.distignore \
  integrations/wordpress-plugin/ <slug>-svn/trunk/
cd <slug>-svn && svn add trunk --force && svn ci -m "Initial commit of 1.0.0"

# 3. Tag it — required, or readme.txt "Stable tag: 1.0.0" resolves to nothing:
svn cp trunk tags/1.0.0 && svn ci -m "Tagging 1.0.0"

# 4. Plugin-page assets live in /assets (sibling of trunk/), NOT in trunk:
#    assets/icon-128x128.png assets/icon-256x256.png
#    assets/banner-772x250.png assets/banner-1544x500.png assets/screenshot-1.png
svn add assets --force && svn ci -m "Plugin page assets"
```

Later releases: bump `Version` in the main file AND `Stable tag` in readme.txt,
add a `== Changelog ==` entry, rsync → trunk, `svn ci`, `svn cp trunk tags/x.y.z`,
`svn ci`. No re-review for routine updates.

## Traps (each = one manual-review round-trip)

- **Every `$_POST`/`$_GET` read needs nonce + capability + sanitize** — the #1
  bounce. `wp_unslash()` BEFORE `sanitize_text_field()`; escape
  (`esc_html`/`esc_attr`/`esc_url`) at the echo, not at assignment.
- **`Stable tag` = header `Version` = an existing `tags/x.y.z`** — mismatch and
  the directory serves the wrong code, or none.
- **Assets in `/assets`, not trunk** — icons/banners committed to trunk never
  render on the plugin page.
- **Folder name, `Text Domain`, and prefixes must match the APPROVED slug** —
  rename everywhere if your requested slug was taken.
- **No remote-loaded JS/CSS, no bundled secrets, no telemetry without consent** —
  calling your documented API with a user-supplied key is fine; CDN scripts,
  `eval`, and minified-only JS are instant rejects.
- **Prefix every function/class/option; `defined( 'ABSPATH' ) || exit;` in every
  PHP file.** `uninstall.php` must delete the plugin's options and meta.
- **`save_post` fires on autosave/revision** — guard with `wp_is_post_autosave()`
  / `wp_is_post_revision()` before calling your API.
- **readme.txt `Tested up to` ≤ current WP release** — a future version warns, a
  stale one sinks search rank.

## Files

`example.php` (next to this README) — the smallest real wiring: header manifest,
a sanitized Settings-API field for the team API key, `save_post` →
`wp_remote_request` to your API, and a nonce-protected form handler. Copy it as
a starting point and rename every `your_product` prefix to your slug.
