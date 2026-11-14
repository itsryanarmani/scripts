#!/usr/bin/env bash
# Periodic cleanup for a Linux or WSL2 host that runs many GitHub Actions runners.
# Run on the host itself, as root. Configure with RUNNER_ROOT (default /opt/actions-runner).
#
#   runner-host-maint.sh status            disk use, busy workers, dead runner folders
#   runner-host-maint.sh clean [--dry-run] [--prune-orphans] [--docker]
#   runner-host-maint.sh install-timer     daily systemd timer that runs "clean"
#
# What "clean" does, in order of risk:
#   1. For each runner folder whose service is active and has no running job: stop the
#      service, delete the job checkouts in _work (keeps _tool and _actions), start the
#      service again. A runner with a job is never touched. A service that was already
#      stopped stays stopped.
#   2. Old _diag logs.
#   3. Only when no job runs anywhere: the runner service account's package caches.
#   4. With --docker: `docker system prune -af --filter until=24h`. That removes unused
#      images, stopped containers, unused networks and build cache older than 24 hours.
#      Docker is shared by the whole host, so this is off by default.
#   5. Journal, apt cache, fstrim.
# A runner folder is a folder that holds .runner or config.sh. A runner folder with no
# service is a dead registration. "clean" lists it. --prune-orphans deletes it.
# "clean" refuses to run when it finds runner folders but no runner services at all, because
# an empty service map would make every runner look dead.
set -uo pipefail
shopt -s nullglob

ROOT="${RUNNER_ROOT:-/opt/actions-runner}"
LOG="${RUNNER_MAINT_LOG:-/var/log/runner-host-maint.log}"
KEEP_IN_WORK=(_tool _actions)
DRY=0 PRUNE_ORPHANS=0 DOCKER=0

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG" 2>/dev/null; }
used_mb() { df -m / | awk 'NR==2{print $3}'; }
real() { readlink -f -- "$1" 2>/dev/null || printf '%s' "$1"; }
is_runner_dir() { [[ -f "$1/.runner" || -f "$1/config.sh" ]]; }
any_busy() { pgrep -f 'Runner\.Worker' >/dev/null 2>&1; }
busy_in() { pgrep -f "$(real "$1")/.*Runner\.Worker" >/dev/null 2>&1; }
run() { if ((DRY)); then echo "dry-run: $*"; else "$@"; fi; }

# Map each runner folder (resolved path) to its service unit, once.
declare -A UNIT_FOR=()
UNIT_COUNT=0
build_map() {
  local u wd
  while read -r u; do
    [[ -n "$u" ]] || continue
    wd="$(systemctl show "$u" -p WorkingDirectory --value 2>/dev/null)"
    if [[ -n "$wd" ]]; then UNIT_FOR["$(real "$wd")"]="$u"; UNIT_COUNT=$((UNIT_COUNT + 1)); fi
  done < <(systemctl list-unit-files 'actions.runner.*' --no-legend --plain 2>/dev/null | awk '{print $1}')
}

