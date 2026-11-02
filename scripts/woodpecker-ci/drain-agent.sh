#!/bin/sh
# Wait until a Docker agent has no running workflows, and refuse if an SRW
# deploy workflow is running on any agent. Woodpecker cancels in-flight
# workflows on agent shutdown, so drain before restart/resize.
set -eu

# shellcheck source=common.sh
. "$(dirname -- "$0")/common.sh"

agent_name=${1:?usage: drain-agent.sh <ci-linux|ci-deploy|all> [timeout_sec]}
timeout_sec=${2:-1800}
started=$(date +%s)

query_db() {
  sql=$1
  docker run --rm -v woodpecker-ci-server-data:/d:ro alpine:3.22 \
    sh -c "apk add -q sqlite >/dev/null && sqlite3 -readonly file:/d/woodpecker.sqlite?mode=ro \"$sql\""
}

srw_deploy_running() {
  query_db "SELECT COUNT(*) FROM workflows w
    JOIN pipelines p ON p.id = w.pipeline_id
    JOIN repos r ON r.id = p.repo_id
    WHERE w.state = 'running'
      AND w.name = 'deploy'
      AND r.full_name LIKE '%strategy-replay-workbench%';"
}

agent_running_count() {
  name=$1
  query_db "SELECT COUNT(*) FROM workflows w
    JOIN agents a ON a.id = w.agent_id
    WHERE w.state = 'running' AND a.name = '$name';"
}

wp_containers() {
  docker ps --filter name=wp_ -q | wc -l | tr -d ' '
}

if [ "$(srw_deploy_running)" != "0" ]; then
  echo "SRW deploy workflow is running; refusing to drain/restart." >&2
  exit 2
fi

names=
case "$agent_name" in
  ci-linux) names="ci-linux" ;;
  ci-deploy) names="ci-deploy" ;;
  all) names="ci-linux ci-deploy" ;;
  *)
    echo "unknown agent: $agent_name" >&2
    exit 1
    ;;
esac

printf 'Draining %s (timeout %ss)...\n' "$agent_name" "$timeout_sec"

while true; do
  if [ "$(srw_deploy_running)" != "0" ]; then
    echo "SRW deploy started during drain; aborting." >&2
    exit 2
  fi
  busy=0
  for n in $names; do
    c=$(agent_running_count "$n")
    if [ "$c" != "0" ]; then
      busy=1
      printf '  %s still has %s running workflow(s)\n' "$n" "$c"
    fi
  done
  # Also wait for wp_* job containers when draining linux agents.
  if [ "$agent_name" != "ci-deploy" ] || [ "$agent_name" = "all" ]; then
    :
  fi
  if [ "$busy" -eq 0 ]; then
    # For all/ci-linux, wait until no wp_* containers either (docker jobs).
    if [ "$agent_name" = "ci-deploy" ]; then
      printf 'Drain complete for %s.\n' "$agent_name"
      exit 0
    fi
    if [ "$(wp_containers)" = "0" ]; then
      printf 'Drain complete for %s (no wp_* containers).\n' "$agent_name"
      exit 0
    fi
    printf '  waiting for %s wp_* container(s)\n' "$(wp_containers)"
  fi
  if [ $(($(date +%s) - started)) -ge "$timeout_sec" ]; then
    echo "Drain timed out after ${timeout_sec}s." >&2
    exit 1
  fi
  sleep 5
done
