#!/bin/sh
# Pause scheduling, wait until the named agent(s) are idle, refuse if an SRW
# deploy is running. Woodpecker cancels in-flight workflows on agent shutdown.
#
# Usage: drain-agent.sh [--hold-file PATH] <ci-linux|ci-deploy|native|all> [timeout_sec]
#         drain-agent.sh --resume <opid>
#         drain-agent.sh --extend-op <opid>
#
# Ownership lives in woodpecker.sqlite table mo117_drain_owned, written in the
# same BEGIN IMMEDIATE transaction as the no_schedule flip. Host
# drain-ops/<opid>/ids mirrors that for operators. Mutual exclusion uses
# fcntl.flock (kernel-owned; released on process death). `all` treats
# ci-deploy as optional when absent; --extend-op claims agents that register
# after the initial drain (new deploy lane) into an open op.
# --hold-file writes the opid as soon as the pause is claimed (before the idle
# wait) so a killed drain still leaves a durable resume handle.
set -eu

# shellcheck source=common.sh disable=SC1091
. "$(dirname -- "$0")/common.sh"

STATE_DIR="$HOME/Library/Logs/woodpecker"
OPS_DIR="$STATE_DIR/drain-ops"
LOCK_FILE="$STATE_DIR/drain-owned.flock"
mkdir -p "$STATE_DIR" "$OPS_DIR"

op_dir=
drain_lock_held=0
owns_active_cleanup=0
DRAIN_LOCK_PY=
HOLD_FILE=
# Incomplete active publish older than this may be reclaimed.
STALE_PUBLISH_SECS=10

while [ "$#" -gt 0 ]; do
  case "$1" in
    --hold-file)
      HOLD_FILE=${2:?--hold-file needs a path}
      shift 2
      ;;
    *)
      break
      ;;
  esac
done

pid_alive() {
  kill -0 "$1" 2>/dev/null
}

file_age_secs() {
  f=$1
  now=$(date +%s)
  mtime=$(stat -f %m "$f" 2>/dev/null || echo "$now")
  echo $((now - mtime))
}

# Hold an exclusive flock in a child until release_drain_lock. The kernel drops
# the lock if the holder dies (including SIGKILL), so no stale-dir reclaim.
acquire_drain_lock() {
  if [ "$drain_lock_held" -eq 1 ]; then
    return 0
  fi
  DRAIN_LOCK_READY="$STATE_DIR/drain-lock-ready.$$"
  DRAIN_LOCK_RELEASE="$STATE_DIR/drain-lock-release.$$"
  rm -f "$DRAIN_LOCK_READY" "$DRAIN_LOCK_RELEASE"
  python3 -u - "$LOCK_FILE" "$DRAIN_LOCK_READY" "$DRAIN_LOCK_RELEASE" <<'PY' &
import fcntl
import os
import sys
import time

lock_path, ready_path, release_path = sys.argv[1], sys.argv[2], sys.argv[3]
parent = os.getppid()
fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
deadline = time.time() + 60.0
while True:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        break
    except (BlockingIOError, OSError):
        if time.time() >= deadline:
            sys.stderr.write("Timed out waiting for drain flock\n")
            sys.exit(1)
        time.sleep(0.1)
os.lseek(fd, 0, os.SEEK_SET)
os.ftruncate(fd, 0)
os.write(fd, b"%d\n" % os.getpid())
with open(ready_path, "w", encoding="utf-8") as ready:
    ready.write("held\n")
while not os.path.exists(release_path):
    if os.getppid() != parent:
        break
    time.sleep(0.1)
sys.exit(0)
PY
  DRAIN_LOCK_PY=$!
  tries=0
  while [ ! -f "$DRAIN_LOCK_READY" ]; do
    if ! kill -0 "$DRAIN_LOCK_PY" 2>/dev/null; then
      wait "$DRAIN_LOCK_PY" 2>/dev/null || true
      rm -f "$DRAIN_LOCK_READY" "$DRAIN_LOCK_RELEASE"
      echo "Failed to acquire drain flock." >&2
      exit 1
    fi
    tries=$((tries + 1))
    if [ "$tries" -ge 650 ]; then
      kill "$DRAIN_LOCK_PY" 2>/dev/null || true
      wait "$DRAIN_LOCK_PY" 2>/dev/null || true
      rm -f "$DRAIN_LOCK_READY" "$DRAIN_LOCK_RELEASE"
      echo "Timed out waiting for drain flock holder." >&2
      exit 1
    fi
    sleep 0.1
  done
  rm -f "$DRAIN_LOCK_READY"
  drain_lock_held=1
}

