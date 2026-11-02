#!/bin/sh
# MO-118: daily 5 PM PT CI SLO report → coordinator evidence on the M4.
#
# Runs on the M1 LaunchAgent (or by hand). Writes locally under
# ~/Library/Logs/woodpecker/ci-slo/, then scp's md+json to
# shyams-m4:~/Code/coordinator/evidence/ci-slo-<date>.{md,json}.
set -eu
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
export PATH

HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
LOG_DIR=${LOG_DIR:-$HOME/Library/Logs/woodpecker/ci-slo}
COORD_HOST=${COORD_HOST:-shyams-m4}
COORD_DIR=${COORD_DIR:-/Users/shyamsivakumar/Code/coordinator/evidence}
DATE=$(TZ=America/Los_Angeles date +%Y-%m-%d)
STAMP=$(TZ=America/Los_Angeles date +%Y-%m-%dT%H%M%S%z)

mkdir -p "$LOG_DIR"
md="$LOG_DIR/ci-slo-$DATE.md"
json="$LOG_DIR/ci-slo-$DATE.json"
runlog="$LOG_DIR/daily-$STAMP.log"

{
  printf 'ci_slo_daily start %s\n' "$STAMP"
  /usr/bin/python3 "$HERE/ci_slo_report.py" --local \
    --md-out "$md" --json-out "$json"
  printf 'Wrote %s and %s\n' "$md" "$json"
  ssh -o BatchMode=yes "$COORD_HOST" "mkdir -p '$COORD_DIR'"
  scp -o BatchMode=yes -q "$md" "$json" "$COORD_HOST:$COORD_DIR/"
  printf 'Posted to %s:%s/ci-slo-%s.{md,json}\n' "$COORD_HOST" "$COORD_DIR" "$DATE"
} >"$runlog" 2>&1

# Also echo the markdown for LaunchAgent stdout / manual runs.
cat "$md"
