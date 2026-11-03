#!/bin/sh
# MO-122: keep the M1 CI box under a host free-space floor.
# Prunes local Xcode DerivedData (age + size cap), unused simulator
# devices (keeps CI-iPhone), and Colima dangling Docker data. Never
# deletes /var/lib/woodpecker-cache (MO-120), never removes
# woodpecker-ci-* volumes or tagged CI images, never runs during an SRW
# deploy or any running workflow. Alerts when free < 15%.
#
# Env:
#   DD_ROOT          default ~/Library/Developer/Xcode/DerivedData
#                    (rejected if under /var/lib/woodpecker-cache)
#   DD_CAP_BYTES     default 20GiB
#   DD_MAX_AGE_DAYS  default 2
#   FREE_FLOOR_PCT   default 25 (target; soft — we prune toward this)
#   ALERT_BELOW_PCT  default 15
#   LOG_FILE         default ~/Library/Logs/woodpecker/disk-hygiene.log
#   CI_IPHONE_NAME   default CI-iPhone (exact device name match)
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
PROTECTED_CACHE=/var/lib/woodpecker-cache

mkdir -p "$(dirname "$LOG_FILE")"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
log() { printf '%s %s\n' "$ts" "$*" | tee -a "$LOG_FILE"; }

bytes_of() {
  du -sk "$1" 2>/dev/null | awk '{print $1 * 1024}'
}

# Free percent on the Data volume (APFS).
free_pct() {
  df -P /System/Volumes/Data 2>/dev/null | awk 'NR==2 {
    if ($5 ~ /%$/) { gsub(/%/,"",$5); print 100-$5; next }
    if ($2+0>0) print int(($4*100)/$2)
  }'
}

avail_human() {
  df -h /System/Volumes/Data 2>/dev/null | awk 'NR==2 {print $4 " free / " $2 " (" $5 " used)"}'
}

# Fail closed: non-zero / empty / non-numeric counts mean "busy".
# Prints reason on stdout when refusing; return 1 = skip destructive work.
require_idle() {
  phase=$1
  srw=$(srw_deploy_running 2>/dev/null || echo unknown)
  case "$srw" in
    0) ;;
    *)
      log "skip $phase: SRW deploy running ($srw)"
      return 1
      ;;
  esac
  still=$(any_workflow_running 2>/dev/null || echo unknown)
  case "$still" in
    0) return 0 ;;
    '' | *[!0-9]*)
      log "skip $phase: could not read running workflow count ($still)"
      return 1
      ;;
    *)
      log "skip $phase: $still workflow(s) running"
      return 1
      ;;
  esac
}

# Canonical absolute path (resolves /var → /private/var, .., symlinks).
# Fails closed when resolution is impossible.
canon_path() {
  python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1" 2>/dev/null
}

PROTECTED_CANON=$(canon_path "$PROTECTED_CACHE") || PROTECTED_CANON=

