#!/bin/sh
# Hot nightly SQLite backup of Woodpecker to the M4 over Tailscale.
# Does not stop agents (unlike backup.sh). Uses sqlite3 .backup.
# Colima has no host mounts, so the DB copy leaves the VM via docker cp.
set -eu

# shellcheck disable=SC1091
. "$(dirname -- "$0")/common.sh"

LOG_DIR="$HOME/Library/Logs/woodpecker"
LOG="$LOG_DIR/backup-nightly.log"
mkdir -p "$LOG_DIR"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"
}

REMOTE_HOST=${WOODPECKER_BACKUP_HOST:-shyams-m4}
REMOTE_DIR=${WOODPECKER_BACKUP_DIR:-/Users/shyamsivakumar/Backups/woodpecker-ci}
KEEP_DAYS=${WOODPECKER_BACKUP_KEEP_DAYS:-14}
stamp=$(date -u +%Y%m%dT%H%M%SZ)
local_dir="$ROOT/backups/nightly-$stamp"
helper="woodpecker-nightly-$stamp"

cleanup() {
  docker rm -f "$helper" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

mkdir -p "$local_dir"
chmod 700 "$local_dir"

docker create --name "$helper" \
  -v woodpecker-ci-server-data:/data:ro \
  alpine:3.22 sleep 3600 >/dev/null
docker start "$helper" >/dev/null
docker exec "$helper" sh -c 'apk add -q sqlite >/dev/null'
docker exec "$helper" sqlite3 /data/woodpecker.sqlite \
  ".backup '/tmp/woodpecker.sqlite'"
# Sanity query inside the helper (no host mount required).
count=$(docker exec "$helper" sqlite3 /tmp/woodpecker.sqlite \
  "SELECT COUNT(*) FROM pipelines;")
[ "$count" -gt 0 ] || {
  echo "backup sanity failed: pipelines count=$count" >&2
  exit 1
}
docker cp "$helper:/tmp/woodpecker.sqlite" "$local_dir/woodpecker.sqlite"
chmod -R go-rwx "$local_dir"

ssh -o BatchMode=yes -o ConnectTimeout=20 "$REMOTE_HOST" \
  "mkdir -p '$REMOTE_DIR' && chmod 700 '$REMOTE_DIR'"
scp -o BatchMode=yes -o ConnectTimeout=20 -q -r "$local_dir" \
  "$REMOTE_HOST:$REMOTE_DIR/"

ssh -o BatchMode=yes "$REMOTE_HOST" \
  "find '$REMOTE_DIR' -maxdepth 1 -type d -name 'nightly-*' -mtime +$KEEP_DAYS -exec rm -rf {} +"
find "$ROOT/backups" -maxdepth 1 -type d -name 'nightly-*' -mtime +"$KEEP_DAYS" -exec rm -rf {} +

log "nightly backup ok: $REMOTE_HOST:$REMOTE_DIR/nightly-$stamp pipelines=$count"
