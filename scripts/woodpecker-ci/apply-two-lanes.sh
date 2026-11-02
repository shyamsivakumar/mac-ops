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
"$ROOT/scripts/drain-agent.sh" all 1800

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

compose up -d --remove-orphans

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

# Live process env (LaunchAgent may still be running the old value).
live_max=
native_pid=$(launchctl list 2>/dev/null | awk '$3=="org.woodpecker.agent"{print $1; exit}')
case "$native_pid" in
  '' | -) live_max=missing ;;
  *)
    live_max=$(ps eww -p "$native_pid" -o command= 2>/dev/null \
      | tr ' ' '\n' | sed -n 's/^WOODPECKER_MAX_WORKFLOWS=//p' | head -1)
    [ -n "$live_max" ] || live_max=unknown
    ;;
esac

# agents.capacity as reported to the server (source of truth for scheduling).
db_cap=$(query_db "SELECT IFNULL(capacity, -1) FROM agents
  WHERE backend = 'local' ORDER BY id LIMIT 1;" || echo missing)

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
  # Drain already held native idle + owned no_schedule; safe to reload.
  launchctl kickstart -k "$DOMAIN/org.woodpecker.agent"
  deadline=$(($(date +%s) + 60))
  until [ "$(query_db "SELECT IFNULL(capacity, -1) FROM agents
      WHERE backend = 'local' ORDER BY id LIMIT 1;")" = "1" ]; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "Native agent did not report capacity 1 after guarded reload." >&2
      exit 1
    fi
    sleep 2
  done
  printf 'Native agent reloaded; agents.capacity=1.\n'
else
  printf 'Native agent live+DB capacity=1 (no reload).\n'
fi

# Resume only agents this drain owned.
"$ROOT/scripts/drain-agent.sh" --resume

"$ROOT/scripts/verify.sh"

docker run --rm -v woodpecker-ci-server-data:/d:ro alpine:3.22 \
  sh -c 'apk add -q sqlite >/dev/null && sqlite3 -readonly file:/d/woodpecker.sqlite?mode=ro -header -column \
  "SELECT id, name, platform, backend, capacity, no_schedule, custom_labels FROM agents ORDER BY id;"'

printf 'MO-117 apply finished.\n'
