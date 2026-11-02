#!/bin/sh
# Mark as failed any pipeline still "running" with no log line for 10 minutes.
# Covers Woodpecker stale-drop zombies (upstream #7063), e.g. pipeline 891.
set -eu

# shellcheck source=/dev/null
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

# Online backup-style write against the live volume. Woodpecker keeps the DB
# open; SQLite's UPDATE is safe enough for this ops script on a quiet box.
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

# Find zombie pipelines: status=running, and either no steps with logs, or
# the newest log_entries.created / steps.started is older than the cutoff.
# A pipeline with no log lines at all and started before cutoff is stale.
zombies=$(docker exec "$helper" sqlite3 /data/woodpecker.sqlite "
SELECT p.id || '|' || p.repo_id || '|' || p.number || '|' || IFNULL(p.started,0)
FROM pipelines p
WHERE p.status = 'running'
  AND p.started > 0
  AND p.started < $cutoff
  AND NOT EXISTS (
    SELECT 1
    FROM steps s
    JOIN log_entries le ON le.step_id = s.id
    WHERE s.pipeline_id = p.id
      AND le.created >= $cutoff
  )
  AND NOT EXISTS (
    SELECT 1
    FROM steps s
    WHERE s.pipeline_id = p.id
      AND s.state = 'running'
      AND s.started >= $cutoff
  );
")

# Also reap workflows still running/pending under a terminal pipeline
# (killed/failure/success) with no recent log activity.
orphan_workflows=$(docker exec "$helper" sqlite3 /data/woodpecker.sqlite "
SELECT w.id || '|' || w.pipeline_id || '|' || IFNULL(w.started,0)
FROM workflows w
JOIN pipelines p ON p.id = w.pipeline_id
WHERE w.state IN ('running', 'pending')
  AND p.status IN ('killed', 'failure', 'success', 'error', 'declined')
  AND (w.started IS NULL OR w.started = 0 OR w.started < $cutoff)
  AND NOT EXISTS (
    SELECT 1
    FROM steps s
    JOIN log_entries le ON le.step_id = s.id
    WHERE s.pipeline_id = w.pipeline_id
      AND le.created >= $cutoff
  );
")

if [ -z "$zombies" ] && [ -z "$orphan_workflows" ]; then
  log "reaper: no stale running pipelines"
  exit 0
fi

echo "$zombies" | while IFS='|' read -r pid repo_id number started; do
  [ -n "$pid" ] || continue
  msg="reaped by MO-117 reaper: no log activity for ${STALE_SECS}s (started=$started)"
  docker exec "$helper" sqlite3 /data/woodpecker.sqlite "
BEGIN;
UPDATE pipelines
  SET status = 'failure',
      finished = $now,
      updated = $now,
      errors = CASE
        WHEN errors IS NULL OR errors = '' OR errors = 'null' THEN json_array(json_object('message', '$msg'))
        ELSE errors
      END
  WHERE id = $pid AND status = 'running';
UPDATE workflows
  SET state = 'failure',
      finished = $now,
      error = '$msg'
  WHERE pipeline_id = $pid AND state IN ('running', 'pending');
UPDATE steps
  SET state = 'failure',
      finished = $now,
      error = '$msg',
      exit_code = 1
  WHERE pipeline_id = $pid AND state IN ('running', 'pending');
COMMIT;
"
  log "reaper: failed pipeline id=$pid repo_id=$repo_id number=$number"
done

echo "$orphan_workflows" | while IFS='|' read -r wid pid started; do
  [ -n "$wid" ] || continue
  msg="reaped by MO-117 reaper: orphan workflow under terminal pipeline (started=$started)"
  docker exec "$helper" sqlite3 /data/woodpecker.sqlite "
BEGIN;
UPDATE workflows
  SET state = 'failure',
      finished = $now,
      error = '$msg'
  WHERE id = $wid AND state IN ('running', 'pending');
UPDATE steps
  SET state = 'failure',
      finished = $now,
      error = '$msg',
      exit_code = 1
  WHERE pipeline_id = $pid AND state IN ('running', 'pending');
COMMIT;
"
  log "reaper: failed orphan workflow id=$wid pipeline_id=$pid"
done
