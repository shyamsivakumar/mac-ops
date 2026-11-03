#!/bin/sh
# MO-120: enforce a size cap on /var/lib/woodpecker-cache.
# Deletes oldest repo/kind trees first until under CAP_BYTES.
# Skips entirely while any Woodpecker workflow is running, and rechecks
# before every deletion (host and Colima) so a job that starts mid-prune
# cannot lose its mount. Safe for LaunchAgent or cron. Never touches secrets.
#
# Env:
#   CACHE_ROOT   default /var/lib/woodpecker-cache
#   CAP_BYTES    default 20GiB (21474836480) — per tree (host and Colima each)
#   LOG_FILE     default ~/Library/Logs/woodpecker/cache-cleanup.log
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
export PATH

# shellcheck source=common.sh disable=SC1091
. "$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)/common.sh"

CACHE_ROOT=${CACHE_ROOT:-/var/lib/woodpecker-cache}
CAP_BYTES=${CAP_BYTES:-21474836480}
LOG_FILE=${LOG_FILE:-$HOME/Library/Logs/woodpecker/cache-cleanup.log}

mkdir -p "$(dirname "$LOG_FILE")"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
log() { printf '%s %s\n' "$ts" "$*" | tee -a "$LOG_FILE"; }

abort_if_busy() {
  still=$(any_workflow_running 2>/dev/null || echo 1)
  if [ "$still" != "0" ]; then
    log "abort prune: $still workflow(s) running (MO-120 mount safety)"
    return 1
  fi
  return 0
}

running=$(any_workflow_running 2>/dev/null || echo unknown)
case "$running" in
  '' | unknown)
    log "skip cleanup: could not read running workflow count"
    exit 0
    ;;
  0) ;;
  *)
    log "skip cleanup: $running workflow(s) running (MO-120 mount safety)"
    exit 0
    ;;
esac

# Host filesystem: oldest leaf kind dirs by mtime.
if [ -d "$CACHE_ROOT" ]; then
  used=$(du -sk "$CACHE_ROOT" | awk '{print $1 * 1024}')
  log "host $CACHE_ROOT used=$used cap=$CAP_BYTES"
  if [ "$used" -gt "$CAP_BYTES" ]; then
    list=$(mktemp "${TMPDIR:-/tmp}/wp-cache-prune.XXXXXX")
    sorted=$(mktemp "${TMPDIR:-/tmp}/wp-cache-prune-sorted.XXXXXX")
    if stat -f '%m' "$CACHE_ROOT" >/dev/null 2>&1; then
      find "$CACHE_ROOT" -mindepth 2 -maxdepth 2 -type d -exec stat -f '%m %N' {} \; \
        >"$list" 2>/dev/null || true
    else
      find "$CACHE_ROOT" -mindepth 2 -maxdepth 2 -type d -exec stat -c '%Y %n' {} \; \
        >"$list" 2>/dev/null || true
    fi
    sort -n "$list" >"$sorted"
    while read -r _mtime path; do
      [ -n "${path:-}" ] || continue
      used=$(du -sk "$CACHE_ROOT" | awk '{print $1 * 1024}')
      [ "$used" -gt "$CAP_BYTES" ] || break
      abort_if_busy || break
      log "host prune $path (mtime=$_mtime)"
      rm -rf "$path"
      mkdir -p "$path"
      chmod 0770 "$path"
    done <"$sorted"
    rm -f "$list" "$sorted"
  fi
else
  log "host $CACHE_ROOT absent (ok if native cache not installed yet)"
fi

# Colima VM tree: list candidates inside the VM, then delete one-at-a-time from
# the host with a workflow recheck before each deletion (never a long unguarded
# loop inside the helper container).
abort_if_busy || exit 0

if ! docker info >/dev/null 2>&1; then
  log "colima context unavailable; skipped VM cleanup"
  exit 0
fi

used_line=$(docker run --rm --privileged \
  -e CACHE_ROOT="$CACHE_ROOT" \
  -v /var/lib:/var/lib \
  alpine:3.22 \
  sh -c '
    set -eu
    ROOT="$CACHE_ROOT"
    if [ ! -d "$ROOT" ]; then
      echo "absent"
      exit 0
    fi
    du -sk "$ROOT" | awk "{print \$1 * 1024}"
  ')
case "$used_line" in
  absent)
    log "colima $CACHE_ROOT absent"
    exit 0
    ;;
esac
log "colima $CACHE_ROOT used=$used_line cap=$CAP_BYTES"
if [ "$used_line" -le "$CAP_BYTES" ]; then
  exit 0
fi

candidates=$(mktemp "${TMPDIR:-/tmp}/wp-cache-colima.XXXXXX")
docker run --rm --privileged \
  -e CACHE_ROOT="$CACHE_ROOT" \
  -v /var/lib:/var/lib \
  alpine:3.22 \
  sh -c '
    set -eu
    ROOT="$CACHE_ROOT"
    find "$ROOT" -mindepth 2 -maxdepth 2 -type d -exec stat -c "%Y %n" {} \; \
      | sort -n
  ' >"$candidates"

while read -r mtime path; do
  [ -n "${path:-}" ] || continue
  used_now=$(docker run --rm --privileged \
    -e CACHE_ROOT="$CACHE_ROOT" \
    -v /var/lib:/var/lib \
    alpine:3.22 \
    sh -c 'du -sk "$CACHE_ROOT" | awk "{print \$1 * 1024}"')
  [ "$used_now" -gt "$CAP_BYTES" ] || break
  abort_if_busy || break
  log "colima prune $path (mtime=$mtime)"
  docker run --rm --privileged \
    -e TARGET="$path" \
    -v /var/lib:/var/lib \
    alpine:3.22 \
    sh -c '
      set -eu
      case "$TARGET" in
        /var/lib/woodpecker-cache/*) ;;
        *) echo "refuse prune outside cache root: $TARGET" >&2; exit 1 ;;
      esac
      rm -rf "$TARGET"
      mkdir -p "$TARGET"
      chmod 0750 "$TARGET"
    '
done <"$candidates"
rm -f "$candidates"
