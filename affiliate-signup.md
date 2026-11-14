# Affiliate network signup

Use one account per network for every site you own. Do not open an account per
site. A network asks for one site URL at signup. Add the other sites inside the
account after approval.

This runbook covers the networks an agent has signed up to first-hand: Awin,
CJ and Impact. Add a network here only after someone has logged in to it.

## Before you start

- Ask the owner for the legal name, country, mailing address and phone number.
  Do not invent any of them. Impact and most other networks require a phone.
- Pick one live site as the signup URL. Check that it returns 200.
- Use a mailbox you can read from a command line. Every network sends a
  verification email.
- Generate one password per network. Store it in a mode 600 env file that Git
  ignores. Never print it, never put it in chat, never put it in a command that
  logs. To hand a password to a person, copy it to the clipboard and clear the
  clipboard after two minutes.
- Do banking and tax pages by hand. Ask the owner for those numbers when the
  network asks. Do not guess them.
- Ask the owner before you accept a legal agreement for them. Record the
  answer. An agreement binds the owner, so an approval for one network does not
  cover the next.

## Which browser to use

An extension-driven browser that attaches to the owner's own Chrome drops its
debugger on login pages. A password manager or another extension injects a
frame, and every call then fails with `Target page, context or browser has been
closed`. Use a clean automation browser with its own profile for logins. It
has no extensions, and the same script runs without a failure.

Snapshot, fill by reference, then check that the button is enabled before you
click. A fill on an unbound field and a click on a disabled button both print
success.

## Awin

Sign up at `ui.awin.com/publisher-signup/en/awin/step1`.

| Step | Asks for | Notes |
|------|----------|-------|
| 1 Account | Company name, tax residency, first and last name, email twice, password twice | The company name needs three or more characters. An individual uses their own name. |
| 2 Promotional type | Primary region, one or more types | You must also mark one type as primary, or the form says "Please select a primary promotional type". |
| 3 Promotional space | Site URL, a description of up to 255 characters, one or more sectors | A site with no sector fails with "Please categorize your website". |
| 4 Verification | A click on the activation link in the email | The link comes from `ui.awin.com/user-signup/confirmation/code/...`. |

Each step takes 15 to 25 seconds to answer. Wait, then read the page again. A
second click while the first is pending only adds noise.

### The false "URL needs to be publicly accessible" error

Step 3 can answer "The URL needs to be publicly accessible" for a site that
returns 200 to every client you try. Cloudflare's own request log showed no
request from Awin during the attempts, so the site was never blocked. The
likely cause is reCAPTCHA v3 scoring the automated browser. A person clicking
Next passed the same form on the same URL. Do not change firewall rules for
this error until the log shows a blocked request from the network.

To prove the point, query the zone's request log by network number and drop your
own network and Cloudflare's own traffic (AS13335). A real validator then shows
up as a row, or it does not.

### After approval

Approval can arrive within minutes. Two emails follow: one to activate the
email address, one to say the application is approved. Activate first, then sign
in. The dashboard asks you to turn on two-step verification.

1. Choose set up. Awin emails "Just making sure it's you". Open the link in it.
2. The page shows a QR code and no text secret. Screenshot the QR code and
   decode it. On macOS, the Vision framework reads it with a few lines of Swift
   (`VNDetectBarcodesRequest` with the `.qr` symbology). Write the result to a
   private file, not to the terminal.
3. Run `./totp save accounts.env AWIN < uri.txt`, then delete `uri.txt`.
4. Enter `./totp code accounts.env AWIN` in the one-time code box.
5. Awin then shows a recovery code. Save it in the same env file under its
   own key before you tick "I have safely recorded this code".

To add the owner's other sites, open Account, Profile, Promotional Spaces, then
"+ Add Content Site". The form takes a URL, a description and a sector. The
sector checkbox sits inside a clickable label. A click on the label text does
not tick it. Run `check` on the checkbox itself.

## CJ

Sign up at `signup.cj.com/member/signup/publisher/`. It redirects to
`public.cj.com/signup/publisher`.

1. Step 1 asks for language, country, email, password twice and a reCAPTCHA v2
   checkbox. The checkbox passed with one click and no image challenge. The
   country box is a custom list: click it, type the name, press Enter.
2. CJ emails a confirmation link. The link goes through `email.cj.com`.
3. The link opens the agreements page. It asks for an age certification and a
   certification of authority, then three agreements: the publisher agreement,
   the software policy and the privacy policy.
4. Each Accept button stays disabled until you open that agreement's link, which
   opens a new tab. Open the link first, then click Accept. Ticking the two
   boxes does not enable the buttons.
5. Continue to account. CJ redirects to a sign-in page at `signin.cj.com`.

The legal tabs and the sign-in page both make an extension-driven browser drop
its debugger. Sign in by hand, or use the clean browser.

## Impact

Sign up at `app.impact.com/signup/none/create-new-mediapartner-account-flow.ihtml`.
It offers Google, Apple or email. Choose email to use a generated password.

The email form asks for email, first and last name, username, a password and a
mobile number. The password needs eight characters, one digit and one of
`! @ # $ % & ?`. The phone field is required.

Before you submit, search the mailbox for the network's name. The form can
answer "Looks like you've already signed up with this email". That means an old
account exists, and it may hold warnings, such as a payout problem. Sign in to
it. Do not reset its password without the owner's yes, because that breaks the
password the owner saved.

## Traps that cost the most time

1. A form error can come from the automation and not from the site. Check the
   request log before you touch the site or its firewall.
2. A button that looks active can be disabled. Read the `disabled` property.
3. A network can already know the email. Search the mailbox first.
4. Two-step verification with a QR code and no text secret needs a decode step.
   Keep the secret and the recovery code in the env file, mode 600.
5. A person's click passes a score check that a script can fail.
6. Verification emails arrive within seconds. Search the mailbox by sender and
   the last ten minutes. Open links without printing them, because most are
   single-use sign-in links.

`totp` is documented in `totp.failure-modes.md`.
