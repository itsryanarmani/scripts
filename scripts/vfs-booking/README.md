# vfs-booking — VFS Global visa portal browser automation

Reusable browser-automation helper for visa.vfsglobal.com. Drives the portal
using `agent-browser` CLI attached over Chrome DevTools Protocol (CDP) to a
real, already-running Chrome browser.

This script handles Cloudflare JS challenges, Turnstile widgets, sticky
overlays, and custom combobox dropdowns that standard automation libraries
struggle with.

## CRITICAL: No payment automation

**This script does NOT and must NOT automate payment.** Attempting to automate
the payment step leaves bookings stuck in "Payment Processing" state and the
booking is silently orphaned from the dashboard — it vanishes completely.

The script stops before the payment step and prints a loud message telling you
to complete payment by hand in a normal, non-automated browser window. This is
a safety feature, not a limitation.

## Prerequisites

1. **Chrome with remote debugging enabled.** Launch Chrome with:
   ```sh
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
     --user-data-dir="$HOME/.agent-browser/real-profiles/vfs" \
     --remote-debugging-port=9334 \
     --no-first-run --no-default-browser-check
   ```
   See `scripts/agent-browser/README.md` for profile cloning and
   setup details.

2. **agent-browser CLI.** Install via Claude Code skill `agent-browser` or
   directly from `itsryanarmani/skills`.

3. **Environment variables.** Set only the vars required for your command
   (see below).

## Usage

### check / status — Report active applications

Query the dashboard to see whether any booking currently exists.

```sh
VFS_CHROME_PORT=9334 vfs-booking check
```

Output: Reports `Active application(s) found` or `No active applications found`.
Exit code 0 on success, 1 on error.

This is the fast path for "did my booking survive?" — essential because VFS
bookings mysteriously disappear if automation touches the payment step.

### login — Sign in to VFS account

```sh
VFS_EMAIL="alice@example.com" \
VFS_PASSWORD="secret" \
VFS_CHROME_PORT=9334 \
vfs-booking login
```

Environment variables:
- `VFS_EMAIL`: Your VFS account email address.
- `VFS_PASSWORD`: Your VFS account password.
- `VFS_CHROME_PORT`: CDP port. Default 9334.

The script:
1. Loads the login page.
2. Waits for Cloudflare JS challenge to settle (~5 seconds).
3. Waits for Turnstile widget to auto-solve.
4. Fills in email and password.
5. Submits the form.
6. Waits for redirect to dashboard.

Exits with code 0 on success, nonzero on error.

### slots — Check appointment slot availability

```sh
VFS_CENTRE="Tokyo" \
VFS_CATEGORY="Visitor" \
VFS_SUBCATEGORY="Short-term" \
VFS_CHROME_PORT=9334 \
vfs-booking slots
```

Environment variables:
- `VFS_CENTRE`: Application centre name (required).
- `VFS_CATEGORY`: Visa category (optional).
- `VFS_SUBCATEGORY`: Sub-category (optional).
- `VFS_CHROME_PORT`: CDP port. Default 9334.

The script:
1. Loads the booking form.
2. Selects the application centre.
3. Selects category and sub-category if provided.
4. Reports slot availability.

Output:
- `Appointments available` if real appointment slots exist.
- `Appointments unavailable (waitlist only)` if only waitlist is available.

Exit code 0 for available, 1 for unavailable, nonzero for error.

## Technical details

### Why this script exists

1. **New Playwright/Chromium browsers are blocked.** Fresh browser instances
   get HTTP 403 (`{"code":"403201"}`) before any page renders. CDP connection
   to a real Chrome profile with existing logins works around this.

2. **Cloudflare JS challenge.** The portal loads a JS challenge that redirects
   after ~5 seconds. Standard polling (checking `document.readyState`) fails
   because the page is "complete" even during the redirect. This script polls
   for a known marker string instead.

3. **Turnstile widget.** The login form has a Cloudflare Turnstile CAPTCHA
   that auto-solves. No manual solve is needed; the script waits for success.

4. **Sticky overlays.** A navbar and loading spinner (`div.ngx-overlay`) cover
   elements. Normal click automation fails with "is covered by". The script
   uses XPath and JS `click()` to bypass.

5. **Custom combobox dropdowns.** The portal uses Material Design comboboxes
   that render options in a portal DOM, outside the normal flow. Option text
   does not appear in `document.body.innerText`. This script uses XPath to find
   and read option elements directly.

### Helpers

The script exports these shell helpers for reuse:

- **`js_click_text(text)`** — Click by text using XPath + JS, bypassing
  overlays and covered-by errors.
- **`wait_for_no_overlay()`** — Poll until `.ngx-overlay.loading-foreground`
  is gone (default timeout 30s).
- **`wait_for_page_settle(marker)`** — Poll `agent-browser get text body`
  until it contains marker string (default timeout 60s for Cloudflare).
- **`list_options()`** — Read all options in an open dropdown as JSON array.
- **`select_option(text)`** — Click an option by partial text match.

### Portal constraints

- **Address fields reject commas.** Normalize to spaces.
- **Phone fields accept digits only.** Strip `+`, spaces, dashes.
- **Dates are DD/MM/YYYY.** Not ISO 8601 or US format.
- **Portal has 5-step wizard.** Appointment Details → Your Details → Book
  Appointment → Services → Review. Then payment (not automated).
- **eForm is a separate 6-page flow.** Eligibility Criteria → Passport Details
  → Application Details → Travel Details → Accommodation Details → Additional
  Details.

## Troubleshooting

### "Failed to connect to CDP browser"

Chrome is not running with `--remote-debugging-port=9334`. Check:
`lsof -iTCP:9334 -sTCP:LISTEN` or set `VFS_CHROME_PORT` to match your port.

### "Page did not settle after 60s"

Cloudflare challenge stuck. Is Chrome responsive? Network working?

### "Overlay did not clear within 30s"

Loading spinner stuck. Refresh or increase `TIMEOUT_GENERAL` in script.

## No PII in this script

All personal data (email, password, names, dates, addresses) comes from
environment variables that you provide at runtime. The script file itself
contains zero real data — only obvious placeholders.

For public distribution, never commit `.env` files with real values. Always
use examples like `VFS_EMAIL=user@example.com` and `VFS_PASSWORD=`.

## See also

- `scripts/agent-browser/` — Profile setup and CDP connection details.
- `itsryanarmani/skills` — `agent-browser-profiles` skill for full CDP workflow.
- VFS Global portal: https://visa.vfsglobal.com
