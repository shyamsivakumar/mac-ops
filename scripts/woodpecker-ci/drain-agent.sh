#!/bin/sh
# Pause scheduling, wait until the named agent(s) are idle, refuse if an SRW
# deploy is running. Woodpecker cancels in-flight workflows on agent shutdown.
#
# Usage: drain-agent.sh <ci-linux|ci-deploy|native|all> [timeout_sec]
# Leaves no_schedule=1 on drained Docker/native agents. Caller must clear it
# (drain-agent.sh --resume) after the restart window, or apply-two-lanes does.
set -eu

# shellcheck source=common.sh disable=SC1091
. "$(dirname -- "$0")/common.sh"

if [ "${1:-}" = "--resume" ]; then
  write_db "UPDATE agents SET no_schedule = 0 WHERE no_schedule != 0;"
  printf 'Scheduling resumed on all agents.\n'
  exit 0
fi

agent_name=${1:?usage: drain-agent.sh <ci-linux|ci-deploy|native|all|--resume> [timeout_sec]}
timeout_sec=${2:-1800}
started=$(date +%s)

wp_containers() {
  docker ps --filter name=wp_ -q | wc -l | tr -d ' '
}

agent_ids_for() {
  case "$1" in
    ci-linux) docker_check_agent_ids ;;
    ci-deploy) docker_deploy_agent_ids ;;
    native) native_agent_ids ;;
    *) return 1 ;;
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
  # Local backend: any child of the LaunchAgent process means a job is live.
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

# Disable scheduling before waiting so nothing new (esp. SRW deploy) starts.
pause_ids=
for t in $targets; do
  ids=$(agent_ids_for "$t" || true)
  [ -n "$ids" ] || continue
  pause_ids="$pause_ids $ids"
done
pause_ids=$(printf '%s' "$pause_ids" | tr ' ' '\n' | awk 'NF' | sort -u | tr '\n' ' ')
if [ -n "$(printf '%s' "$pause_ids" | tr -d '[:space:]')" ]; then
  in_list=$(printf '%s' "$pause_ids" | tr ' ' ',' | sed 's/,$//;s/^,//')
  write_db "UPDATE agents SET no_schedule = 1 WHERE id IN ($in_list);"
  printf 'Set no_schedule=1 on agent id(s): %s\n' "$pause_ids"
fi

printf 'Draining %s (timeout %ss)...\n' "$agent_name" "$timeout_sec"

while true; do
  if [ "$(srw_deploy_running)" != "0" ]; then
    echo "SRW deploy started during drain; aborting (no_schedule left set)." >&2
    exit 2
  fi
  busy=0
  for t in $targets; do
    if [ "$t" = "native" ]; then
      if [ "$(native_agent_busy)" != "0" ]; then
        busy=1
        printf '  native agent still has child processes\n'
      fi
      ids=$(agent_ids_for native || true)
      if [ -n "$ids" ] && [ "$(running_on_ids "$ids")" != "0" ]; then
        busy=1
        printf '  native agent still has DB running workflow(s)\n'
      fi
      continue
    fi
    ids=$(agent_ids_for "$t" || true)
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
      printf 'Drain complete for %s (no_schedule still 1 until --resume).\n' \
        "$agent_name"
      exit 0
    fi
  fi
  if [ $(($(date +%s) - started)) -ge "$timeout_sec" ]; then
    echo "Drain timed out after ${timeout_sec}s (no_schedule left set)." >&2
    exit 1
  fi
  sleep 5
done
