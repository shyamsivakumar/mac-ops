#!/bin/sh
# Recover a stopped Colima VM. Starts missing stack containers only.
# Does not restart healthy Docker agents or the native agent (that would
# cancel in-flight work, including SRW deploy).
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

# Start only services that are not already running. Never compose restart.
need_up=0
for service in server agent-linux agent-deploy webhook-proxy; do
  if [ -z "$(compose ps --status running -q "$service" 2>/dev/null)" ]; then
    log "Service $service is not running; will compose up -d."
    need_up=1
  fi
done
if [ "$need_up" -eq 1 ]; then
  # Refuse to bring agents up while an SRW deploy DB row is somehow mid-flight
  # on a surviving native path; Docker agents were down with Colima anyway.
  if [ "$(srw_deploy_running)" != "0" ]; then
    log "SRW deploy marked running; composing server/webhook only."
    compose up -d server webhook-proxy
  else
    compose up -d
  fi
fi

# Native agent: start only if LaunchAgent is not running.
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

log "Recovery finished (no blanket agent restart)."