release_drain_lock() {
  if [ "$drain_lock_held" -ne 1 ]; then
    return 0
  fi
  if [ -n "$DRAIN_LOCK_RELEASE" ]; then
    : >"$DRAIN_LOCK_RELEASE"
  fi
  if [ -n "$DRAIN_LOCK_PY" ]; then
    wait "$DRAIN_LOCK_PY" 2>/dev/null || true
  fi
  rm -f "$DRAIN_LOCK_READY" "$DRAIN_LOCK_RELEASE"
  DRAIN_LOCK_READY=
  DRAIN_LOCK_RELEASE=
  DRAIN_LOCK_PY=
  drain_lock_held=0
}

# Publish waiter pid atomically (temp + rename). Never leave an empty marker.
publish_active_marker() {
  d=$1
  tmp="$d/active.tmp.$$"
  printf '%s\n' "$$" >"$tmp"
  mv -f "$tmp" "$d/active"
}

# Reclaim only confirmed-dead waiters (re-read pid). Incomplete publishes are
# reclaimed only after STALE_PUBLISH_SECS so a concurrent writer is safe.
reclaim_stale_active() {
  d=$1
  [ -f "$d/active" ] || return 0
  apid=$(cat "$d/active" 2>/dev/null || true)
  case "$apid" in
    '' | *[!0-9]*)
      age=$(file_age_secs "$d/active")
      if [ "$age" -ge "$STALE_PUBLISH_SECS" ]; then
        echo "Clearing aged incomplete active marker in $d." >&2
        rm -f "$d/active"
      fi
      return 0
      ;;
  esac
  if pid_alive "$apid"; then
    return 0
  fi
  apid2=$(cat "$d/active" 2>/dev/null || true)
  if [ "$apid2" != "$apid" ]; then
    return 0
  fi
  if pid_alive "$apid2"; then
    return 0
  fi
  echo "Clearing stale active marker in $d (dead pid $apid)." >&2
  rm -f "$d/active"
}

