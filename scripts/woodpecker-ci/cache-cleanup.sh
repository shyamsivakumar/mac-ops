#!/bin/sh
# MO-120: enforce a size cap on /var/lib/woodpecker-cache.
# Deletes oldest repo/kind trees first until under CAP_BYTES.
# Skips entirely while any Woodpecker workflow is running (avoids deleting
# mounts mid-job). Safe for LaunchAgent or cron. Never touches secrets.
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

# Prune oldest leaf kind dirs (by mtime) until under cap.
prune_oldest() {
  root=$1
  label=$2
  dir_mode=${3:-0750}
  used=$(du -sk "$root" | awk '{print $1 * 1024}')
  log "$label $root used=$used cap=$CAP_BYTES"
  if [ "$used" -le "$CAP_BYTES" ]; then
    return 0
  fi
  list=$(mktemp "${TMPDIR:-/tmp}/wp-cache-prune.XXXXXX")
  if stat -f '%m' "$root" >/dev/null 2>&1; then
    find "$root" -mindepth 2 -maxdepth 2 -type d -exec stat -f '%m %N' {} \; \
      >"$list" 2>/dev/null || true
  else
    find "$root" -mindepth 2 -maxdepth 2 -type d -exec stat -c '%Y %n' {} \; \
      >"$list" 2>/dev/null || true
  fi
  sort -n "$list" | while read -r _mtime path; do
    used=$(du -sk "$root" | awk '{print $1 * 1024}')
    [ "$used" -gt "$CAP_BYTES" ] || break
    still=$(any_workflow_running 2>/dev/null || echo 1)
    if [ "$still" != "0" ]; then
      log "$label abort prune: workflows running ($still)"
      break
    fi
    log "$label prune $path (mtime=$_mtime)"
    rm -rf "$path"
    mkdir -p "$path"
    chmod "$dir_mode" "$path"
  done
  rm -f "$list"
}

# Host tree (native agent).
if [ -d "$CACHE_ROOT" ]; then
  prune_oldest "$CACHE_ROOT" host 0770
else
  log "host $CACHE_ROOT absent (ok if native cache not installed yet)"
fi

# Colima VM tree (Docker agents). Cap is per-tree (see docs/ci-cache.md).
still=$(any_workflow_running 2>/dev/null || echo 1)
if [ "$still" != "0" ]; then
  log "skip colima prune: $still workflow(s) running"
  exit 0
fi
if docker info >/dev/null 2>&1; then
  # shellcheck disable=SC2016
  docker run --rm --privileged \
    -e CACHE_ROOT="$CACHE_ROOT" \
    -e CAP_BYTES="$CAP_BYTES" \
    -v /var/lib:/var/lib \
    alpine:3.22 \
    sh -c '
      set -eu
      ROOT="$CACHE_ROOT"
      CAP="$CAP_BYTES"
      if [ ! -d "$ROOT" ]; then
        echo "colima $ROOT absent"
        exit 0
      fi
      used=$(du -sk "$ROOT" | awk "{print \$1 * 1024}")
      echo "colima $ROOT used=$used cap=$CAP"
      if [ "$used" -le "$CAP" ]; then
        exit 0
      fi
      find "$ROOT" -mindepth 2 -maxdepth 2 -type d -exec stat -c "%Y %n" {} \; \
        | sort -n | while read -r mtime path; do
        used=$(du -sk "$ROOT" | awk "{print \$1 * 1024}")
        [ "$used" -gt "$CAP" ] || break
        echo "colima prune $path (mtime=$mtime)"
        rm -rf "$path"
        mkdir -p "$path"
        chmod 0750 "$path"
      done
    ' | while IFS= read -r line; do
    log "$line"
  done
else
  log "colima context unavailable; skipped VM cleanup"
fi
