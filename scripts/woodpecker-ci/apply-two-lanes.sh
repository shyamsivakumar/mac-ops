#!/bin/sh
# MO-117: resize Colima, swap in two Docker agents, install reaper + nightly backup.
# Refuses to run while an SRW deploy is active. Drains Docker work first.
set -eu

# shellcheck disable=SC1091
. "$(dirname -- "$0")/common.sh"

DOMAIN="gui/$(id -u)"
COLIMA_MEM=${COLIMA_MEM:-10}
LINUX_CAP=${LINUX_CAP:-3}

printf 'MO-117 apply: Colima memory=%sGiB ci-linux capacity=%s\n' "$COLIMA_MEM" "$LINUX_CAP"

"$ROOT/scripts/drain-agent.sh" all 1800

# Snapshot Colima config before resize.
if [ ! -f "$HOME/.colima/woodpecker/colima.yaml.before-mo117" ]; then
  cp "$HOME/.colima/woodpecker/colima.yaml" \
    "$HOME/.colima/woodpecker/colima.yaml.before-mo117"
fi

# Update memory in colima.yaml
python3 - <<PY
from pathlib import Path
p = Path.home() / ".colima/woodpecker/colima.yaml"
text = p.read_text()
import re
new = re.sub(r"(?m)^memory:\s*\d+", f"memory: $COLIMA_MEM", text, count=1)
if new == text and f"memory: $COLIMA_MEM" not in text:
    raise SystemExit("failed to set memory in colima.yaml")
p.write_text(new)
print(p, "memory ->", $COLIMA_MEM)
PY

# Stop Colima cleanly (agents already drained; server stop is brief).
compose stop agent agent-linux agent-deploy 2>/dev/null || true
"$COLIMA" stop woodpecker

# Kick Colima LaunchAgent so it picks up the new memory.
launchctl kickstart -k "$DOMAIN/com.shyamsivakumar.colima-woodpecker"

deadline=$(($(date +%s) + 180))
until "$COLIMA" status woodpecker >/dev/null 2>&1 && docker ps -q >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "Colima did not become ready after resize." >&2
    exit 1
  fi
  sleep 3
done

# Seed linux agent config from the previous single-agent volume when present.
if docker volume inspect woodpecker-ci-agent-config >/dev/null 2>&1; then
  docker volume create woodpecker-ci-agent-linux-config >/dev/null
  docker run --rm \
    -v woodpecker-ci-agent-config:/from:ro \
    -v woodpecker-ci-agent-linux-config:/to \
    alpine:3.22 sh -c 'cp -a /from/. /to/ && ls -la /to'
fi

# Bring up the new compose (removes orphaned single agent).
compose up -d --remove-orphans

# Install LaunchAgents for reaper and nightly backup.
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
launchctl kickstart -k "$DOMAIN/com.shyamsivakumar.woodpecker-reaper"

# Ensure native macOS agent stays at capacity 1.
launchctl kickstart -k "$DOMAIN/org.woodpecker.agent"

"$ROOT/scripts/verify.sh"

# Show agents table.
docker run --rm -v woodpecker-ci-server-data:/d:ro alpine:3.22 \
  sh -c 'apk add -q sqlite >/dev/null && sqlite3 -readonly file:/d/woodpecker.sqlite?mode=ro -header -column \
  "SELECT id, name, platform, backend, capacity, no_schedule FROM agents ORDER BY id;"'

printf 'MO-117 apply finished.\n'