runner_dirs() {
  local d
  for d in "$ROOT"/*/; do
    d="${d%/}"
    is_runner_dir "$d" && printf '%s\n' "$(real "$d")"
  done
}

cmd_status() {
  build_map
  df -h / | tail -1
  echo "busy workers: $(pgrep -fc 'Runner\.Worker' || true)"
  local d orphans=0
  while read -r d; do
    [[ -n "$d" ]] || continue
    if [[ -z "${UNIT_FOR[$d]:-}" ]]; then
      echo "orphan (no service): $(basename "$d") $(du -sh "$d" 2>/dev/null | cut -f1)"; orphans=$((orphans + 1))
    fi
  done < <(runner_dirs)
  echo "orphans: $orphans"
}

clean_runner() {
  local d="$1" unit="$2" find_args=() k
  if ! systemctl is-active --quiet "$unit"; then echo "inactive, left alone: $(basename "$d")"; return 1; fi
  if busy_in "$d"; then echo "busy, skipped: $(basename "$d")"; return 1; fi
  if ! run systemctl stop "$unit"; then echo "stop failed, skipped: $(basename "$d")"; return 1; fi
  if ! ((DRY)) && busy_in "$d"; then
    echo "got a job, skipped: $(basename "$d")"
    if ! run systemctl start "$unit"; then
      log "RESTART FAILED: $(basename "$d") ($unit) is down"
      return 2
    fi
    return 1
  fi
  for k in "${KEEP_IN_WORK[@]}"; do find_args+=(! -name "$k"); done
  if [[ -d "$d/_work" ]]; then
    if ((DRY)); then echo "dry-run: would clear $d/_work ($(du -sh "$d/_work" 2>/dev/null | cut -f1))"
    else find "$d/_work" -mindepth 1 -maxdepth 1 "${find_args[@]}" -exec rm -rf {} + 2>/dev/null; fi
  fi
  ((DRY)) || find "$d/_diag" -type f -mtime +7 -delete 2>/dev/null
  if ! run systemctl start "$unit"; then
    log "RESTART FAILED: $(basename "$d") ($unit) is down"
    return 2
  fi
  return 0
}

cmd_clean() {
  exec 9>/var/lock/runner-host-maint.lock
  flock -n 9 || { echo "another run is active"; exit 0; }
  build_map
  local dirs=() d before after cleaned=0 skipped=0 failed=0 orphans=() rc
  while read -r d; do [[ -n "$d" ]] && dirs+=("$d"); done < <(runner_dirs)
  if ((${#dirs[@]} > 0 && UNIT_COUNT == 0)); then
    echo "refusing: found ${#dirs[@]} runner folders and no runner services (is systemd up?)" >&2
    exit 3
  fi
  before="$(used_mb)"
  for d in "${dirs[@]}"; do
    if [[ -z "${UNIT_FOR[$d]:-}" ]]; then orphans+=("$d"); continue; fi
    clean_runner "$d" "${UNIT_FOR[$d]}"; rc=$?
    case "$rc" in
      0) cleaned=$((cleaned + 1)) ;;
      2) failed=$((failed + 1)) ;;
      *) skipped=$((skipped + 1)) ;;
    esac
  done
  for d in "${orphans[@]}"; do
    # Also keep a folder with a live listener: its unit may have another name.
    if ((PRUNE_ORPHANS)) && ! busy_in "$d" && ! pgrep -f "$d/.*Runner\.Listener" >/dev/null 2>&1; then
      run rm -rf -- "$d"; log "removed orphan $(basename "$d")"
    else echo "orphan kept: $(basename "$d") (use --prune-orphans, and it must have no live listener)"; fi
  done
  # Package caches of the runner service account. A job may be using them, so skip
  # this step while any job runs. A service with its own HOME is not covered here.
  local h="/home/${RUNNER_SERVICE_USER:-actions}"
  if [[ -d "$h" ]]; then
    if any_busy; then echo "jobs running, caches kept"
    else run rm -rf "$h/.cache" "$h/.npm/_cacache" "$h/.bun/install/cache"; fi
  fi
  if ((DOCKER)) && command -v docker >/dev/null 2>&1; then
    run docker system prune -af --filter until=24h >/dev/null 2>&1
  fi
  run journalctl --vacuum-size=100M >/dev/null 2>&1
  run apt-get clean
  run fstrim / >/dev/null 2>&1
  after="$(used_mb)"
  log "clean dry=$DRY cleaned=$cleaned skipped=$skipped restart_failed=$failed orphans=${#orphans[@]} freed_mb=$((before - after)) used_mb=$after"
  ((failed == 0)) || exit 4
}

cmd_install_timer() {
  local self; self="$(readlink -f "$0")"
  install -m 0755 "$self" /usr/local/bin/runner-host-maint
  cat >/etc/systemd/system/runner-host-maint.service <<'UNIT'
[Unit]
Description=Clean idle GitHub Actions runners
[Service]
Type=oneshot
Environment=RUNNER_ROOT=__ROOT__
Environment=RUNNER_SERVICE_USER=__USER__
ExecStart=/usr/local/bin/runner-host-maint clean
UNIT
  sed -i "s|__ROOT__|$ROOT|; s|__USER__|${RUNNER_SERVICE_USER:-actions}|" /etc/systemd/system/runner-host-maint.service
  cat >/etc/systemd/system/runner-host-maint.timer <<'UNIT'
[Unit]
Description=Daily runner host cleanup
[Timer]
OnCalendar=*-*-* 04:15:00
RandomizedDelaySec=10m
Persistent=true
[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload
  systemctl enable --now runner-host-maint.timer
  systemctl list-timers runner-host-maint.timer --no-pager
  echo "Installed a copy at /usr/local/bin/runner-host-maint. Re-run install-timer after you update this script."
}

main() {
  local sub="${1:-status}"; shift || true
  local a
  for a in "$@"; do
    case "$a" in
      --dry-run) DRY=1 ;;
      --prune-orphans) PRUNE_ORPHANS=1 ;;
      --docker) DOCKER=1 ;;
      *) echo "unknown option: $a" >&2; exit 2 ;;
    esac
  done
  [[ -d "$ROOT" ]] || { echo "RUNNER_ROOT not found: $ROOT" >&2; exit 2; }
  case "$sub" in
    status) cmd_status ;;
    clean) cmd_clean ;;
    install-timer) cmd_install_timer ;;
    *) echo "usage: $0 status | clean [--dry-run] [--prune-orphans] [--docker] | install-timer" >&2; exit 2 ;;
  esac
}
main "$@"
