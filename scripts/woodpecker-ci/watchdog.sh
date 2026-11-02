#!/bin/sh
# Recover a stopped Colima VM. Starts missing stack containers only.
# Does not recreate healthy running services (compose --no-recreate and
# only names the missing ones). Does not restart the native agent if loaded.
set -eu

# shellcheck disable=SC1091
. "$(dirname -- "$0")/common.sh"

LOG_DIR="$HOME/Library/Logs/woodpecker"
LOG="$LOG_DIR/watchdog.log"
DOMAIN="gui/$(id -u)"
mkdir -p "$LOG_DIR"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >>"$LOG"
}

"$COLIMA" status woodpecker >/dev/null 2>&1 && exit 0

log "Colima profile woodpecker is not running; restarting its LaunchAgent."
launchctl kickstart -k "$DOMAIN/com.shyamsivakumar.colima-woodpecker"

deadline=$(($(date +%s) + 180))
until "$COLIMA" status woodpecker >/dev/null 2>&1 && docker ps -q >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    log "Colima did not become ready within 180 seconds."
    exit 1
  fi
  sleep 3
done
log "Colima is running."

missing=
for service in server agent-linux agent-deploy webhook-proxy; do
  if [ -z "$(compose ps --status running -q "$service" 2>/dev/null)" ]; then
    missing="$missing $service"
  fi
done
missing=$(printf '%s' "$missing" | sed 's/^ *//')

if [ -n "$missing" ]; then
  if [ "$(srw_deploy_running)" != "0" ]; then
    # Never bring Docker agents up under a live SRW deploy row.
    start=
    case " $missing " in
      *" server "*) start="$start server" ;;
    esac
    case " $missing " in
      *" webhook-proxy "*) start="$start webhook-proxy" ;;
    esac
    start=$(printf '%s' "$start" | sed 's/^ *//')
    if [ -n "$start" ]; then
      log "SRW deploy marked running; compose up --no-recreate: $start"
      # shellcheck disable=SC2086
      compose up -d --no-recreate $start
    else
      log "SRW deploy marked running; missing only agents — leaving them down."
    fi
  else
    log "compose up -d --no-recreate for missing: $missing"
    # shellcheck disable=SC2086
    compose up -d --no-recreate $missing
  fi
else
  log "All compose services already running; nothing to start."
fi

native_pid=$(launchctl list 2>/dev/null | awk '$3=="org.woodpecker.agent"{print $1; exit}')
case "$native_pid" in
  '' | -)
    log "Native agent not loaded; bootstrapping LaunchAgent (no -k)."
    launchctl bootstrap "$DOMAIN" \
      "$HOME/Library/LaunchAgents/org.woodpecker.agent.plist" 2>/dev/null \
      || launchctl kickstart "$DOMAIN/org.woodpecker.agent"
    ;;
  *)
    log "Native agent pid=$native_pid left running."
    ;;
esac

log "Recovery finished (missing-only, --no-recreate)."
