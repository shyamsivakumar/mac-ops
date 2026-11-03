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
# Retries briefly on SQLITE_BUSY (server writes during pipelines).
# Result rows go to stdout; diagnostics stay on stderr.
query_db() {
  sql=$1
  i=0
  stdout=$(mktemp "${TMPDIR:-/tmp}/wp-sql-out.XXXXXX")
  stderr=$(mktemp "${TMPDIR:-/tmp}/wp-sql-err.XXXXXX")
  while :; do
    : >"$stdout"
    : >"$stderr"
    set +e
    docker run --rm -v woodpecker-ci-server-data:/d:ro alpine:3.22 \
      sh -c "apk add -q sqlite >/dev/null && sqlite3 -readonly \"file:/d/woodpecker.sqlite?mode=ro&immutable=0\" \"$sql\"" \
      >"$stdout" 2>"$stderr"
    rc=$?
    set -e
    if [ "$rc" -eq 0 ]; then
      cat "$stdout"
      # Surface non-fatal docker/sqlite chatter without polluting the result.
      if [ -s "$stderr" ]; then
        cat "$stderr" >&2
      fi
      rm -f "$stdout" "$stderr"
      return 0
    fi
    err=$(
      cat "$stderr"
      cat "$stdout"
    )
    case "$err" in
      *locked* | *BUSY*)
        i=$((i + 1))
        if [ "$i" -gt 30 ]; then
          printf '%s\n' "$err" >&2
          rm -f "$stdout" "$stderr"
          return 1
        fi
        sleep 1
        ;;
      *)
        printf '%s\n' "$err" >&2
        rm -f "$stdout" "$stderr"
        return 1
        ;;
    esac
  done
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

# Any non-terminal workflow — used by cache-cleanup to avoid deleting live mounts.
any_workflow_running() {
  query_db "SELECT COUNT(*) FROM workflows WHERE state = 'running';"
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

# How fresh agents.last_contact must be (seconds) before a drain may resume.
AGENT_READY_MAX_AGE=${AGENT_READY_MAX_AGE:-90}

agent_ids_for_target() {
  case "$1" in
    ci-linux) docker_check_agent_ids ;;
    ci-deploy) docker_deploy_agent_ids ;;
    native) native_agent_ids ;;
    all)
      {
        docker_check_agent_ids
        docker_deploy_agent_ids
        native_agent_ids
      } | awk 'NF' | sort -u
      ;;
    *)
      echo "unknown agent target: $1" >&2
      return 1
      ;;
  esac
}

native_agent_process_up() {
  pid=$(launchctl list 2>/dev/null | awk '$3=="org.woodpecker.agent"{print $1; exit}')
  case "$pid" in
    '' | -) return 1 ;;
  esac
  return 0
}

docker_service_up() {
  service=$1
  [ -n "$(compose ps --status running -q "$service" 2>/dev/null)" ]
}

# True when every agent id in the list has last_contact within max_age seconds.
agents_contact_fresh() {
  ids=$1
  max_age=${2:-$AGENT_READY_MAX_AGE}
  ids_clean=$(printf '%s' "$ids" | tr ' ' '\n' | awk 'NF' | sort -u)
  [ -n "$ids_clean" ] || return 1
  expected=$(printf '%s\n' "$ids_clean" | wc -l | tr -d ' ')
  in_list=$(printf '%s\n' "$ids_clean" | tr '\n' ',' | sed 's/,$//')
  fresh=$(query_db "SELECT COUNT(*) FROM agents
    WHERE id IN ($in_list)
      AND last_contact >= strftime('%s','now') - $max_age;") || return 1
  [ "$fresh" = "$expected" ]
}

# Process/container readiness for a drain target (ci-linux|ci-deploy|native|all).
target_process_ready() {
  target=$1
  case "$target" in
    ci-linux)
      docker_service_up agent-linux
      ;;
    ci-deploy)
      docker_service_up agent-deploy
      ;;
    native)
      native_agent_process_up
      ;;
    all)
      docker_service_up agent-linux \
        && docker_service_up agent-deploy \
        && native_agent_process_up
      ;;
    *)
      echo "unknown agent target: $target" >&2
      return 1
      ;;
  esac
}

