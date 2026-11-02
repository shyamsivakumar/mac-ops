#!/bin/sh
# Fail zombie pipelines that are still "running" with no log for 10 minutes
# AND no executor evidence (MO-116 rule). Silence alone is not enough — a
# healthy quiet build must keep running. Covers upstream #7063 stale-drop.
set -eu

# shellcheck source=common.sh disable=SC1091
. "$(dirname -- "$0")/common.sh"

LOG_DIR="$HOME/Library/Logs/woodpecker"
LOG="$LOG_DIR/reaper.log"
mkdir -p "$LOG_DIR"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"
}

STALE_SECS=${WOODPECKER_REAPER_STALE_SECS:-600}
now=$(date +%s)
cutoff=$((now - STALE_SECS))

helper="woodpecker-reaper-$$"
cleanup() {
  docker rm -f "$helper" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker create --name "$helper" \
  -v woodpecker-ci-server-data:/data \
  alpine:3.22 sleep 3600 >/dev/null
docker start "$helper" >/dev/null
docker exec "$helper" sh -c 'apk add -q sqlite >/dev/null'

sql() {
  docker exec "$helper" sqlite3 /data/woodpecker.sqlite "$1"
}

wp_count() {
  docker ps --filter name=wp_ -q | wc -l | tr -d ' '
}

native_busy() {
  pid=$(launchctl list 2>/dev/null | awk '$3=="org.woodpecker.agent"{print $1; exit}')
  case "$pid" in
    '' | -)
      echo 0
      return
      ;;
  esac
  if pgrep -P "$pid" >/dev/null 2>&1; then echo 1; else echo 0; fi
}

# True when the pipeline has lost its executor: no queue task row, and no
# live Docker job containers / native agent children for its backends.
pipeline_lost_executor() {
  pid=$1
  task_n=$(sql "SELECT COUNT(*) FROM tasks WHERE pipeline_id = $pid;")
  if [ "$task_n" != "0" ]; then
    return 1
  fi
  docker_n=$(sql "SELECT COUNT(*) FROM workflows w
    LEFT JOIN agents a ON a.id = w.agent_id
    WHERE w.pipeline_id = $pid AND w.state IN ('running','pending')
      AND (a.backend = 'docker' OR a.backend IS NULL OR w.agent_id = 0 OR w.agent_id IS NULL);")
  local_n=$(sql "SELECT COUNT(*) FROM workflows w
    JOIN agents a ON a.id = w.agent_id
    WHERE w.pipeline_id = $pid AND w.state IN ('running','pending')
      AND a.backend = 'local';")
  if [ "$docker_n" != "0" ] && [ "$(wp_count)" != "0" ]; then
    return 1
  fi
  if [ "$local_n" != "0" ] && [ "$(native_busy)" != "0" ]; then
    return 1
  fi
  # No assigned agent yet but still "running" with no task and no containers:
  # treat as lost only when there is also no native activity and no wp_*.
  if [ "$docker_n" = "0" ] && [ "$local_n" = "0" ]; then
    if [ "$(wp_count)" != "0" ] || [ "$(native_busy)" != "0" ]; then
      return 1
    fi
  fi
  return 0
}

still_quiet_running() {
  pid=$1
  n=$(sql "SELECT COUNT(*) FROM pipelines p
    WHERE p.id = $pid AND p.status = 'running'
      AND NOT EXISTS (
        SELECT 1 FROM steps s
        JOIN log_entries le ON le.step_id = s.id
        WHERE s.pipeline_id = p.id AND le.created >= $cutoff
      );")
  [ "$n" = "1" ]
}

candidates=$(sql "
SELECT p.id || '|' || p.repo_id || '|' || p.number || '|' || IFNULL(p.started,0)
FROM pipelines p
WHERE p.status = 'running'
  AND p.started > 0
  AND p.started < $cutoff
  AND NOT EXISTS (
    SELECT 1 FROM steps s
    JOIN log_entries le ON le.step_id = s.id
    WHERE s.pipeline_id = p.id AND le.created >= $cutoff
  );
")

orphan_workflows=$(sql "
SELECT w.id || '|' || w.pipeline_id || '|' || IFNULL(w.started,0)
FROM workflows w
JOIN pipelines p ON p.id = w.pipeline_id
WHERE w.state IN ('running', 'pending')
  AND p.status IN ('killed', 'failure', 'success', 'error', 'declined')
  AND (w.started IS NULL OR w.started = 0 OR w.started < $cutoff);
")

echo "$candidates" | while IFS='|' read -r pid repo_id number started; do
  [ -n "$pid" ] || continue
  if ! pipeline_lost_executor "$pid"; then
    log "reaper: skip pipeline id=$pid number=$number (executor present or task queued)"
    continue
  fi
  if ! still_quiet_running "$pid"; then
    log "reaper: skip pipeline id=$pid number=$number (changed before mutate)"
    continue
  fi
  # Re-check executor immediately before UPDATE.
  if ! pipeline_lost_executor "$pid"; then
    log "reaper: skip pipeline id=$pid number=$number (executor returned)"
    continue
  fi
  msg="reaped by MO-117 reaper: no log for ${STALE_SECS}s and no executor (started=$started)"
  sql "
BEGIN;
UPDATE pipelines
  SET status = 'failure', finished = $now, updated = $now,
      errors = CASE
        WHEN errors IS NULL OR errors = '' OR errors = 'null'
          THEN json_array(json_object('message', '$msg'))
        ELSE errors END
  WHERE id = $pid AND status = 'running'
    AND NOT EXISTS (
      SELECT 1 FROM steps s
      JOIN log_entries le ON le.step_id = s.id
      WHERE s.pipeline_id = $pid AND le.created >= $cutoff
    );
UPDATE workflows
  SET state = 'failure', finished = $now, error = '$msg'
  WHERE pipeline_id = $pid AND state IN ('running', 'pending');
UPDATE steps
  SET state = 'failure', finished = $now, error = '$msg', exit_code = 1
  WHERE pipeline_id = $pid AND state IN ('running', 'pending');
COMMIT;
"
  log "reaper: failed pipeline id=$pid repo_id=$repo_id number=$number"
done

echo "$orphan_workflows" | while IFS='|' read -r wid pid started; do
  [ -n "$wid" ] || continue
  msg="reaped by MO-117 reaper: orphan workflow under terminal pipeline (started=$started)"
  sql "
BEGIN;
UPDATE workflows
  SET state = 'failure', finished = $now, error = '$msg'
  WHERE id = $wid AND state IN ('running', 'pending');
UPDATE steps
  SET state = 'failure', finished = $now, error = '$msg', exit_code = 1
  WHERE pipeline_id = $pid AND state IN ('running', 'pending');
COMMIT;
"
  log "reaper: failed orphan workflow id=$wid pipeline_id=$pid"
done

if [ -z "$candidates" ] && [ -z "$orphan_workflows" ]; then
  log "reaper: no stale running pipelines"
fi
