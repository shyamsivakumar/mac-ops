#!/bin/sh
# Keep Colima + missing stack containers up. Starts missing services only
# (compose --no-recreate). Retains the SRW deploy guard for Docker agents.
# Re-checks missing services even when Colima is already running so agents
# left down under the deploy guard are brought up on a later pass.
#
# MO-121: never kickstart -k Colima while Docker still answers without
# draining first. Undrained Colima/agent kills show up as docker.sock
# "Canceled" infra failures on in-flight SRW/mac-ops workflows.
# Persist the drain opid across watchdog invocations so a failed recovery
# pass can still release no_schedule on a later successful pass.
set -eu

# shellcheck disable=SC1091
. "$(dirname -- "$0")/common.sh"

LOG_DIR="$HOME/Library/Logs/woodpecker"
LOG="$LOG_DIR/watchdog.log"
DRAIN_HOLD_FILE="$LOG_DIR/watchdog-drain-opid"
DOMAIN="gui/$(id -u)"
mkdir -p "$LOG_DIR"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >>"$LOG"
}

docker_reachable() {
  docker ps -q >/dev/null 2>&1
}

read_held_drain_opid() {
  if [ -f "$DRAIN_HOLD_FILE" ]; then
    tr -d '[:space:]' <"$DRAIN_HOLD_FILE"
  fi
}

persist_held_drain_opid() {
  opid=$1
  if [ -z "$opid" ]; then
    return 0
  fi
  printf '%s\n' "$opid" >"$DRAIN_HOLD_FILE"
  log "Persisted drain op $opid in $DRAIN_HOLD_FILE"
}

clear_held_drain_opid() {
  rm -f "$DRAIN_HOLD_FILE"
}

# Resume a held drain only after all agents are process-up and contacting.
resume_held_drain_if_ready() {
  drain="$ROOT/scripts/drain-agent.sh"
  opid=$(read_held_drain_opid)
  if [ -z "$opid" ]; then
    return 0
  fi
  if [ ! -x "$drain" ]; then
    log "Held drain $opid but drain-agent.sh missing; cannot resume."
    return 1
  fi
  if ! docker_reachable; then
    log "Held drain $opid; Docker not ready yet — will retry next pass."
    return 0
  fi

  start_missing_services
  ensure_native_agent

  ready_log=$(mktemp "${TMPDIR:-/tmp}/mo121-watchdog-ready.XXXXXX")
  ready_rc=0
  wait_agents_ready all 180 >"$ready_log" 2>&1 || ready_rc=$?
  while IFS= read -r line; do
    log "ready: $line"
  done <"$ready_log"
  rm -f "$ready_log"
  if [ "$ready_rc" -ne 0 ]; then
    log "Held drain $opid; agents not ready yet — will retry next pass."
    return 0
  fi

  if "$drain" --resume "$opid" >>"$LOG" 2>&1; then
    log "Resumed held drain $opid after verified agent readiness."
    clear_held_drain_opid
    return 0
  fi
  log "Failed to resume held drain $opid; leaving hold file for next pass."
  return 1
}

