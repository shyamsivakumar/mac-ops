#!/bin/sh
# Pause scheduling, wait until the named agent(s) are idle, refuse if an SRW
# deploy is running. Woodpecker cancels in-flight workflows on agent shutdown.
#
# Usage: drain-agent.sh <ci-linux|ci-deploy|native|all> [timeout_sec]
#         drain-agent.sh --resume <opid>
#
# Ownership lives in woodpecker.sqlite table mo117_drain_owned, written in the
# same BEGIN IMMEDIATE transaction as the no_schedule flip (RETURNING-equivalent
# via a temp flipped set). Host drain-ops/<opid>/ids mirrors that for operators.
# Stale mkdir locks and active markers (dead owner pid) are reclaimed safely.
set -eu

# shellcheck source=common.sh disable=SC1091
. "$(dirname -- "$0")/common.sh"

STATE_DIR="$HOME/Library/Logs/woodpecker"
OPS_DIR="$STATE_DIR/drain-ops"
LOCK_DIR="$STATE_DIR/drain-owned.lock"
mkdir -p "$STATE_DIR" "$OPS_DIR"

op_dir=
drain_lock_held=0
owns_active_cleanup=0

pid_alive() {
  kill -0 "$1" 2>/dev/null
}

acquire_drain_lock() {
  tries=0
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    if [ -f "$LOCK_DIR/pid" ]; then
      oldpid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
      case "$oldpid" in
        '' | *[!0-9]*)
          echo "Removing corrupt drain lock dir." >&2
          rm -rf "$LOCK_DIR"
          continue
          ;;
      esac
      if ! pid_alive "$oldpid"; then
        echo "Removing stale drain lock (dead pid $oldpid)." >&2
        rm -rf "$LOCK_DIR"
        continue
      fi
    else
      # Lock dir without pid — treat as stale after a short settle.
      if [ "$tries" -ge 5 ]; then
        echo "Removing drain lock dir with no pid file." >&2
        rm -rf "$LOCK_DIR"
        continue
      fi
    fi
    tries=$((tries + 1))
    if [ "$tries" -ge 600 ]; then
      echo "Timed out waiting for drain ownership lock ($LOCK_DIR)." >&2
      exit 1
    fi
    sleep 0.1
  done
  printf '%s\n' "$$" >"$LOCK_DIR/pid"
  drain_lock_held=1
}

release_drain_lock() {
  if [ "$drain_lock_held" -eq 1 ]; then
    rm -rf "$LOCK_DIR"
    drain_lock_held=0
  fi
}

# Clear active only if this process created it, or if the recorded waiter is dead.
reclaim_stale_active() {
  d=$1
  [ -f "$d/active" ] || return 0
  apid=$(cat "$d/active" 2>/dev/null || true)
  case "$apid" in
    '' | *[!0-9]*)
      echo "Clearing corrupt active marker in $d." >&2
      rm -f "$d/active"
      return 0
      ;;
  esac
  if ! pid_alive "$apid"; then
    echo "Clearing stale active marker in $d (dead pid $apid)." >&2
    rm -f "$d/active"
  fi
}

