#!/bin/sh
# Fail zombie pipelines that are still "running" with no log for 10 minutes
# AND no executor evidence (MO-116 rule). Silence alone is not enough — a
# healthy quiet build must keep running. Covers upstream #7063 stale-drop.
#
# Mutates only inside BEGIN IMMEDIATE, gated on a reap_ok set that requires
# still-running + no recent logs + no tasks row. Workflow/step updates run
# only for pipeline ids in that set.
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
  if [ "$docker_n" = "0" ] && [ "$local_n" = "0" ]; then
    if [ "$(wp_count)" != "0" ] || [ "$(native_busy)" != "0" ]; then
      return 1
    fi
  fi
  return 0
}

# Same executor evidence, scoped to one workflow row (orphans under terminal
# pipelines must not be failed while their own executor is still live).
workflow_lost_executor() {
  wid=$1
  task_n=$(sql "SELECT COUNT(*) FROM tasks t
    JOIN workflows w ON w.pipeline_id = t.pipeline_id
    WHERE w.id = $wid;")
  if [ "$task_n" != "0" ]; then
    return 1
  fi
  backend=$(sql "SELECT IFNULL(a.backend, '') FROM workflows w
    LEFT JOIN agents a ON a.id = w.agent_id
    WHERE w.id = $wid;")
  case "$backend" in
    local)
      if [ "$(native_busy)" != "0" ]; then return 1; fi
      ;;
    docker | '')
      if [ "$(wp_count)" != "0" ]; then return 1; fi
      ;;
  esac
  return 0
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
  AND (w.started IS NULL OR w.started = 0 OR w.started < $cutoff)
  AND NOT EXISTS (
    SELECT 1 FROM steps s
    JOIN log_entries le ON le.step_id = s.id
    WHERE s.pipeline_id = w.pipeline_id
      AND (s.pid = w.pid OR s.ppid = w.pid)
      AND le.created >= $cutoff
  );
")

echo "$candidates" | while IFS='|' read -r pid repo_id number started; do
  [ -n "$pid" ] || continue
  if ! pipeline_lost_executor "$pid"; then
    log "reaper: skip pipeline id=$pid number=$number (executor present or task queued)"
    continue
  fi
  msg="reaped by MO-117 reaper: no log for ${STALE_SECS}s and no executor (started=$started)"
  # IMMEDIATE locks out writers (including a newly queued task) while we
  # revalidate and mutate. Workflow/step updates only touch reap_ok ids.
  reaped=$(sql "
BEGIN IMMEDIATE;
CREATE TEMP TABLE IF NOT EXISTS reap_ok (id INTEGER PRIMARY KEY);
DELETE FROM reap_ok;
INSERT INTO reap_ok (id)
SELECT p.id FROM pipelines p
WHERE p.id = $pid
  AND p.status = 'running'
  AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.pipeline_id = p.id)
  AND NOT EXISTS (
    SELECT 1 FROM steps s
    JOIN log_entries le ON le.step_id = s.id
    WHERE s.pipeline_id = p.id AND le.created >= $cutoff
  );
UPDATE pipelines
  SET status = 'failure', finished = $now, updated = $now,
      errors = CASE
        WHEN errors IS NULL OR errors = '' OR errors = 'null'
          THEN json_array(json_object('message', '$msg'))
        ELSE errors END
  WHERE id IN (SELECT id FROM reap_ok);
UPDATE workflows
  SET state = 'failure', finished = $now, error = '$msg'
  WHERE pipeline_id IN (SELECT id FROM reap_ok)
    AND state IN ('running', 'pending');
UPDATE steps
  SET state = 'failure', finished = $now, error = '$msg', exit_code = 1
  WHERE pipeline_id IN (SELECT id FROM reap_ok)
    AND state IN ('running', 'pending');
SELECT COUNT(*) FROM reap_ok;
COMMIT;
")
  case "$reaped" in
    '' | 0)
      log "reaper: skip pipeline id=$pid number=$number (atomic revalidation failed)"
      ;;
    *)
      log "reaper: failed pipeline id=$pid repo_id=$repo_id number=$number"
      ;;
  esac
done

echo "$orphan_workflows" | while IFS='|' read -r wid pid started; do
  [ -n "$wid" ] || continue
  if ! workflow_lost_executor "$wid"; then
    log "reaper: skip orphan workflow id=$wid (executor present or task queued)"
    continue
  fi
  msg="reaped by MO-117 reaper: orphan workflow under terminal pipeline (started=$started)"
  reaped=$(sql "
BEGIN IMMEDIATE;
CREATE TEMP TABLE IF NOT EXISTS orphan_ok (id INTEGER PRIMARY KEY);
DELETE FROM orphan_ok;
INSERT INTO orphan_ok (id)
SELECT w.id FROM workflows w
JOIN pipelines p ON p.id = w.pipeline_id
WHERE w.id = $wid
  AND w.state IN ('running', 'pending')
  AND p.status IN ('killed', 'failure', 'success', 'error', 'declined')
  AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.pipeline_id = w.pipeline_id)
  AND NOT EXISTS (
    SELECT 1 FROM steps s
    JOIN log_entries le ON le.step_id = s.id
    WHERE s.pipeline_id = w.pipeline_id
      AND (s.pid = w.pid OR s.ppid = w.pid)
      AND le.created >= $cutoff
  );
UPDATE workflows
  SET state = 'failure', finished = $now, error = '$msg'
  WHERE id IN (SELECT id FROM orphan_ok);
UPDATE steps
  SET state = 'failure', finished = $now, error = '$msg', exit_code = 1
  WHERE state IN ('running', 'pending')
    AND pipeline_id = $pid
    AND EXISTS (
      SELECT 1 FROM workflows w
      WHERE w.id IN (SELECT id FROM orphan_ok)
        AND (steps.pid = w.pid OR steps.ppid = w.pid)
    );
SELECT COUNT(*) FROM orphan_ok;
COMMIT;
")
  case "$reaped" in
    '' | 0)
      log "reaper: skip orphan workflow id=$wid (atomic revalidation failed)"
      ;;
    *)
      log "reaper: failed orphan workflow id=$wid pipeline_id=$pid"
      ;;
  esac
done

if [ -z "$candidates" ] && [ -z "$orphan_workflows" ]; then
  log "reaper: no stale running pipelines"
fi
