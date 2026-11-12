#!/bin/sh
# Daily collect + eval of Empryo hub agent build sessions on this Mac.
#
# Default day is the *previous* local calendar day so the 17:30 LaunchAgent
# covers a finished day. Unfinished runs from recent days are reconciled, and
# every changed day's report is regenerated. Writes scrubbed traces under
# ~/.local/state/mac-ops/session-traces/ and tables under session-evals/;
# copies into coordinator/evidence when present.
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
export PATH

HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH='' cd -- "$HERE/../.." && pwd)
STATE=${MAC_OPS_STATE:-$HOME/.local/state/mac-ops}
COORD_DIR=${COORD_DIR:-$HOME/Code/coordinator/evidence}
if [ "${1-}" != "" ]; then
  DATE=$1
else
  DATE=$(TZ=America/Los_Angeles date -v-1d +%Y-%m-%d)
fi
STAMP=$(TZ=America/Los_Angeles date +%Y-%m-%dT%H%M%S%z)
LOG_DIR=$STATE/session-evals/logs
mkdir -p "$LOG_DIR"
runlog=$LOG_DIR/daily-$STAMP.log

{
  printf 'session_traces_daily start %s day=%s\n' "$STAMP" "$DATE"
  /usr/bin/python3 "$REPO/mo124" run-daily --day "$DATE"
  manifest=$STATE/session-evals/_last_daily.json
  if [ -f "$manifest" ] && [ -d "$COORD_DIR" ]; then
    /usr/bin/python3 - "$manifest" "$STATE" "$COORD_DIR" <<'PY'
import json, sys
from pathlib import Path
manifest, state, coord = sys.argv[1:4]
obj = json.loads(Path(manifest).read_text(encoding="utf-8"))
days = obj.get("days_reported") or [obj.get("day")]
coord_p = Path(coord)
for d in days:
    if not d:
        continue
    md = Path(state) / "session-evals" / f"{d}.md"
    js = Path(state) / "session-evals" / f"{d}.json"
    if md.is_file() and js.is_file():
        (coord_p / f"session-eval-{d}.md").write_bytes(md.read_bytes())
        (coord_p / f"session-eval-{d}.json").write_bytes(js.read_bytes())
        print(f"Posted to {coord}/session-eval-{d}.{{md,json}}")
PY
  fi
} >"$runlog" 2>&1

cat "$STATE/session-evals/$DATE.md"