wp_containers() {
  docker ps --filter name=wp_ -q | wc -l | tr -d ' '
}

running_workflows_on_ids() {
  ids=$1
  [ -n "$(printf '%s' "$ids" | tr -d '[:space:]')" ] || {
    echo 0
    return 0
  }
  in_list=$(printf '%s' "$ids" | tr ' \n' ',' | sed 's/,$//;s/^,//;s/,,*/,/g')
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

# Wait until drained agents have no running workflows (and no wp_* for linux).
# Used when reusing a held drain before Colima kickstart -k.
wait_agents_idle() {
  target=${1:?wait_agents_idle needs target}
  timeout_sec=${2:-900}
  started=$(date +%s)
  need_wp=0
  case "$target" in
    ci-linux | all) need_wp=1 ;;
  esac

  while :; do
    if [ "$(srw_deploy_running)" != "0" ]; then
      printf 'wait_agents_idle: SRW deploy running; refusing\n' >&2
      return 2
    fi
    busy=0
    case "$target" in
      all) targets='ci-linux ci-deploy native' ;;
      *) targets=$target ;;
    esac
    for t in $targets; do
      if ! ids=$(agent_ids_for_target "$t"); then
        return 1
      fi
      ids=$(printf '%s' "$ids" | tr '\n' ' ' | sed 's/[[:space:]]*$//')
      if [ -z "$(printf '%s' "$ids" | tr -d '[:space:]')" ]; then
        # Optional missing deploy agent is fine for "all".
        if [ "$t" = "ci-deploy" ] && [ "$target" = "all" ]; then
          continue
        fi
        printf 'wait_agents_idle: no agent ids for %s\n' "$t"
        busy=1
        continue
      fi
      if [ "$t" = "native" ]; then
        if [ "$(native_agent_busy)" != "0" ]; then
          busy=1
          printf 'wait_agents_idle: native still has child processes\n'
        fi
      fi
      c=$(running_workflows_on_ids "$ids")
      if [ "$c" != "0" ]; then
        busy=1
        printf 'wait_agents_idle: %s has %s running workflow(s)\n' "$t" "$c"
      fi
    done
    if [ "$busy" -eq 0 ]; then
      if [ "$need_wp" -eq 1 ] && [ "$(wp_containers)" != "0" ]; then
        printf 'wait_agents_idle: waiting for %s wp_* container(s)\n' "$(wp_containers)"
      else
        printf 'wait_agents_idle: %s idle\n' "$target"
        return 0
      fi
    fi
    if [ $(($(date +%s) - started)) -ge "$timeout_sec" ]; then
      printf 'wait_agents_idle: timed out after %ss for %s\n' \
        "$timeout_sec" "$target" >&2
      return 1
    fi
    sleep 5
  done
}

# Block until target agents are up and freshly contacting the server, or timeout.
# Prints progress lines to stdout. Returns 0 when ready.
wait_agents_ready() {
  target=${1:?wait_agents_ready needs target}
  timeout_sec=${2:-180}
  max_age=${3:-$AGENT_READY_MAX_AGE}
  started=$(date +%s)

  while :; do
    if ! ids=$(agent_ids_for_target "$target"); then
      return 1
    fi
    ids=$(printf '%s' "$ids" | tr '\n' ' ' | sed 's/[[:space:]]*$//')
    if [ -z "$(printf '%s' "$ids" | tr -d '[:space:]')" ]; then
      printf 'wait_agents_ready: no agent ids for %s yet\n' "$target"
    elif ! target_process_ready "$target"; then
      printf 'wait_agents_ready: process/container not ready for %s\n' "$target"
    elif agents_contact_fresh "$ids" "$max_age"; then
      printf 'wait_agents_ready: %s ready (ids %s, contact ≤%ss)\n' \
        "$target" "$ids" "$max_age"
      return 0
    else
      printf 'wait_agents_ready: %s up but last_contact stale (ids %s)\n' \
        "$target" "$ids"
    fi
    if [ $(($(date +%s) - started)) -ge "$timeout_sec" ]; then
      printf 'wait_agents_ready: timed out after %ss for %s\n' \
        "$timeout_sec" "$target" >&2
      return 1
    fi
    sleep 3
  done
}
