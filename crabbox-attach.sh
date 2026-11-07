#!/usr/bin/env bash
set -euo pipefail

# Warm one Crabbox VM for the current Git worktree.
# Dependencies stay on the VM. The calling wrapper selects CRABBOX_CONFIG.
#
# Canonical source: itsryanarmani/scripts crabbox-attach.sh.
# ~/.local/bin/crabbox-attach.sh is a symlink to it. After a Box exists the
# delta goes through box-fast-attach (~1.5s); the crabbox rsync below only
# runs when the fast path cannot.

WORKTREE_ROOT="$(git rev-parse --show-toplevel)"
MAIN_ROOT="$(git worktree list --porcelain | sed -n 's/^worktree //p' | head -1)"

if [[ "$MAIN_ROOT" == "$WORKTREE_ROOT" ]]; then
  echo "[crabbox-attach] In main repo, skipping."
  exit 0
fi

# A main-repo marker enables new worktrees on this machine. Each worktree
# still receives its own marker so existing worktrees remain explicit.
if [[ ! -f "$WORKTREE_ROOT/.crabbox-enabled" && -f "$MAIN_ROOT/.crabbox-default-on" ]]; then
  echo "[crabbox-attach] .crabbox-default-on detected; enabling this worktree."
  touch "$WORKTREE_ROOT/.crabbox-enabled"
fi

if [[ ! -f "$WORKTREE_ROOT/.crabbox-enabled" && "${CRABBOX:-0}" != "1" ]]; then
  echo "[crabbox-attach] Not enabled, skipping."
  exit 0
fi

# mkdir is an atomic lock on macOS and Linux.
LOCK_DIR="$WORKTREE_ROOT/.crabbox-attach.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  lock_age_secs=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || stat -c %Y "$LOCK_DIR" 2>/dev/null || echo 0) ))
  if (( lock_age_secs > 1200 )); then
    echo "[crabbox-attach] Stale lock (${lock_age_secs}s old), stealing."
    rmdir "$LOCK_DIR" 2>/dev/null || true
    mkdir "$LOCK_DIR"
  else
    echo "[crabbox-attach] Another attach is running, skipping."
    exit 0
  fi
fi

cleanup() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

if ! command -v crabbox >/dev/null 2>&1; then
  echo "[crabbox-attach] crabbox CLI is not installed." >&2
  exit 1
fi

# crabbox shells out to the `box` binary. There is a box() zsh function that
# wraps it, but a function is invisible to a child process, and ~/.zshrc is only
# sourced for interactive shells -- so a script-driven warmup died on
#   ascii-box CLI new failed: exec: "box": executable file not found in $PATH
# Put the real directory on PATH here, where it always applies.
if [[ -d "$HOME/.ascii/bin" ]]; then
  export PATH="$HOME/.ascii/bin:$PATH"
fi

if [[ -z "${CRABBOX_CONFIG:-}" ]]; then
  echo "[crabbox-attach] CRABBOX_CONFIG is not set; using Crabbox defaults." >&2
else
  echo "[crabbox-attach] Using Crabbox config: $CRABBOX_CONFIG"
fi

# Read the provider from the pinned config rather than assuming one. This line
# used to default to `gcp` and pass it as a CLI flag, and a flag overrides the
# config file -- so a personal worktree that correctly pinned personal.yaml
# (provider: ascii-box) still warmed a VM in the Mozilla GCP project. Default to
# ascii-box, which is the personal remote tier; work repos set the variable.
if [[ -z "${CRABBOX_PROVIDER:-}" && -n "${CRABBOX_CONFIG:-}" && -f "${CRABBOX_CONFIG}" ]]; then
  CRABBOX_PROVIDER="$(sed -n 's/^provider:[[:space:]]*//p' "$CRABBOX_CONFIG" | head -1 | tr -d '"'"'"'[:space:]')"
fi
CRABBOX_PROVIDER="${CRABBOX_PROVIDER:-ascii-box}"

