#!/bin/sh
set -eu

# shellcheck source=common.sh
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

for service in server agent-linux agent-deploy webhook-proxy; do
  if [ -z "$(compose ps --status running -q "$service")" ]; then
    log "Starting containers with compose up -d."
    compose up -d
    break
  fi
done

log "Restarting the Docker agents and the native agent."
compose restart agent-linux agent-deploy
launchctl kickstart -k "$DOMAIN/org.woodpecker.agent"
log "Recovery finished."