# Pause agents via drain when the engine is still up, then hard-restart Colima.
# If Docker is already dead, only kickstart (prefer without -k) and bring the
# compose services back — the sock drop already canceled in-flight jobs.
# If a prior pass already held a drain, do not open a second overlapping op.
restart_colima() {
  drain="$ROOT/scripts/drain-agent.sh"
  opid=$(read_held_drain_opid)

  if [ -n "$opid" ]; then
    log "Reusing held drain $opid from a prior pass; not opening a new drain."
  elif docker_reachable; then
    if [ "$(srw_deploy_running)" != "0" ]; then
      log "Colima unhealthy but SRW deploy running; refusing kickstart -k."
      exit 2
    fi
    if [ -x "$drain" ]; then
      log "Docker still reachable; draining all agents before Colima kickstart -k."
      drain_log=$(mktemp "${TMPDIR:-/tmp}/mo121-watchdog-drain.XXXXXX")
      drain_rc=0
      "$drain" all 900 >"$drain_log" 2>&1 || drain_rc=$?
      while IFS= read -r line; do
        log "drain: $line"
      done <"$drain_log"
      opid=$(awk -F= '/^DRAIN_OPID=/{print $2; exit}' "$drain_log")
      rm -f "$drain_log"
      # Persist as soon as we own a drain so a later crash cannot strand it
      # without a recorded opid.
      if [ -n "$opid" ]; then
        persist_held_drain_opid "$opid"
      fi
      if [ "$drain_rc" -ne 0 ]; then
        log "Drain failed (rc=$drain_rc); not kickstarting Colima."
        exit "$drain_rc"
      fi
      if [ -z "$opid" ]; then
        log "Drain printed no DRAIN_OPID; not kickstarting Colima."
        exit 1
      fi
    else
      log "drain-agent.sh missing; refusing Colima kickstart -k while Docker is up."
      exit 1
    fi
  else
    log "Docker already unreachable; Colima recovery without drain (sock already gone)."
  fi

  # Prefer a non-kill start when the LaunchAgent is not loaded; use -k only when
  # we drained (or Docker was already dead) so a wedged foreground colima exits.
  if launchctl print "$DOMAIN/com.shyamsivakumar.colima-woodpecker" >/dev/null 2>&1; then
    log "kickstart -k com.shyamsivakumar.colima-woodpecker"
    launchctl kickstart -k "$DOMAIN/com.shyamsivakumar.colima-woodpecker"
  else
    log "bootstrapping com.shyamsivakumar.colima-woodpecker"
    launchctl bootstrap "$DOMAIN" \
      "$HOME/Library/LaunchAgents/com.shyamsivakumar.colima-woodpecker.plist" 2>/dev/null \
      || launchctl kickstart "$DOMAIN/com.shyamsivakumar.colima-woodpecker"
  fi

  deadline=$(($(date +%s) + 180))
  until "$COLIMA" status woodpecker >/dev/null 2>&1 && docker_reachable; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      log "Colima did not become ready within 180 seconds."
      if [ -n "$opid" ]; then
        log "Drain $opid remains held in $DRAIN_HOLD_FILE for a later pass."
      fi
      exit 1
    fi
    sleep 3
  done
  log "Colima is running."
}

start_missing_services() {
  missing=
  for service in server agent-linux agent-deploy webhook-proxy; do
    if [ -z "$(compose ps --status running -q "$service" 2>/dev/null)" ]; then
      missing="$missing $service"
    fi
  done
  missing=$(printf '%s' "$missing" | sed 's/^ *//')

  if [ -z "$missing" ]; then
    return 0
  fi

  if [ "$(srw_deploy_running)" != "0" ]; then
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
    # Missing agents: start only (--no-recreate). Never force-recreate here;
    # use safe-restart.sh when a recreate is required.
    log "compose up -d --no-recreate for missing: $missing"
    # shellcheck disable=SC2086
    compose up -d --no-recreate $missing
  fi
}

ensure_native_agent() {
  native_pid=$(launchctl list 2>/dev/null | awk '$3=="org.woodpecker.agent"{print $1; exit}')
  case "$native_pid" in
    '' | -)
      if [ "$(srw_deploy_running)" != "0" ]; then
        log "Native agent not loaded but SRW deploy running; not bootstrapping."
        return 0
      fi
      log "Native agent not loaded; bootstrapping LaunchAgent (no -k)."
      launchctl bootstrap "$DOMAIN" \
        "$HOME/Library/LaunchAgents/org.woodpecker.agent.plist" 2>/dev/null \
        || launchctl kickstart "$DOMAIN/org.woodpecker.agent"
      ;;
    *)
      :
      ;;
  esac
}

if ! "$COLIMA" status woodpecker >/dev/null 2>&1; then
  log "Colima profile woodpecker is not running; recovering."
  restart_colima
fi

# Always inspect missing services while Colima is up (including later passes
# after an SRW-guarded recovery left agents down).
if ! docker_reachable; then
  log "Docker context not ready yet; deferring service check."
  # Keep any held drain for a later pass; do not clear the hold file.
  exit 0
fi

start_missing_services
ensure_native_agent

# Release this pass's drain and any stranded hold from a prior failed pass,
# but only after agents are verified ready.
resume_held_drain_if_ready
