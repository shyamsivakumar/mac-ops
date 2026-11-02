#!/bin/sh
# Pause scheduling, wait until the named agent(s) are idle, refuse if an SRW
# deploy is running. Woodpecker cancels in-flight workflows on agent shutdown.
#
# Usage: drain-agent.sh <ci-linux|ci-deploy|native|all> [timeout_sec]
#         drain-agent.sh --resume <opid>
#
# Each drain creates an operation id. Ownership records only pauses this drain
# system created (plus agents already claimed by other drain ops). Independent
# operator pauses are never claimed or cleared. Only the drain waiter clears
# its own active marker on EXIT; --resume never touches another op's active.
set -eu

# shellcheck source=common.sh disable=SC1091
. "$(dirname -- "$0")/common.sh"

STATE_DIR="$HOME/Library/Logs/woodpecker"
OPS_DIR="$STATE_DIR/drain-ops"
LOCK_DIR="$STATE_DIR/drain-owned.lock"
mkdir -p "$STATE_DIR" "$OPS_DIR"

op_dir=
drain_lock_held=0
# Only the process that created this drain's active marker may clear it.
owns_active_cleanup=0

acquire_drain_lock() {
  tries=0
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
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

on_exit() {
  if [ "$owns_active_cleanup" -eq 1 ] && [ -n "$op_dir" ] && [ -d "$op_dir" ]; then
    rm -f "$op_dir/active"
  fi
  release_drain_lock
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

agents_still_owned() {
  skip=${1:-}
  for d in "$OPS_DIR"/*; do
    [ -d "$d" ] || continue
    base=$(basename "$d")
    if [ -n "$skip" ] && [ "$base" = "$skip" ]; then
      continue
    fi
    if [ -f "$d/ids" ]; then
      cat "$d/ids"
    fi
  done | awk 'NF' | sort -u
}

overlapping_active_ops() {
  opid=$1
  my_ids="$OPS_DIR/$opid/ids"
  [ -f "$my_ids" ] || return 1
  for d in "$OPS_DIR"/*; do
    [ -d "$d" ] || continue
    other=$(basename "$d")
    [ "$other" != "$opid" ] || continue
    [ -f "$d/active" ] || continue
    [ -f "$d/ids" ] || continue
    if awk 'NR==FNR{a[$1]=1; next} $1 in a{found=1; exit} END{exit !found}' \
      "$my_ids" "$d/ids"; then
      return 0
    fi
  done
  return 1
}

persist_owned_ids() {
  # Write ownership file durably (temp + rename) under the drain lock.
  dest=$1
  shift
  tmp="$dest.tmp.$$"
  printf '%s\n' "$@" | tr -s '[:space:]' '\n' | awk 'NF' | sort -u >"$tmp"
  mv -f "$tmp" "$dest"
}

if [ "${1:-}" = "--resume" ]; then
  opid=${2:?usage: drain-agent.sh --resume <opid>}
  # Do not set owns_active_cleanup — a refused resume must not clear the
  # waiter process's active marker.
  op_dir="$OPS_DIR/$opid"
  acquire_drain_lock
  if [ ! -d "$op_dir" ] || [ ! -f "$op_dir/ids" ]; then
    echo "Unknown or already resumed drain op: $opid" >&2
    exit 1
  fi
  if [ -f "$op_dir/active" ]; then
    echo "Drain op $opid is still active (idle wait); refusing --resume." >&2
    exit 1
  fi
  if overlapping_active_ops "$opid"; then
    echo "Another active drain overlaps op $opid agents; refusing --resume." >&2
    exit 1
  fi
  still=$(agents_still_owned "$opid" | tr '\n' ' ')
  clear_ids=
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    case " $still " in
      *" $id "*) ;;
      *) clear_ids="$clear_ids $id" ;;
    esac
  done <"$op_dir/ids"
  clear_ids=$(printf '%s' "$clear_ids" | sed 's/^ *//')
  if [ -n "$(printf '%s' "$clear_ids" | tr -d '[:space:]')" ]; then
    in_list=$(printf '%s' "$clear_ids" | tr ' ' ',' | sed 's/,$//;s/^,//')
    write_db "UPDATE agents SET no_schedule = 0
      WHERE id IN ($in_list) AND no_schedule != 0;" >/dev/null
    printf 'Scheduling resumed on agent id(s): %s (op %s)\n' "$clear_ids" "$opid"
  else
    printf 'Op %s released; agents still held by other drain ops.\n' "$opid"
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
: >"$op_dir/active"
owns_active_cleanup=1
: >"$op_dir/ids"

in_list=$(printf '%s' "$pause_ids" | tr ' ' ',' | sed 's/,$//;s/^,//')
acquire_drain_lock

# Persist recoverable ownership BEFORE the pause commit: agents we will flip,
# plus targets already claimed by other drain ops.
will_flip=$(query_db "SELECT id FROM agents
  WHERE id IN ($in_list) AND IFNULL(no_schedule, 0) = 0;")
already=$(agents_still_owned | tr '\n' ' ')
pre_ids=
for id in $will_flip; do
  pre_ids="$pre_ids $id"
done
for id in $pause_ids; do
  case " $already " in
    *" $id "*) pre_ids="$pre_ids $id" ;;
  esac
done
persist_owned_ids "$op_dir/ids" "$pre_ids"

owned=$(write_db "
BEGIN IMMEDIATE;
UPDATE agents
  SET no_schedule = 1
  WHERE id IN ($in_list) AND IFNULL(no_schedule, 0) = 0
  RETURNING id;
COMMIT;
")
owned=$(printf '%s' "$owned" | tr '\n' ' ' | sed 's/[[:space:]]*$//')

# Refresh ownership from RETURNING + drain-owned refs (should match pre_ids).
already=$(agents_still_owned "$opid" | tr '\n' ' ')
post_ids=$owned
for id in $pause_ids; do
  case " $already " in
    *" $id "*) post_ids="$post_ids $id" ;;
  esac
done
persist_owned_ids "$op_dir/ids" "$post_ids"

if [ -n "$(printf '%s' "$owned" | tr -d '[:space:]')" ]; then
  printf 'Set no_schedule=1 on drain-created pause id(s): %s\n' "$owned"
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
