#!/bin/sh
# Drain → run a restart/recreate command → wait for agent readiness → resume.
#
# Use for any Colima stop/resize or Docker/native agent recreate so in-flight
# workflows are not killed with docker.sock "Canceled" / connect errors.
# Refuses while an SRW deploy is running (same guard as drain-agent.sh).
#
# Usage:
#   safe-restart.sh [--timeout SEC] [--ready-timeout SEC] \
#     [ci-linux|ci-deploy|native|all] -- <command...>
#   safe-restart.sh all -- compose up -d --force-recreate --no-deps agent-linux
#
# Prints DRAIN_OPID=... then runs the command. On command failure or readiness
# timeout the drain stays held (resume manually). On success resumes that opid
# only after wait_agents_ready confirms process + fresh last_contact.
set -eu

# shellcheck disable=SC1091
. "$(dirname -- "$0")/common.sh"

timeout_sec=1800
ready_timeout_sec=180
target=all

while [ "$#" -gt 0 ]; do
  case "$1" in
    --timeout)
      timeout_sec=${2:?--timeout needs a value}
      shift 2
      ;;
    --ready-timeout)
      ready_timeout_sec=${2:?--ready-timeout needs a value}
      shift 2
      ;;
    --)
      shift
      break
      ;;
    ci-linux | ci-deploy | native | all)
      target=$1
      shift
      ;;
    -h | --help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *)
      echo "usage: safe-restart.sh [--timeout SEC] [--ready-timeout SEC] [ci-linux|ci-deploy|native|all] -- <command...>" >&2
      exit 1
      ;;
  esac
done

if [ "$#" -eq 0 ]; then
  echo "safe-restart.sh: missing command after --" >&2
  exit 1
fi

drain="$ROOT/scripts/drain-agent.sh"
if [ ! -x "$drain" ]; then
  echo "Missing executable $drain" >&2
  exit 1
fi

drain_log=$(mktemp "${TMPDIR:-/tmp}/mo121-safe-restart-drain.XXXXXX")
drain_rc=0
"$drain" "$target" "$timeout_sec" >"$drain_log" 2>&1 || drain_rc=$?
cat "$drain_log"
opid=$(awk -F= '/^DRAIN_OPID=/{print $2; exit}' "$drain_log")
rm -f "$drain_log"

if [ "$drain_rc" -ne 0 ]; then
  echo "Drain failed (rc=$drain_rc); not running restart command." >&2
  if [ -n "$opid" ]; then
    echo "Drain op $opid may still be held; resume with: $drain --resume $opid" >&2
  fi
  exit "$drain_rc"
fi

if [ -z "$opid" ]; then
  echo "drain-agent.sh did not print DRAIN_OPID; refusing to restart." >&2
  exit 1
fi

printf 'Running restart command under drain op %s: %s\n' "$opid" "$*"
cmd_rc=0
"$@" || cmd_rc=$?
if [ "$cmd_rc" -ne 0 ]; then
  echo "Restart command failed (rc=$cmd_rc); leaving drain held ($opid)." >&2
  echo "Resume with: $drain --resume $opid" >&2
  exit "$cmd_rc"
fi

printf 'Waiting for %s agent readiness (timeout %ss) before resume...\n' \
  "$target" "$ready_timeout_sec"
if ! wait_agents_ready "$target" "$ready_timeout_sec"; then
  echo "Agents not ready after restart; leaving drain held ($opid)." >&2
  echo "Resume with: $drain --resume $opid" >&2
  exit 1
fi

"$drain" --resume "$opid"
printf 'Restart finished; drain %s resumed after readiness.\n' "$opid"