sweep_stale_actives() {
  for d in "$OPS_DIR"/*; do
    [ -d "$d" ] || continue
    reclaim_stale_active "$d"
  done
}

on_exit() {
  if [ "$owns_active_cleanup" -eq 1 ] && [ -n "$op_dir" ] && [ -d "$op_dir" ]; then
    rm -f "$op_dir/active"
  fi
  release_drain_lock
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

persist_ids_file() {
  dest=$1
  shift
  tmp="$dest.tmp.$$"
  printf '%s\n' "$@" | tr -s '[:space:]' '\n' | awk 'NF' | sort -u >"$tmp"
  mv -f "$tmp" "$dest"
}

# DB-backed ownership helpers (same sqlite volume as Woodpecker).
claim_pause_txn() {
  opid=$1
  in_list=$2
  write_db "
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS mo117_drain_owned (
  opid TEXT NOT NULL,
  agent_id INTEGER NOT NULL,
  PRIMARY KEY (opid, agent_id)
);
CREATE TEMP TABLE flipped AS
  SELECT id AS agent_id FROM agents
  WHERE id IN ($in_list) AND IFNULL(no_schedule, 0) = 0;
UPDATE agents
  SET no_schedule = 1
  WHERE id IN (SELECT agent_id FROM flipped);
INSERT OR IGNORE INTO mo117_drain_owned (opid, agent_id)
  SELECT '$opid', agent_id FROM flipped;
INSERT OR IGNORE INTO mo117_drain_owned (opid, agent_id)
  SELECT '$opid', d.agent_id FROM mo117_drain_owned d
  WHERE d.agent_id IN ($in_list) AND d.opid != '$opid';
SELECT agent_id FROM mo117_drain_owned WHERE opid = '$opid' ORDER BY agent_id;
SELECT 'FLIPPED';
SELECT agent_id FROM flipped ORDER BY agent_id;
COMMIT;
"
}

resume_op_txn() {
  opid=$1
  write_db "
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS mo117_drain_owned (
  opid TEXT NOT NULL,
  agent_id INTEGER NOT NULL,
  PRIMARY KEY (opid, agent_id)
);
CREATE TEMP TABLE clearing AS
  SELECT agent_id FROM mo117_drain_owned WHERE opid = '$opid'
  AND agent_id NOT IN (
    SELECT agent_id FROM mo117_drain_owned WHERE opid != '$opid'
  );
UPDATE agents SET no_schedule = 0
  WHERE id IN (SELECT agent_id FROM clearing) AND no_schedule != 0;
DELETE FROM mo117_drain_owned WHERE opid = '$opid';
SELECT agent_id FROM clearing ORDER BY agent_id;
COMMIT;
"
}

other_active_overlap() {
  opid=$1
  # Overlap if another op still has active and shares a DB-owned agent.
  my_ids=$(query_db "SELECT agent_id FROM mo117_drain_owned WHERE opid = '$opid';" || true)
  [ -n "$(printf '%s' "$my_ids" | tr -d '[:space:]')" ] || return 1
  for d in "$OPS_DIR"/*; do
    [ -d "$d" ] || continue
    other=$(basename "$d")
    [ "$other" != "$opid" ] || continue
    reclaim_stale_active "$d"
    [ -f "$d/active" ] || continue
    other_ids=$(query_db "SELECT agent_id FROM mo117_drain_owned WHERE opid = '$other';" || true)
    if [ -z "$(printf '%s' "$other_ids" | tr -d '[:space:]')" ]; then
      continue
    fi
    if printf '%s\n%s\n' "$my_ids" "$other_ids" | awk 'NF{c[$1]++; if(c[$1]>1){found=1; exit}} END{exit !found}'; then
      return 0
    fi
  done
  return 1
}

if [ "${1:-}" = "--resume" ]; then
  opid=${2:?usage: drain-agent.sh --resume <opid>}
  op_dir="$OPS_DIR/$opid"
  sweep_stale_actives
  acquire_drain_lock
  write_db "CREATE TABLE IF NOT EXISTS mo117_drain_owned (
    opid TEXT NOT NULL,
    agent_id INTEGER NOT NULL,
    PRIMARY KEY (opid, agent_id)
  );" >/dev/null
  if [ ! -d "$op_dir" ]; then
    # Allow resume from DB even if host dir was lost.
    mkdir -p "$op_dir"
  fi
  reclaim_stale_active "$op_dir"
  if [ -f "$op_dir/active" ]; then
    echo "Drain op $opid is still active (idle wait); refusing --resume." >&2
    exit 1
  fi
  owned_n=$(query_db "SELECT COUNT(*) FROM mo117_drain_owned WHERE opid = '$opid';" 2>/dev/null || echo 0)
  if [ "$owned_n" = "0" ] && [ ! -s "$op_dir/ids" ]; then
    echo "Unknown or already resumed drain op: $opid" >&2
    exit 1
  fi
  if other_active_overlap "$opid"; then
    echo "Another active drain overlaps op $opid agents; refusing --resume." >&2
    exit 1
  fi
  cleared=$(resume_op_txn "$opid")
  cleared=$(printf '%s' "$cleared" | tr '\n' ' ' | sed 's/[[:space:]]*$//')
  if [ -n "$(printf '%s' "$cleared" | tr -d '[:space:]')" ]; then
    printf 'Scheduling resumed on agent id(s): %s (op %s)\n' "$cleared" "$opid"
  else
    printf 'Op %s released; agents still held by other drain ops (or none flipped).\n' "$opid"
  fi
  rm -rf "$op_dir"
  op_dir=
  exit 0
fi

agent_name=${1:?usage: drain-agent.sh <ci-linux|ci-deploy|native|all|--resume> [timeout_sec|opid]}
timeout_sec=${2:-1800}
started=$(date +%s)
opid="$(date +%Y%m%dT%H%M%S)-$$"
op_dir="$OPS_DIR/$opid"

wp_containers() {
  docker ps --filter name=wp_ -q | wc -l | tr -d ' '
}

agent_ids_for() {
  case "$1" in
    ci-linux) docker_check_agent_ids ;;
    ci-deploy) docker_deploy_agent_ids ;;
    native) native_agent_ids ;;
    *)
      echo "unknown agent target: $1" >&2
      return 1
      ;;
  esac
}

running_on_ids() {
  ids=$1
  [ -n "$ids" ] || {
    echo 0
    return
  }
  in_list=$(printf '%s' "$ids" | tr '\n' ',' | sed 's/,$//')
  query_db "SELECT COUNT(*) FROM workflows
    WHERE state = 'running' AND agent_id IN ($in_list);"
}

native_agent_busy() {
  pid=$(launchctl list 2>/dev/null | awk '$3=="org.woodpecker.agent"{print $1; exit}')
  case "$pid" in
    '' | -)
      echo 0
      return
      ;;
  esac
  if pgrep -P "$pid" >/dev/null 2>&1; then
    echo 1
  else
    echo 0
  fi
}

sweep_stale_actives

if [ "$(srw_deploy_running)" != "0" ]; then
  echo "SRW deploy workflow is running; refusing to drain/restart." >&2
  exit 2
fi

targets=
case "$agent_name" in
  ci-linux) targets="ci-linux" ;;
  ci-deploy) targets="ci-deploy" ;;
  native) targets="native" ;;
  all) targets="ci-linux ci-deploy native" ;;
  *)
    echo "unknown agent: $agent_name" >&2
    exit 1
    ;;
esac

pause_ids=
for t in $targets; do
  if ! ids=$(agent_ids_for "$t"); then
    echo "Failed to look up agent ids for $t." >&2
    exit 1
  fi
  if [ -z "$(printf '%s' "$ids" | tr -d '[:space:]')" ]; then
    echo "No agents matched target $t; refusing to drain." >&2
    exit 1
  fi
  pause_ids="$pause_ids $ids"
done
pause_ids=$(printf '%s' "$pause_ids" | tr ' ' '\n' | awk 'NF' | sort -u | tr '\n' ' ')

mkdir -p "$op_dir"
printf '%s\n' "$$" >"$op_dir/active"
owns_active_cleanup=1

in_list=$(printf '%s' "$pause_ids" | tr ' ' ',' | sed 's/,$//;s/^,//')
acquire_drain_lock

txn_out=$(claim_pause_txn "$opid" "$in_list")
# Parse ids before FLIPPED marker and flipped list after.
owned=$(printf '%s\n' "$txn_out" | awk 'BEGIN{p=1} /^FLIPPED$/{p=0; next} p' | tr '\n' ' ' | sed 's/[[:space:]]*$//')
flipped=$(printf '%s\n' "$txn_out" | awk 'BEGIN{p=0} /^FLIPPED$/{p=1; next} p' | tr '\n' ' ' | sed 's/[[:space:]]*$//')

persist_ids_file "$op_dir/ids" "$owned"

if [ -n "$(printf '%s' "$flipped" | tr -d '[:space:]')" ]; then
  printf 'Set no_schedule=1 on drain-created pause id(s): %s\n' "$flipped"
else
  printf 'No new pauses created (targets already paused); op claims only drain-owned refs.\n'
fi
release_drain_lock

printf 'DRAIN_OPID=%s\n' "$opid"
printf 'Draining %s (timeout %ss, op %s)...\n' "$agent_name" "$timeout_sec" "$opid"

while true; do
  if [ "$(srw_deploy_running)" != "0" ]; then
    echo "SRW deploy started during drain; aborting (ownership retained, active cleared on exit)." >&2
    exit 2
  fi
  busy=0
  for t in $targets; do
    if ! ids=$(agent_ids_for "$t"); then
      echo "Failed to look up agent ids for $t during wait." >&2
      exit 1
    fi
    if [ -z "$(printf '%s' "$ids" | tr -d '[:space:]')" ]; then
      echo "Agent lookup for $t returned empty during wait." >&2
      exit 1
    fi
    if [ "$t" = "native" ]; then
      if [ "$(native_agent_busy)" != "0" ]; then
        busy=1
        printf '  native agent still has child processes\n'
      fi
      if [ "$(running_on_ids "$ids")" != "0" ]; then
        busy=1
        printf '  native agent still has DB running workflow(s)\n'
      fi
      continue
    fi
    c=$(running_on_ids "$ids")
    if [ "$c" != "0" ]; then
      busy=1
      printf '  %s still has %s running workflow(s)\n' "$t" "$c"
    fi
  done
  if [ "$busy" -eq 0 ]; then
    need_wp=0
    case "$agent_name" in
      ci-linux | all) need_wp=1 ;;
    esac
    if [ "$need_wp" -eq 1 ] && [ "$(wp_containers)" != "0" ]; then
      printf '  waiting for %s wp_* container(s)\n' "$(wp_containers)"
    else
      rm -f "$op_dir/active"
      owns_active_cleanup=0
      printf 'Drain complete for %s (op %s held until --resume %s).\n' \
        "$agent_name" "$opid" "$opid"
      exit 0
    fi
  fi
  if [ $(($(date +%s) - started)) -ge "$timeout_sec" ]; then
    echo "Drain timed out after ${timeout_sec}s (ownership retained for --resume $opid; active cleared on exit)." >&2
    exit 1
  fi
  sleep 5
done