# POLICY: crabbox is a PERSONAL-only tool, and personal means ascii.dev.
#
# Work repositories do not use crabbox at all -- not on ascii.dev (a third-party
# provider that must never hold work source) and not on GCP either. So there is
# one legal provider here, and a work repo is simply refused.
#
# Path is not a reliable owner signal: ~/code holds personal repos AND clones of
# Mozilla-Ocho/solo-admin. Ask the git remote who owns the code instead.
REPO_REMOTE="$(git -C "$WORKTREE_ROOT" remote get-url origin 2>/dev/null || true)"

case "$REPO_REMOTE" in
  *Mozilla-Ocho*|*mozilla-ocho*|*mozilla.org*|*moz-ocho*)
    echo "[crabbox-attach] REFUSING: $MAIN_ROOT is a work repo ($REPO_REMOTE)." >&2
    echo "[crabbox-attach] crabbox is personal-only. Work does not use it." >&2
    exit 1
    ;;
  "")
    # No remote tells us nothing, so fall back to the path and treat anything
    # outside the personal trees as work -- leaking work source costs more than
    # a refused personal warmup.
    case "$MAIN_ROOT" in
      "$HOME/Documents/Personal/"*|"$HOME/code/"*|"$HOME/nova-wt/"*|"$HOME/tmp/"*) : ;;
      *)
        echo "[crabbox-attach] REFUSING: $MAIN_ROOT has no remote and sits outside the personal trees." >&2
        echo "[crabbox-attach] crabbox is personal-only. Set a remote or move the repo." >&2
        exit 1
        ;;
    esac
    ;;
esac

if [[ "$CRABBOX_PROVIDER" != "ascii-box" ]]; then
  echo "[crabbox-attach] REFUSING: provider=$CRABBOX_PROVIDER. Personal work runs on ascii.dev only." >&2
  echo "[crabbox-attach] Check CRABBOX_CONFIG and CRABBOX_PROVIDER." >&2
  exit 1
fi

# Warm-start selection.
#
# A named `box env` carries the repo's build variables (TURBO_API, TURBO_TOKEN,
# TURBO_TEAM) and its safety toggles. A named snapshot carries the installed
# dependency tree. Both are keyed off the repo name, so a new repo only has to
# create `box env new <repo>` to opt in.
#
# crabbox itself cannot pass either one: it forwards only -ascii-box-base-url,
# -ascii-box-cli and -ascii-box-workdir. box-warm-shim stands in for the `box`
# binary and injects `--environment` and `--from` on `new`. If the shim is not
# installed we simply start cold, which is what happens today.
REPO_SLUG="$(basename -s .git "${REPO_REMOTE:-}" 2>/dev/null || true)"
export CRABBOX_BOX_ENVIRONMENT="${CRABBOX_BOX_ENVIRONMENT:-$REPO_SLUG}"
export CRABBOX_BOX_SNAPSHOT="${CRABBOX_BOX_SNAPSHOT:-${REPO_SLUG}-ready}"
BOX_WARM_SHIM="${BOX_WARM_SHIM:-$HOME/Documents/Personal/scripts/box-warm-shim}"

# Machine type is provider-specific: e2-standard-2 is a GCP name, `default` is
# the ascii.dev tier. Picking one default for both is how a GCP type leaked into
# an ascii-box call.
if [[ "$CRABBOX_PROVIDER" == "ascii-box" ]]; then
  CRABBOX_TYPE="${CRABBOX_TYPE:-default}"
else
  CRABBOX_TYPE="${CRABBOX_TYPE:-e2-standard-2}"
fi
CRABBOX_TTL="${CRABBOX_TTL:-90m}"
CRABBOX_IDLE="${CRABBOX_IDLE:-30m}"
CRABBOX_MARKET="${CRABBOX_MARKET:-on-demand}"

SLUG_FILE="$WORKTREE_ROOT/.crabbox-slug"
SHARED_SLUG_FILE="$MAIN_ROOT/.crabbox-shared-slug"

PACKAGE_MANAGER=""
if [[ -f "$WORKTREE_ROOT/bun.lock" || -f "$WORKTREE_ROOT/bun.lockb" ]]; then
  PACKAGE_MANAGER="bun"
