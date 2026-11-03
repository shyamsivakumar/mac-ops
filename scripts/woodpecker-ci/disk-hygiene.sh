#!/bin/sh
# MO-122: keep the M1 CI box under a host free-space floor.
# Prunes local Xcode DerivedData (age + size cap), unused simulator
# devices (keeps CI-iPhone), safe package caches, and Colima dangling
# Docker data. Never deletes /var/lib/woodpecker-cache (MO-120), never
# removes woodpecker-ci-* volumes or pinned CI images, never runs during
# an SRW deploy. Alerts (log + optional osascript) when free < 15%.
#
# Env:
#   DD_ROOT          default ~/Library/Developer/Xcode/DerivedData
#   DD_CAP_BYTES     default 20GiB
#   DD_MAX_AGE_DAYS  default 2
#   FREE_FLOOR_PCT   default 25 (target; soft — we prune toward this)
#   ALERT_BELOW_PCT  default 15
#   LOG_FILE         default ~/Library/Logs/woodpecker/disk-hygiene.log
#   CI_IPHONE_NAME   default CI-iPhone
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
export PATH

# shellcheck source=common.sh disable=SC1091
. "$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)/common.sh"

DD_ROOT=${DD_ROOT:-$HOME/Library/Developer/Xcode/DerivedData}
DD_CAP_BYTES=${DD_CAP_BYTES:-21474836480}
DD_MAX_AGE_DAYS=${DD_MAX_AGE_DAYS:-2}
FREE_FLOOR_PCT=${FREE_FLOOR_PCT:-25}
ALERT_BELOW_PCT=${ALERT_BELOW_PCT:-15}
LOG_FILE=${LOG_FILE:-$HOME/Library/Logs/woodpecker/disk-hygiene.log}
CI_IPHONE_NAME=${CI_IPHONE_NAME:-CI-iPhone}

mkdir -p "$(dirname "$LOG_FILE")"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
log() { printf '%s %s\n' "$ts" "$*" | tee -a "$LOG_FILE"; }

bytes_of() {
  du -sk "$1" 2>/dev/null | awk '{print $1 * 1024}'
}

# Free percent on the Data volume (APFS).
free_pct() {
  df -P /System/Volumes/Data 2>/dev/null | awk 'NR==2 {
    # Prefer capacity field when present; else compute from 1K-blocks.
    if ($5 ~ /%$/) { gsub(/%/,"",$5); print 100-$5; next }
    if ($2+0>0) print int(($4*100)/$2)
  }'
}

avail_human() {
  df -h /System/Volumes/Data 2>/dev/null | awk 'NR==2 {print $4 " free / " $2 " (" $5 " used)"}'
}

srw=$(srw_deploy_running 2>/dev/null || echo unknown)
case "$srw" in
  0) ;;
  *)
    log "skip: SRW deploy running ($srw)"
    exit 0
    ;;
esac

running=$(any_workflow_running 2>/dev/null || echo unknown)
log "start free=$(avail_human) workflows=$running"

# --- DerivedData: age then cap. Never touch MO-120 shared cache. ---
if [ -d "$DD_ROOT" ]; then
  used=$(bytes_of "$DD_ROOT")
  log "DerivedData used=$used cap=$DD_CAP_BYTES age_days=$DD_MAX_AGE_DAYS"
  find "$DD_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +"$DD_MAX_AGE_DAYS" -print 2>/dev/null \
    | while IFS= read -r p; do
      case "$p" in
        /var/lib/woodpecker-cache/*) continue ;;
      esac
      log "DerivedData age-prune $p"
      rm -rf "$p"
    done
  used=$(bytes_of "$DD_ROOT")
  if [ "${used:-0}" -gt "$DD_CAP_BYTES" ]; then
    list=$(mktemp "${TMPDIR:-/tmp}/dd-prune.XXXXXX")
    find "$DD_ROOT" -mindepth 1 -maxdepth 1 -type d -exec stat -f '%m %N' {} \; 2>/dev/null \
      | sort -n >"$list"
    while read -r _mtime path; do
      [ -n "${path:-}" ] || continue
      used=$(bytes_of "$DD_ROOT")
      [ "$used" -gt "$DD_CAP_BYTES" ] || break
      still=$(any_workflow_running 2>/dev/null || echo 1)
      # Native darwin jobs may be using DerivedData; skip cap deletes while busy.
      if [ "$still" != "0" ]; then
        log "DerivedData cap-prune paused: $still workflow(s) running"
        break
      fi
      log "DerivedData cap-prune $path"
      rm -rf "$path"
    done <"$list"
    rm -f "$list"
  fi
else
  log "DerivedData absent"
fi

# --- Simulators: delete every device except CI-iPhone; keep its runtime. ---
ci_udid=$(xcrun simctl list devices 2>/dev/null | grep "$CI_IPHONE_NAME" | head -1 \
  | sed -n 's/.*(\([0-9A-Fa-f-]\{36\}\)).*/\1/p')
if [ -n "${ci_udid:-}" ]; then
  xcrun simctl list devices 2>/dev/null | sed -n 's/.*(\([0-9A-Fa-f-]\{36\}\)).*/\1/p' \
    | while read -r udid; do
      [ "$udid" = "$ci_udid" ] && continue
      log "simctl delete $udid"
      xcrun simctl delete "$udid" 2>/dev/null || true
    done
else
  log "CI-iPhone not found; skipped simulator deletes"
fi

# --- Colima: dangling only; keep pinned tags + woodpecker volumes. ---
if docker info >/dev/null 2>&1; then
  still=$(any_workflow_running 2>/dev/null || echo 1)
  if [ "$still" = "0" ]; then
    log "docker: prune stopped containers + dangling images + builder cache"
    docker container prune -f >/dev/null 2>&1 || true
    docker image prune -f >/dev/null 2>&1 || true
    docker builder prune -f >/dev/null 2>&1 || true
    # Dangling volumes only — never woodpecker-ci-* by name.
    docker volume ls -qf dangling=true 2>/dev/null | while read -r vol; do
      case "$vol" in
        woodpecker-ci-*)
          log "keep volume $vol"
          continue
          ;;
        '') continue ;;
      esac
      log "docker volume rm $vol"
      docker volume rm "$vol" >/dev/null 2>&1 || true
    done
  else
    log "docker prune skipped: $still workflow(s) running"
  fi
else
  log "docker context unavailable; skipped"
fi

pct=$(free_pct)
pct=${pct:-0}
log "done free=$(avail_human) free_pct=$pct floor=$FREE_FLOOR_PCT alert_below=$ALERT_BELOW_PCT"

if [ "$pct" -lt "$ALERT_BELOW_PCT" ] 2>/dev/null; then
  msg="MO-122 disk alert: Data volume ${pct}% free (below ${ALERT_BELOW_PCT}%). $(avail_human)"
  log "ALERT $msg"
  # Best-effort GUI banner when a session exists; always logged.
  osascript -e "display notification \"$msg\" with title \"M1 CI disk\"" 2>/dev/null || true
  printf '%s\n' "$msg" >&2
  exit 1
fi

if [ "$pct" -lt "$FREE_FLOOR_PCT" ] 2>/dev/null; then
  log "warn: free_pct=$pct below floor=$FREE_FLOOR_PCT (cap prune may need manual help)"
fi

exit 0
