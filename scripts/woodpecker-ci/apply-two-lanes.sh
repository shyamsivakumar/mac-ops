#!/bin/sh
# MO-117: resize Colima, swap in two Docker agents, install reaper + nightly backup.
# Refuses to run while an SRW deploy is active. Drains Docker (+native if
# needed) with owned no_schedule before stopping Colima. Verifies the live
# native capacity is 1 (plist + process env + agents.capacity); guarded reload
# only after drain when the running agent drifted.
set -eu

# shellcheck source-path=SCRIPTDIR source=common.sh disable=SC1091
. "$(dirname -- "$0")/common.sh"

DOMAIN="gui/$(id -u)"
COLIMA_MEM=${COLIMA_MEM:-10}
LINUX_CAP=${LINUX_CAP:-3}
PLIST="$HOME/Library/LaunchAgents/org.woodpecker.agent.plist"

printf 'MO-117 apply: Colima memory=%sGiB ci-linux capacity=%s\n' "$COLIMA_MEM" "$LINUX_CAP"

# Pause scheduling + wait for Docker (and native, if busy) to go idle.
# Capture DRAIN_OPID so --resume cannot clear a different op's pause.
drain_log=$(mktemp)
drain_rc=0
"$ROOT/scripts/drain-agent.sh" all 1800 >"$drain_log" || drain_rc=$?
cat "$drain_log"
DRAIN_OPID=$(sed -n 's/^DRAIN_OPID=//p' "$drain_log" | tail -1)
rm -f "$drain_log"
[ "$drain_rc" -eq 0 ] || exit "$drain_rc"
[ -n "$DRAIN_OPID" ] || {
  echo "drain-agent.sh did not print DRAIN_OPID." >&2
  exit 1
}

# Snapshot Colima config before resize.
if [ ! -f "$HOME/.colima/woodpecker/colima.yaml.before-mo117" ]; then
  cp "$HOME/.colima/woodpecker/colima.yaml" \
    "$HOME/.colima/woodpecker/colima.yaml.before-mo117"
fi

python3 - <<PY
from pathlib import Path
import re
p = Path.home() / ".colima/woodpecker/colima.yaml"
text = p.read_text()
new = re.sub(r"(?m)^memory:\s*\d+", f"memory: $COLIMA_MEM", text, count=1)
if new == text and f"memory: $COLIMA_MEM" not in text:
    raise SystemExit("failed to set memory in colima.yaml")
p.write_text(new)
print(p, "memory ->", $COLIMA_MEM)
PY

# Stop only Docker agents; Colima stop takes the VM with them.
compose stop agent agent-linux agent-deploy 2>/dev/null || true
"$COLIMA" stop woodpecker

launchctl kickstart -k "$DOMAIN/com.shyamsivakumar.colima-woodpecker"

deadline=$(($(date +%s) + 180))
until "$COLIMA" status woodpecker >/dev/null 2>&1 && docker ps -q >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "Colima did not become ready after resize." >&2
    exit 1
  fi
  sleep 3
done

if docker volume inspect woodpecker-ci-agent-config >/dev/null 2>&1; then
  docker volume create woodpecker-ci-agent-linux-config >/dev/null
  docker run --rm \
    -v woodpecker-ci-agent-config:/from:ro \
    -v woodpecker-ci-agent-linux-config:/to \
    alpine:3.22 sh -c 'cp -a /from/. /to/ && ls -la /to'
fi

# Bring server up first, then agents, so we can pause as they register.
compose up -d --remove-orphans server webhook-proxy
agents_up_at=$(date +%s)
compose up -d agent-linux agent-deploy

# agent.conf on each volume binds the running container to agents.id.
agent_id_from_volume() {
  vol=$1
  docker run --rm -v "$vol:/c:ro" alpine:3.22 \
    sh -c 'test -s /c/agent.conf && cat /c/agent.conf' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["agent_id"])'
}

# Fail closed: empty/non-integer DB results are not success.
db_count() {
  sql=$1
  out=
  if ! out=$(query_db "$sql"); then
    return 1
  fi
  case "$out" in
    '' | *[!0-9]*) return 1 ;;
  esac
  printf '%s\n' "$out"
}

# True when the agent_id from this volume is fresh, owned, and paused.
volume_agent_paused() {
  vol=$1
  aid=
  if ! aid=$(agent_id_from_volume "$vol"); then
    return 1
  fi
  case "$aid" in
    '' | *[!0-9]*) return 1 ;;
  esac
  n=$(db_count "SELECT COUNT(*) FROM agents a
    JOIN mo117_drain_owned o ON o.agent_id = a.id AND o.opid = '$DRAIN_OPID'
    WHERE a.id = $aid
      AND a.no_schedule = 1
      AND IFNULL(a.last_contact, 0) >= $agents_up_at;") || return 1
  [ "$n" -ge 1 ]
}