elif [[ -f "$WORKTREE_ROOT/pnpm-lock.yaml" ]]; then
  PACKAGE_MANAGER="pnpm"
elif [[ -f "$WORKTREE_ROOT/package-lock.json" ]]; then
  PACKAGE_MANAGER="npm"
elif [[ -f "$WORKTREE_ROOT/yarn.lock" ]]; then
  PACKAGE_MANAGER="yarn"
else
  echo "[crabbox-attach] No supported lockfile in $WORKTREE_ROOT; skipping."
  exit 0
fi
echo "[crabbox-attach] Package manager: $PACKAGE_MANAGER"

SLUG=""
SHARED_MODE=0

if [[ -f "$SHARED_SLUG_FILE" ]]; then
  SHARED_SLUG="$(tr -d '[:space:]' < "$SHARED_SLUG_FILE")"
  if [[ -n "$SHARED_SLUG" ]] && crabbox inspect --id "$SHARED_SLUG" >/dev/null 2>&1; then
    SLUG="$SHARED_SLUG"
    SHARED_MODE=1
    echo "[crabbox-attach] Using shared warm box: $SLUG"
  else
    echo "[crabbox-attach] Shared slug is not active; using a per-worktree box."
  fi
fi

if [[ -z "$SLUG" && -f "$SLUG_FILE" ]]; then
  SLUG="$(tr -d '[:space:]' < "$SLUG_FILE")"
  echo "[crabbox-attach] Reusing per-worktree slug: $SLUG"
  if ! crabbox inspect --id "$SLUG" >/dev/null 2>&1; then
    echo "[crabbox-attach] Stored slug is not active; warming a new box."
    rm -f "$SLUG_FILE"
    SLUG=""
  fi
fi

if [[ -z "$SLUG" ]]; then
  echo "[crabbox-attach] Warming a $CRABBOX_PROVIDER box (type=$CRABBOX_TYPE ttl=$CRABBOX_TTL idle=$CRABBOX_IDLE market=$CRABBOX_MARKET)"
  warmup_log="$(mktemp)"
  # --type and --market are GCP-shaped and rejected outright by ascii-box, so
  # build the flag list per provider instead of sending one set to all of them.
  warm_flags=( --provider "$CRABBOX_PROVIDER" --ttl "$CRABBOX_TTL" --idle-timeout "$CRABBOX_IDLE" --keep )
  if [[ -x "$BOX_WARM_SHIM" ]]; then
    warm_flags+=( --ascii-box-cli "$BOX_WARM_SHIM" )
    echo "[crabbox-attach] Warm start: env=$CRABBOX_BOX_ENVIRONMENT snapshot=$CRABBOX_BOX_SNAPSHOT"
  fi
  if [[ "$CRABBOX_PROVIDER" != "ascii-box" ]]; then
    warm_flags+=( --type "$CRABBOX_TYPE" --market "$CRABBOX_MARKET" )
  fi
  if ! crabbox warmup "${warm_flags[@]}" 2>&1 | tee "$warmup_log"; then
    rm -f "$warmup_log"
    echo "[crabbox-attach] Warmup failed." >&2
    exit 1
  fi
  SLUG="$(grep -oE 'slug=[a-zA-Z0-9_-]+' "$warmup_log" | head -1 | cut -d= -f2 || true)"
  rm -f "$warmup_log"
  if [[ -z "$SLUG" ]]; then
    echo "[crabbox-attach] Could not parse the slug from warmup output." >&2
    exit 1
  fi
  echo "$SLUG" > "$SLUG_FILE"
  echo "[crabbox-attach] Recorded slug $SLUG in .crabbox-slug"
fi

RECLAIM_FLAG=""
if (( SHARED_MODE == 1 )); then
  RECLAIM_FLAG="--reclaim"
fi