# True if path is the MO-120 cache or a descendant (canonical compare).
under_protected_cache() {
  target=$(canon_path "$1") || return 0
  [ -n "$PROTECTED_CANON" ] || return 0
  case "$target" in
    "$PROTECTED_CANON" | "$PROTECTED_CANON"/*) return 0 ;;
    *) return 1 ;;
  esac
}

# Absolute canonical DD_ROOT; refuse MO-120 cache and its descendants.
resolve_dd_root() {
  root=$1
  abs=$(canon_path "$root") || {
    log "refuse DD_ROOT: cannot canonicalize $root"
    return 1
  }
  if under_protected_cache "$abs"; then
    log "refuse DD_ROOT under protected cache: $abs"
    return 1
  fi
  printf '%s\n' "$abs"
}

# Exact-name keep set from simctl JSON. Empty / ambiguous → refuse deletes.
ci_iphone_udids() {
  name=$1
  xcrun simctl list devices -j 2>/dev/null | CI_NAME="$name" python3 -c '
import json, os, sys
name = os.environ["CI_NAME"]
data = json.load(sys.stdin)
udids = []
for devices in data.get("devices", {}).values():
    for dev in devices:
        if dev.get("name") == name and dev.get("udid"):
            udids.append(dev["udid"])
for u in udids:
    print(u)
'
}

require_idle entry || exit 0
log "start free=$(avail_human)"

# --- DerivedData: age then cap. Never touch MO-120 shared cache. ---
if [ -d "$DD_ROOT" ]; then
  if ! DD_ROOT=$(resolve_dd_root "$DD_ROOT"); then
    log "DerivedData skipped: protected DD_ROOT"
  else
    used=$(bytes_of "$DD_ROOT")
    log "DerivedData root=$DD_ROOT used=$used cap=$DD_CAP_BYTES age_days=$DD_MAX_AGE_DAYS"
    if require_idle "DerivedData-age"; then
      list=$(mktemp "${TMPDIR:-/tmp}/dd-age.XXXXXX")
      find "$DD_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +"$DD_MAX_AGE_DAYS" \
        -print 2>/dev/null >"$list" || true
      while IFS= read -r p; do
        [ -n "${p:-}" ] || continue
        under_protected_cache "$p" && continue
        require_idle "DerivedData-age-item" || break
        log "DerivedData age-prune $p"
        rm -rf "$p"
      done <"$list"
      rm -f "$list"
    fi
    used=$(bytes_of "$DD_ROOT")
    if [ "${used:-0}" -gt "$DD_CAP_BYTES" ] && require_idle "DerivedData-cap"; then
      list=$(mktemp "${TMPDIR:-/tmp}/dd-cap.XXXXXX")
      find "$DD_ROOT" -mindepth 1 -maxdepth 1 -type d -exec stat -f '%m %N' {} \; \
        2>/dev/null | sort -n >"$list"
      while read -r _mtime path; do
        [ -n "${path:-}" ] || continue
        under_protected_cache "$path" && continue
        used=$(bytes_of "$DD_ROOT")
        [ "$used" -gt "$DD_CAP_BYTES" ] || break
        require_idle "DerivedData-cap-item" || break
        log "DerivedData cap-prune $path"
        rm -rf "$path"
      done <"$list"
      rm -f "$list"
    fi
  fi
else
  log "DerivedData absent"
fi

# --- Simulators: delete every device except exact CI-iPhone name(s). ---
if require_idle simulators; then
  keep=$(mktemp "${TMPDIR:-/tmp}/sim-keep.XXXXXX")
  if ! ci_iphone_udids "$CI_IPHONE_NAME" >"$keep"; then
    log "simctl JSON unavailable; skipped simulator deletes"
    rm -f "$keep"
  else
    nkeep=$(wc -l <"$keep" | tr -d ' ')
    if [ "$nkeep" -eq 0 ]; then
      log "no exact device named $CI_IPHONE_NAME; skipped simulator deletes"
    else
      log "keeping $nkeep device(s) named $CI_IPHONE_NAME"
      xcrun simctl list devices -j 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
for devices in data.get("devices", {}).values():
    for dev in devices:
        u = dev.get("udid")
        if u:
            print(u)
' | while read -r udid; do
        [ -n "$udid" ] || continue
        if grep -qx "$udid" "$keep"; then
          continue
        fi
        require_idle "simctl-delete" || break
        log "simctl delete $udid"
        xcrun simctl delete "$udid" 2>/dev/null || true
      done
    fi
    rm -f "$keep"
  fi
fi

# --- Colima: dangling only; keep tagged images + woodpecker volumes. ---
if docker info >/dev/null 2>&1; then
  if require_idle "docker-container-prune"; then
    log "docker: container prune"
    docker container prune -f >/dev/null 2>&1 || true
  fi
  if require_idle "docker-image-prune"; then
    log "docker: image prune (dangling only)"
    docker image prune -f >/dev/null 2>&1 || true
  fi
  if require_idle "docker-builder-prune"; then
    log "docker: builder prune"
    docker builder prune -f >/dev/null 2>&1 || true
  fi
  if require_idle "docker-volume-list"; then
    docker volume ls -qf dangling=true 2>/dev/null | while read -r vol; do
      case "$vol" in
        woodpecker-ci-*)
          log "keep volume $vol"
          continue
          ;;
        '') continue ;;
      esac
      require_idle "docker-volume" || break
      log "docker volume rm $vol"
      docker volume rm "$vol" >/dev/null 2>&1 || true
    done
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
  osascript -e "display notification \"$msg\" with title \"M1 CI disk\"" 2>/dev/null || true
  printf '%s\n' "$msg" >&2
  exit 1
fi

if [ "$pct" -lt "$FREE_FLOOR_PCT" ] 2>/dev/null; then
  log "warn: free_pct=$pct below floor=$FREE_FLOOR_PCT (cap prune may need manual help)"
fi

exit 0
