#!/bin/sh
# MO-124: daily collect + eval of T3 agent build sessions on this Mac.
#
# Writes scrubbed traces under ~/.local/state/mac-ops/session-traces/ and a
# daily table under ~/.local/state/mac-ops/session-evals/. Copies the markdown
# + JSON into coordinator/evidence when that path exists.
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
export PATH

HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH='' cd -- "$HERE/../.." && pwd)
STATE=${MAC_OPS_STATE:-$HOME/.local/state/mac-ops}
COORD_DIR=${COORD_DIR:-$HOME/Code/coordinator/evidence}
DATE=${1:-$(TZ=America/Los_Angeles date +%Y-%m-%d)}
STAMP=$(TZ=America/Los_Angeles date +%Y-%m-%dT%H%M%S%z)
LOG_DIR=$STATE/session-evals/logs
mkdir -p "$LOG_DIR"
runlog=$LOG_DIR/daily-$STAMP.log

{
  printf 'session_traces_daily start %s day=%s\n' "$STAMP" "$DATE"
  /usr/bin/python3 "$REPO/mo124" run-daily --day "$DATE"
  md=$STATE/session-evals/$DATE.md
  json=$STATE/session-evals/$DATE.json
  if [ -d "$COORD_DIR" ]; then
    cp "$md" "$COORD_DIR/session-eval-$DATE.md"
    cp "$json" "$COORD_DIR/session-eval-$DATE.json"
    printf 'Posted to %s/session-eval-%s.{md,json}\n' "$COORD_DIR" "$DATE"
  fi
} >"$runlog" 2>&1

# Echo the markdown for LaunchAgent stdout / manual runs.
cat "$STATE/session-evals/$DATE.md"
