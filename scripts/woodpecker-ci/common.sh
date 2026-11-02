#!/bin/sh
# Shared helpers for the M1 woodpecker-ci stack.
#
# Live layout on the M1 (~/Code/woodpecker-ci):
#   compose.yaml, *.plist          at repo root
#   scripts/{common,drain,...}.sh  here (this file's directory)
#
# mac-ops mirrors the same files flat under scripts/woodpecker-ci/.
# Install onto the M1 with: scripts/woodpecker-ci/install-to-m1.sh
set -eu

PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
export PATH

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
COMPOSE=/opt/homebrew/lib/docker/cli-plugins/docker-compose
DOCKER=/opt/homebrew/bin/docker
export COLIMA=/opt/homebrew/bin/colima
export TAILSCALE=/Applications/Tailscale.app/Contents/MacOS/Tailscale
CONTEXT=colima-woodpecker

compose() {
  "$COMPOSE" --context "$CONTEXT" --project-directory "$ROOT" "$@"
}

docker() {
  "$DOCKER" --context "$CONTEXT" "$@"
}

# Read-only SQL against the live Woodpecker SQLite volume.
query_db() {
  sql=$1
  docker run --rm -v woodpecker-ci-server-data:/d:ro alpine:3.22 \
    sh -c "apk add -q sqlite >/dev/null && sqlite3 -readonly file:/d/woodpecker.sqlite?mode=ro \"$sql\""
}

# Writable SQL (brief helper container). Prints sqlite stdout (e.g. RETURNING).
write_db() {
  sql=$1
  helper="woodpecker-dbwrite-$$"
  docker create --name "$helper" -v woodpecker-ci-server-data:/data \
    alpine:3.22 sleep 120 >/dev/null
  docker start "$helper" >/dev/null
  docker exec "$helper" sh -c 'apk add -q sqlite >/dev/null'
  docker exec "$helper" sqlite3 /data/woodpecker.sqlite "$sql"
  docker rm -f "$helper" >/dev/null 2>&1 || true
}

srw_deploy_running() {
  query_db "SELECT COUNT(*) FROM workflows w
    JOIN pipelines p ON p.id = w.pipeline_id
    JOIN repos r ON r.id = p.repo_id
    WHERE w.state = 'running'
      AND w.name = 'deploy'
      AND r.full_name LIKE '%strategy-replay-workbench%';"
}

# Match Docker check agents even when the DB still shows the seeded hash name.
docker_check_agent_ids() {
  query_db "SELECT id FROM agents
    WHERE backend = 'docker'
      AND name != 'ci-deploy'
      AND IFNULL(custom_labels, '') NOT LIKE '%role\":\"deploy%';"
}

docker_deploy_agent_ids() {
  query_db "SELECT id FROM agents
    WHERE name = 'ci-deploy'
       OR IFNULL(custom_labels, '') LIKE '%role\":\"deploy%';"
}

native_agent_ids() {
  query_db "SELECT id FROM agents WHERE backend = 'local';"
}
