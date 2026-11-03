#!/bin/sh
# MO-120: enforce a size cap on /var/lib/woodpecker-cache.
# Deletes oldest repo/kind trees first until under CAP_BYTES.
# Safe for LaunchAgent or cron. Never touches secrets (caches only).
#
# Env:
#   CACHE_ROOT   default /var/lib/woodpecker-cache
#   CAP_BYTES    default 20GiB (21474836480)
#   LOG_FILE     default ~/Library/Logs/woodpecker/cache-cleanup.log
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
export PATH

CACHE_ROOT=${CACHE_ROOT:-/var/lib/woodpecker-cache}
CAP_BYTES=${CAP_BYTES:-21474836480}
LOG_FILE=${LOG_FILE:-$HOME/Library/Logs/woodpecker/cache-cleanup.log}
DOCKER=${DOCKER:-/opt/homebrew/bin/docker}
CONTEXT=${CONTEXT:-colima-woodpecker}

mkdir -p "$(dirname "$LOG_FILE")"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
log() { printf '%s %s\n' "$ts" "$*" | tee -a "$LOG_FILE"; }

# Host tree (native agent).
if [ -d "$CACHE_ROOT" ]; then
  used=$(du -sk "$CACHE_ROOT" | awk '{print $1 * 1024}')
  log "host $CACHE_ROOT used=$used cap=$CAP_BYTES"
  if [ "$used" -gt "$CAP_BYTES" ]; then
    # Oldest leaf kind dirs first.
    du -sk "$CACHE_ROOT"/*/* 2>/dev/null | sort -n | while read -r _kb path; do
      used=$(du -sk "$CACHE_ROOT" | awk '{print $1 * 1024}')
      [ "$used" -gt "$CAP_BYTES" ] || break
      log "host prune $path"
      rm -rf "$path"
      mkdir -p "$path"
    done
  fi
else
  log "host $CACHE_ROOT absent (ok if native cache not installed yet)"
fi

# Colima VM tree (Docker agents).
if "$DOCKER" --context "$CONTEXT" info >/dev/null 2>&1; then
  # shellcheck disable=SC2016
  "$DOCKER" --context "$CONTEXT" run --rm --privileged \
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
      du -sk "$ROOT"/*/* 2>/dev/null | sort -n | while read -r _kb path; do
        used=$(du -sk "$ROOT" | awk "{print \$1 * 1024}")
        [ "$used" -gt "$CAP" ] || break
        echo "colima prune $path"
        rm -rf "$path"
        mkdir -p "$path"
        chmod 0750 "$path"
      done
    ' | while IFS= read -r line; do
    log "$line"
  done
else
  log "colima context $CONTEXT unavailable; skipped VM cleanup"
fi
