# agent-browser — isolated work/personal browser profiles

Keep separate automation browsers for separate contexts — for example one for
work and one for personal. Each runs on its own profile. They never mix. And you
avoid the repeated Chrome "Allow remote debugging" prompt.

The concept-level skill is `agent-browser-profiles` in `itsryanarmani/skills`.

## Start with AUTO_CONNECT=0

Set this in your shell config first:

```sh
export AGENT_BROWSER_AUTO_CONNECT=0
```

With `AGENT_BROWSER_AUTO_CONNECT=1`, `agent-browser` attaches every call to your
daily Chrome and ignores `--profile`. Chrome 136 then shows the "Allow remote
debugging" prompt over and over, and automation lands in the wrong profile. Set
it to `0` to make `agent-browser` isolated by default. Opt into attaching with a
dedicated command when you need it.

## Two ways to run an automation browser

**1. Fresh isolated profiles.** Each is a clean Chrome-for-Testing profile. You
log in once. The login persists. No prompts. Use this for a site you can sign
into again.

**2. Real Chrome on a clone.** The real Chrome binary runs on a copy of one real
profile. You keep your existing logins. No prompt. This is what
`browser-clone-setup.sh` builds. Use one port per clone.

## Build a clone

List your Chrome profile directory names first. They look like `Default`,
`Profile 1`, `Profile 2`:

```sh
ls "$HOME/Library/Application Support/Google/Chrome"
```

Then clone one profile:

```sh
./browser-clone-setup.sh work --source-profile "Profile 1" --port 9333
./browser-clone-setup.sh personal --source-profile "Profile 2" --port 9334
```

The script prints the exact launch and connect commands when it finishes. It
copies a session subset only (Cookies, Local Storage, IndexedDB, Login Data,
Network, Preferences, Web Data) plus the top-level `Local State`, which holds the
cookie key. It skips caches. Your real profile stays read-only. Re-run the same
command to refresh a clone with your latest logins.

## Example zsh functions

Add functions like these to your shell config. Change the profile names and
ports to match your machine.

```sh
export AGENT_BROWSER_AUTO_CONNECT=0

# Fresh, isolated Chrome-for-Testing profiles. Log in once; the login persists.
browser-work()     { AGENT_BROWSER_AUTO_CONNECT=0 agent-browser --profile "$HOME/.agent-browser/profiles/work"     --session work     --headed "$@"; }
browser-personal() { AGENT_BROWSER_AUTO_CONNECT=0 agent-browser --profile "$HOME/.agent-browser/profiles/personal" --session personal --headed "$@"; }

# Opt into driving your daily Chrome (may show the Chrome-136 prompt).
browser-attach()   { AGENT_BROWSER_AUTO_CONNECT=1 agent-browser "$@"; }

# Real Chrome on a clone: real logins, no prompt. One port per clone.
_browser_real() {  # $1=clone-name  $2=port
  local target="$1" port="$2"
  local clone="$HOME/.agent-browser/real-profiles/$target"
  if ! lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    [ -d "$clone" ] || { echo "run browser-clone-setup.sh first"; return 1; }
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --user-data-dir="$clone" \
      --remote-debugging-port="$port" \
      --no-first-run --no-default-browser-check >/dev/null 2>&1 &
    sleep 2
  fi
  agent-browser connect "$port"
}
browser-work-real()     { _browser_real work 9333; }
browser-personal-real() { _browser_real personal 9334; }
```

These `browser-*` names are browser profiles. They are not the same thing as
per-account Claude Code logins that may share the same names.

## Why the clone works, and its limits

- **Keychain.** Chrome-for-Testing uses a separate macOS Keychain entry ("Chrome
  for Testing Safe Storage"). Cookies from your real Chrome are encrypted with
  the "Chrome Safe Storage" key, so they do not decrypt inside
  Chrome-for-Testing. Do not copy cookies into it. The clone works because real
  Chrome shares the one "Chrome Safe Storage" key across any `--user-data-dir`.
- **Chrome 136.** Chrome 136 blocks remote debugging on the Default profile and
  ignores the port there. Launch real Chrome with the debug flag on a distinct
  `--user-data-dir` to stay prompt-free. The prompt fires only when you attach to
  a running user session.
- **Device-bound cookies (DBSC).** Google binds web session cookies to the
  device. So Google-owned sites, such as Gmail, can still need one sign-in inside
  the clone. Other sites usually carry over.

## Separation contract

Each clone holds exactly one source profile, normalized to `Default`. The script
rewrites the clone's `Local State` to list only `Default`. So one clone never
sees another clone's profiles. Give each clone its own directory and its own
port.