print_banner() {  # $1 = slug, $2 = remote workdir
  cat <<EOF

============================================================
[crabbox-attach] Box ready: slug=$1
============================================================

  SSH in:
    crabbox ssh --id $1

  Remote workdir:
    $2

  Port-forward a service:
    eval "\$(crabbox ssh --id $1) -L LOCAL_PORT:localhost:REMOTE_PORT -N"

  Stop the box:
    crabbox stop $1

============================================================
EOF
}

# FAST PATH: box-fast-attach seeds in ~1.5s after the first send; the crabbox
# rsync below costs ~50s every time. A Box already exists here (warmed or
# reused above), so send the delta through the fast path and skip the tree
# sync entirely when it can run.
FAST_ATTACH=""
for _cand in "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/box-fast-attach" \
    "$HOME/Documents/Personal/scripts/box-fast-attach" \
    "$HOME/.local/bin/box-fast-attach"; do
  if [[ -x "$_cand" ]]; then FAST_ATTACH="$_cand"; break; fi
done
unset _cand

if [[ -n "$FAST_ATTACH" ]]; then
  # box-fast-attach addresses Boxes by bx_ id; the slug resolves against the
  # live Box list (subdomain or name), the same match box-reap-cron uses.
  _box_id=""
  if _box_json="$("$HOME/.ascii/bin/box" list --json 2>/dev/null)"; then
    _box_id="$(printf '%s' "$_box_json" | SLUG="$SLUG" python3 -c '
import sys, json, os
want = os.environ.get("SLUG", "")
try:
    d = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
for b in d.get("boxes", []):
    if b.get("subdomain") == want or b.get("name") == want:
        print(b.get("id", ""))
        break
