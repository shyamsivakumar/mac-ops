#!/bin/sh
# MO-117: resize Colima, swap in two Docker agents, install reaper + nightly backup.
# Refuses to run while an SRW deploy is active. Drains Docker (+native if
# needed) with no_schedule set before stopping Colima. Does not restart the
# native agent; only verifies WOODPECKER_MAX_WORKFLOWS=1 in its plist.
set -eu

# shellcheck source-path=SCRIPTDIR source=common.sh
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

# Enforce native capacity 1 via plist (no kickstart — that would cancel a
# live darwin job). Fix the file if drifted; operator reloads when idle.
if [ -f "$PLIST" ]; then
  max=$(/usr/libexec/PlistBuddy -c 'Print :EnvironmentVariables:WOODPECKER_MAX_WORKFLOWS' \
    "$PLIST" 2>/dev/null || echo missing)
  if [ "$max" != "1" ]; then
    echo "Native agent WOODPECKER_MAX_WORKFLOWS is '$max' (want 1)." >&2
    echo "Fix $PLIST then: drain-agent.sh native && launchctl kickstart -k $DOMAIN/org.woodpecker.agent" >&2
    exit 1
  fi
  printf 'Native agent plist WOODPECKER_MAX_WORKFLOWS=1 (not restarted).\n'
fi

# Resume scheduling now that the new agents are up.
"$ROOT/scripts/drain-agent.sh" --resume

"$ROOT/scripts/verify.sh"

docker run --rm -v woodpecker-ci-server-data:/d:ro alpine:3.22 \
  sh -c 'apk add -q sqlite >/dev/null && sqlite3 -readonly file:/d/woodpecker.sqlite?mode=ro -header -column \
  "SELECT id, name, platform, backend, capacity, no_schedule, custom_labels FROM agents ORDER BY id;"'

printf 'MO-117 apply finished.\n'