sweep_stale_actives() {
  for d in "$OPS_DIR"/*; do
    [ -d "$d" ] || continue
    reclaim_stale_active "$d"
  done
}

# shellcheck disable=SC2329
on_exit() {
  if [ "$owns_active_cleanup" -eq 1 ] && [ -n "$op_dir" ] && [ -d "$op_dir" ]; then
    # Only clear our marker if it still names this process.
    if [ -f "$op_dir/active" ] && [ "$(cat "$op_dir/active" 2>/dev/null)" = "$$" ]; then
      rm -f "$op_dir/active"
    fi
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

agent_ids_for() {
  agent_ids_for_target "$1"
}

ensure_owned_table() {
  write_db "CREATE TABLE IF NOT EXISTS mo117_drain_owned (
    opid TEXT NOT NULL,
    agent_id INTEGER NOT NULL,
    PRIMARY KEY (opid, agent_id)
  );" >/dev/null
}

if [ "${1:-}" = "--resume" ]; then
  opid=${2:?usage: drain-agent.sh --resume <opid>}
  op_dir="$OPS_DIR/$opid"
  sweep_stale_actives
  acquire_drain_lock
  ensure_owned_table
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

# Claim agents that appeared after the initial drain (new ci-deploy lane, etc.)
# into an existing open op so they stay paused until --resume.
if [ "${1:-}" = "--extend-op" ]; then
  opid=${2:?usage: drain-agent.sh --extend-op <opid>}
  op_dir="$OPS_DIR/$opid"
  acquire_drain_lock
  ensure_owned_table
  owned_n=$(query_db "SELECT COUNT(*) FROM mo117_drain_owned WHERE opid = '$opid';" 2>/dev/null || echo 0)
  if [ "$owned_n" = "0" ] && [ ! -d "$op_dir" ]; then
    echo "Unknown drain op for extend: $opid" >&2
    exit 1
  fi
  mkdir -p "$op_dir"
  extend_ids=
  for t in ci-linux ci-deploy native; do
    if ! ids=$(agent_ids_for "$t"); then
      echo "Failed to look up agent ids for $t during extend." >&2
      exit 1
    fi
    extend_ids="$extend_ids $ids"
  done
  extend_ids=$(printf '%s' "$extend_ids" | tr ' ' '\n' | awk 'NF' | sort -u | tr '\n' ' ')
  if [ -z "$(printf '%s' "$extend_ids" | tr -d '[:space:]')" ]; then
    echo "No agents found to extend into op $opid." >&2
    exit 1
  fi
  in_list=$(printf '%s' "$extend_ids" | tr ' ' ',' | sed 's/,$//;s/^,//')
  txn_out=$(claim_pause_txn "$opid" "$in_list")
  owned=$(printf '%s\n' "$txn_out" | awk 'BEGIN{p=1} /^FLIPPED$/{p=0; next} p' | tr '\n' ' ' | sed 's/[[:space:]]*$//')
  flipped=$(printf '%s\n' "$txn_out" | awk 'BEGIN{p=0} /^FLIPPED$/{p=1; next} p' | tr '\n' ' ' | sed 's/[[:space:]]*$//')
  persist_ids_file "$op_dir/ids" "$owned"
  printf 'Extended op %s; newly flipped id(s): %s\n' "$opid" "${flipped:-none}"
  op_dir=
  exit 0
fi

agent_name=${1:?usage: drain-agent.sh [--hold-file PATH] <ci-linux|ci-deploy|native|all|--resume|--extend-op> [timeout_sec|opid]}
timeout_sec=${2:-1800}
opid="$(date +%Y%m%dT%H%M%S)-$$"
op_dir="$OPS_DIR/$opid"

sweep_stale_actives

if [ "$(srw_deploy_running)" != "0" ]; then
  echo "SRW deploy workflow is running; refusing to drain/restart." >&2
  exit 2
fi

targets=
optional_targets=
case "$agent_name" in
  ci-linux) targets="ci-linux" ;;
  ci-deploy) targets="ci-deploy" ;;
  native) targets="native" ;;
  all)
    targets="ci-linux ci-deploy native"
    # First two-lane rollout: ci-deploy may not exist until apply brings it up.
    optional_targets="ci-deploy"
    ;;
  *)
    echo "unknown agent: $agent_name" >&2
    exit 1
    ;;
esac

pause_ids=
present_targets=
for t in $targets; do
  if ! ids=$(agent_ids_for "$t"); then
    echo "Failed to look up agent ids for $t." >&2
    exit 1
  fi
  if [ -z "$(printf '%s' "$ids" | tr -d '[:space:]')" ]; then
    case " $optional_targets " in
      *" $t "*)
        printf 'Target %s not present; skipping (optional for this drain).\n' "$t"
        continue
        ;;
    esac
    echo "No agents matched target $t; refusing to drain." >&2
    exit 1
  fi
  present_targets="$present_targets $t"
  pause_ids="$pause_ids $ids"
done
present_targets=$(printf '%s' "$present_targets" | sed 's/^ *//')
pause_ids=$(printf '%s' "$pause_ids" | tr ' ' '\n' | awk 'NF' | sort -u | tr '\n' ' ')
if [ -z "$(printf '%s' "$pause_ids" | tr -d '[:space:]')" ]; then
  echo "No agents to drain after optional skips." >&2
  exit 1
fi

mkdir -p "$op_dir"
publish_active_marker "$op_dir"
owns_active_cleanup=1

in_list=$(printf '%s' "$pause_ids" | tr ' ' ',' | sed 's/,$//;s/^,//')
acquire_drain_lock

txn_out=$(claim_pause_txn "$opid" "$in_list")
# Parse ids before FLIPPED marker and flipped list after.
owned=$(printf '%s\n' "$txn_out" | awk 'BEGIN{p=1} /^FLIPPED$/{p=0; next} p' | tr '\n' ' ' | sed 's/[[:space:]]*$//')
flipped=$(printf '%s\n' "$txn_out" | awk 'BEGIN{p=0} /^FLIPPED$/{p=1; next} p' | tr '\n' ' ' | sed 's/[[:space:]]*$//')

persist_ids_file "$op_dir/ids" "$owned"
# Durable at claim time (before idle wait) so a killed drain still leaves a
# resume handle for watchdog / operators.
if [ -n "$HOLD_FILE" ]; then
  printf '%s\n' "$opid" >"$HOLD_FILE"
fi

if [ -n "$(printf '%s' "$flipped" | tr -d '[:space:]')" ]; then
  printf 'Set no_schedule=1 on drain-created pause id(s): %s\n' "$flipped"
else
  printf 'No new pauses created (targets already paused); op claims only drain-owned refs.\n'
fi
release_drain_lock

printf 'DRAIN_OPID=%s\n' "$opid"
if [ -n "$HOLD_FILE" ]; then
  printf 'Wrote hold file %s at pause claim\n' "$HOLD_FILE"
fi
printf 'Draining %s (timeout %ss, op %s)...\n' "$agent_name" "$timeout_sec" "$opid"

idle_log=$(mktemp "${TMPDIR:-/tmp}/mo117-drain-idle.XXXXXX")
idle_rc=0
wait_agents_idle "$agent_name" "$timeout_sec" >"$idle_log" 2>&1 || idle_rc=$?
while IFS= read -r line; do
  printf '  %s\n' "$line"
done <"$idle_log"
rm -f "$idle_log"
if [ "$idle_rc" -eq 2 ]; then
  echo "SRW deploy started during drain; aborting (ownership retained, active cleared on exit)." >&2
  exit 2
fi
if [ "$idle_rc" -ne 0 ]; then
  echo "Drain timed out after ${timeout_sec}s (ownership retained for --resume $opid; active cleared on exit)." >&2
  exit 1
fi
if [ -f "$op_dir/active" ] && [ "$(cat "$op_dir/active" 2>/dev/null)" = "$$" ]; then
  rm -f "$op_dir/active"
fi
owns_active_cleanup=0
printf 'Drain complete for %s (op %s held until --resume %s).\n' \
  "$agent_name" "$opid" "$opid"
exit 0