must_extend_op() {
  if ! "$ROOT/scripts/drain-agent.sh" --extend-op "$DRAIN_OPID"; then
    echo "drain-agent.sh --extend-op $DRAIN_OPID failed." >&2
    exit 1
  fi
}

# Soft extend during registration only (agent.conf / rows may not exist yet).
extend_loop_stop="$HOME/Library/Logs/woodpecker/mo117-extend-stop-$$"
mkdir -p "$HOME/Library/Logs/woodpecker"
rm -f "$extend_loop_stop"
(
  while [ ! -f "$extend_loop_stop" ]; do
    "$ROOT/scripts/drain-agent.sh" --extend-op "$DRAIN_OPID" >/dev/null 2>&1 || true
    sleep 0.5
  done
) &
extend_pid=$!
cleanup_extend() {
  : >"$extend_loop_stop"
  wait "$extend_pid" 2>/dev/null || true
  rm -f "$extend_loop_stop"
}
trap cleanup_extend EXIT

deadline=$(($(date +%s) + 120))
until {
  [ -n "$(compose ps --status running -q agent-linux 2>/dev/null)" ] \
    && [ -n "$(compose ps --status running -q agent-deploy 2>/dev/null)" ] \
    && volume_agent_paused woodpecker-ci-agent-linux-config \
    && volume_agent_paused woodpecker-ci-agent-deploy-config
}; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    cleanup_extend
    echo "Fresh paused agents bound to linux/deploy volumes did not appear under op $DRAIN_OPID within 120s." >&2
    exit 1
  fi
  sleep 1
done
cleanup_extend
trap - EXIT
printf 'Volume-bound agents paused under op %s (linux+deploy).\n' "$DRAIN_OPID"

# From here, extension failures are fatal. Re-claim, then wait for idle.
must_extend_op

idle_deadline=$(($(date +%s) + 1800))
while true; do
  must_extend_op
  if ! srw=$(db_count "$(
    cat <<SQL
SELECT COUNT(*) FROM workflows w
JOIN pipelines p ON p.id = w.pipeline_id
JOIN repos r ON r.id = p.repo_id
WHERE w.state = 'running'
  AND w.name = 'deploy'
  AND r.full_name LIKE '%strategy-replay-workbench%';
SQL
  )"); then
    echo "Failed to query SRW deploy status." >&2
    exit 1
  fi
  if [ "$srw" != "0" ]; then
    echo "SRW deploy running after agent bring-up; refusing to continue apply." >&2
    exit 2
  fi
  if ! running=$(db_count "SELECT COUNT(*) FROM workflows w
    JOIN mo117_drain_owned o ON o.agent_id = w.agent_id AND o.opid = '$DRAIN_OPID'
    WHERE w.state = 'running';"); then
    echo "Failed to query owned running workflows." >&2
    exit 1
  fi
  if ! volume_agent_paused woodpecker-ci-agent-linux-config \
    || ! volume_agent_paused woodpecker-ci-agent-deploy-config; then
    if [ "$(date +%s)" -ge "$idle_deadline" ]; then
      echo "Volume-bound agents lost pause ownership under op $DRAIN_OPID." >&2
      exit 1
    fi
    sleep 2
    continue
  fi
  if [ "$running" = "0" ]; then
    printf 'Post-extend idle: owned Docker agents quiet under op %s.\n' "$DRAIN_OPID"
    break
  fi
  if [ "$(date +%s)" -ge "$idle_deadline" ]; then
    echo "Owned agents still running workflows after extend (op $DRAIN_OPID)." >&2
    exit 1
  fi
  sleep 5
done

install -m 600 "$ROOT/com.shyamsivakumar.woodpecker-reaper.plist" \
  "$HOME/Library/LaunchAgents/"
install -m 600 "$ROOT/com.shyamsivakumar.woodpecker-backup-nightly.plist" \
  "$HOME/Library/LaunchAgents/"

for label in com.shyamsivakumar.woodpecker-reaper \
  com.shyamsivakumar.woodpecker-backup-nightly; do
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$HOME/Library/LaunchAgents/$label.plist"
  launchctl enable "$DOMAIN/$label" 2>/dev/null || true
done
launchctl kickstart "$DOMAIN/com.shyamsivakumar.woodpecker-reaper"

# Fail closed if the native LaunchAgent plist is missing or wrong.
if [ ! -f "$PLIST" ]; then
  echo "Native agent plist missing: $PLIST" >&2
  exit 1
fi
plist_max=$(/usr/libexec/PlistBuddy -c \
  'Print :EnvironmentVariables:WOODPECKER_MAX_WORKFLOWS' "$PLIST" 2>/dev/null || echo missing)
if [ "$plist_max" != "1" ]; then
  echo "Native agent plist WOODPECKER_MAX_WORKFLOWS is '$plist_max' (want 1)." >&2
  exit 1
fi

native_live_max() {
  pid=$1
  case "$pid" in
    '' | -)
      echo missing
      return
      ;;
  esac
  val=$(ps eww -p "$pid" -o command= 2>/dev/null \
    | tr ' ' '\n' | sed -n 's/^WOODPECKER_MAX_WORKFLOWS=//p' | head -1)
  if [ -n "$val" ]; then echo "$val"; else echo unknown; fi
}