' 2>/dev/null || true)"
  fi
  if [[ -n "$_box_id" ]]; then
    _remote_workdir="$(crabbox inspect --id "$SLUG" --json 2>/dev/null | grep -oE '"workdir":"[^"]+"' | head -1 | sed 's/"workdir":"\(.*\)"/\1/' || true)"
    echo "[crabbox-attach] Fast path: box-fast-attach --box $_box_id"
    _fast_ok=0
    if [[ -n "$_remote_workdir" ]]; then
      if BOX_REMOTE_DIR="$_remote_workdir" "$FAST_ATTACH" --box "$_box_id"; then _fast_ok=1; fi
    else
      if "$FAST_ATTACH" --box "$_box_id"; then _fast_ok=1; fi
    fi
    if (( _fast_ok )); then
      print_banner "$SLUG" "${_remote_workdir:-(unknown)}"
      exit 0
    fi
    echo "[crabbox-attach] Fast path failed; falling back to the crabbox sync." >&2
  else
    echo "[crabbox-attach] No live Box matches slug $SLUG; using the crabbox sync." >&2
  fi
  unset _box_id _box_json _remote_workdir _fast_ok
else
  echo "[crabbox-attach] box-fast-attach not found; using the crabbox sync." >&2
fi

# Read secret paths from the main repo. The fallback keeps the old .env
# behavior without adding repo-specific paths.
SECRET_PATHS=()
SECRETS_FILE="$MAIN_ROOT/.crabbox-secrets"
if [[ -f "$SECRETS_FILE" ]]; then
  while IFS= read -r secret_path || [[ -n "$secret_path" ]]; do
    secret_path="$(printf '%s\n' "$secret_path" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$secret_path" || "${secret_path#\#}" != "$secret_path" ]] && continue
    SECRET_PATHS[${#SECRET_PATHS[@]}]="$secret_path"
  done < "$SECRETS_FILE"
else
  [[ -e "$WORKTREE_ROOT/.env.local" ]] && SECRET_PATHS[${#SECRET_PATHS[@]}]=".env.local"
  [[ -e "$WORKTREE_ROOT/.env" ]] && SECRET_PATHS[${#SECRET_PATHS[@]}]=".env"
fi

EXISTING_SECRETS=()
for secret_path in "${SECRET_PATHS[@]:-}"; do
  [[ -e "$WORKTREE_ROOT/$secret_path" ]] && EXISTING_SECRETS[${#EXISTING_SECRETS[@]}]="$secret_path"
done

tar_b64=""
if (( ${#EXISTING_SECRETS[@]} > 0 )); then
  tar_b64="$(cd "$WORKTREE_ROOT" && tar -czhf - "${EXISTING_SECRETS[@]}" 2>/dev/null | base64)"
fi

echo "[crabbox-attach] Syncing the worktree, secrets, and runtime dependencies..."
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  echo 'echo "[remote] cwd=$(pwd)"'

  if [[ -n "$tar_b64" ]]; then
    echo "base64 -d <<'__CRABBOX_TAR_EOF__' | tar -xzf -"
    echo "$tar_b64"
    echo '__CRABBOX_TAR_EOF__'
    echo 'echo "[remote] secrets extracted"'
  fi

  echo 'if ! command -v curl >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1 || ! command -v gcc >/dev/null 2>&1; then'
  echo '  sudo apt-get update -qq'
  echo '  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates curl git build-essential python3 python-is-python3 pkg-config'
  echo 'fi'

  case "$PACKAGE_MANAGER" in
    bun)
      echo 'export PATH="$HOME/.bun/bin:/opt/bun/bin:$PATH"'
      echo 'if ! command -v bun >/dev/null 2>&1; then curl -fsSL https://bun.sh/install | bash; export PATH="$HOME/.bun/bin:/opt/bun/bin:$PATH"; fi'
      ;;
    npm|pnpm|yarn)
      echo 'if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then'
      echo '  sudo apt-get update -qq'
      echo '  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs npm'
      echo 'fi'
      if [[ "$PACKAGE_MANAGER" == "pnpm" || "$PACKAGE_MANAGER" == "yarn" ]]; then
        echo "if ! command -v $PACKAGE_MANAGER >/dev/null 2>&1; then"
        echo '  if command -v corepack >/dev/null 2>&1; then'
        echo "    corepack enable && corepack prepare $PACKAGE_MANAGER@latest --activate"
        echo '  else'
        echo "    npm install --global $PACKAGE_MANAGER"
        echo '  fi'
        echo 'fi'
      fi
      ;;
  esac

  if [[ -f "$WORKTREE_ROOT/pnpm-workspace.yaml" ]]; then
    echo 'echo "[remote] pnpm workspace detected; running one root install"'
  else
    echo 'echo "[remote] single-root project; running one root install"'
  fi
  # Turborepo reads its remote-cache credentials from the process environment,
  # not from .env.local. The named box env already injects them, but a box
  # started without one (no shim, or a repo with no environment yet) still has
  # the file. Source it so the cache works either way -- without this every
  # build on the box is a cold build even though the credentials are present.
  echo 'if [[ -f .env.local ]]; then set -a; . ./.env.local; set +a; fi'
  echo 'if [[ -n "${TURBO_TOKEN:-}" ]]; then echo "[remote] turbo remote cache: on (team=${TURBO_TEAM:-unset})"; else echo "[remote] turbo remote cache: OFF"; fi'

  echo "$PACKAGE_MANAGER install"

  # Repo-specific setup (D1 migrations, workspace symlink repair) lives in the
  # repo, and it never ran on the box before. Run it when it exists.
  echo 'if [[ -x bin/setup-worktree.sh ]]; then'
  echo '  echo "[remote] running bin/setup-worktree.sh"'
  echo '  bin/setup-worktree.sh || echo "[remote] setup-worktree.sh failed (non-fatal)"'
  echo 'fi'

  echo 'echo "[remote] attach complete, workdir=$(pwd)"'
} | crabbox run --id "$SLUG" $RECLAIM_FLAG --script-stdin

REMOTE_WORKDIR="$(crabbox inspect --id "$SLUG" --json 2>/dev/null | grep -oE '"workdir":"[^"]+"' | head -1 | sed 's/"workdir":"\(.*\)"/\1/' || true)"
[[ -z "$REMOTE_WORKDIR" ]] && REMOTE_WORKDIR="(unknown)"

print_banner "$SLUG" "$REMOTE_WORKDIR"