native_pid=$(launchctl list 2>/dev/null | awk '$3=="org.woodpecker.agent"{print $1; exit}')
live_max=$(native_live_max "$native_pid")
db_row=$(query_db "SELECT IFNULL(capacity, -1) || '|' || IFNULL(last_contact, 0)
  FROM agents WHERE backend = 'local' ORDER BY id LIMIT 1;" || echo 'missing|0')
db_cap=${db_row%%|*}
old_contact=${db_row##*|}

need_reload=0
if [ "$live_max" != "1" ]; then
  printf 'Native agent live WOODPECKER_MAX_WORKFLOWS=%s (want 1); guarded reload.\n' \
    "$live_max"
  need_reload=1
fi
if [ "$db_cap" != "1" ]; then
  printf 'Native agents.capacity=%s (want 1); guarded reload.\n' "$db_cap"
  need_reload=1
fi

if [ "$need_reload" -eq 1 ]; then
  # Drain already held native idle + owned no_schedule. Reload the service
  # definition from the current plist (kickstart -k alone keeps a stale load).
  old_pid=$native_pid
  launchctl bootout "$DOMAIN/org.woodpecker.agent" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$PLIST"
  launchctl enable "$DOMAIN/org.woodpecker.agent" 2>/dev/null || true
  launchctl kickstart "$DOMAIN/org.woodpecker.agent"

  deadline=$(($(date +%s) + 90))
  while true; do
    new_pid=$(launchctl list 2>/dev/null | awk '$3=="org.woodpecker.agent"{print $1; exit}')
    new_max=$(native_live_max "$new_pid")
    new_row=$(query_db "SELECT IFNULL(capacity, -1) || '|' || IFNULL(last_contact, 0)
      FROM agents WHERE backend = 'local' ORDER BY id LIMIT 1;" || echo 'missing|0')
    new_cap=${new_row%%|*}
    new_contact=${new_row##*|}
    replaced=0
    case "$old_pid" in
      '' | -)
        if [ -n "$new_pid" ] && [ "$new_pid" != "-" ]; then replaced=1; fi
        ;;
      *)
        if [ -n "$new_pid" ] && [ "$new_pid" != "-" ] && [ "$new_pid" != "$old_pid" ]; then
          replaced=1
        fi
        ;;
    esac
    contact_fresh=0
    if [ "$new_contact" -gt "$old_contact" ] 2>/dev/null; then
      contact_fresh=1
    fi
    if [ "$replaced" -eq 1 ] && [ "$new_max" = "1" ] \
      && [ "$new_cap" = "1" ] && [ "$contact_fresh" -eq 1 ]; then
      printf 'Native agent reloaded pid=%s env=1 capacity=1 last_contact=%s (was %s).\n' \
        "$new_pid" "$new_contact" "$old_contact"
      break
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "Native agent did not prove fresh capacity 1 after plist reload (pid=$new_pid env=$new_max cap=$new_cap contact=$new_contact old_contact=$old_contact)." >&2
      exit 1
    fi
    sleep 2
  done
else
  printf 'Native agent live+DB capacity=1 (no reload).\n'
fi

# Resume only this apply drain op (refcount: other ops keep their pauses).
# Final claim + idle/ownership proof before clearing the drain op.
must_extend_op
if ! volume_agent_paused woodpecker-ci-agent-linux-config \
  || ! volume_agent_paused woodpecker-ci-agent-deploy-config; then
  echo "Volume-bound agents not paused under op $DRAIN_OPID before resume." >&2
  exit 1
fi
if ! running=$(db_count "SELECT COUNT(*) FROM workflows w
  JOIN mo117_drain_owned o ON o.agent_id = w.agent_id AND o.opid = '$DRAIN_OPID'
  WHERE w.state = 'running';"); then
  echo "Failed final owned-workflow idle check." >&2
  exit 1
fi
if [ "$running" != "0" ]; then
  echo "Owned agents still running workflows before resume (op $DRAIN_OPID)." >&2
  exit 1
fi
"$ROOT/scripts/drain-agent.sh" --resume "$DRAIN_OPID"

"$ROOT/scripts/verify.sh"

docker run --rm -v woodpecker-ci-server-data:/d:ro alpine:3.22 \
  sh -c 'apk add -q sqlite >/dev/null && sqlite3 -readonly file:/d/woodpecker.sqlite?mode=ro -header -column \
  "SELECT id, name, platform, backend, capacity, no_schedule, custom_labels FROM agents ORDER BY id;"'

printf 'MO-117 apply finished.\n'
