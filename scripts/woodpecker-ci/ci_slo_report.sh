#!/bin/sh
# MO-118: run the cross-repo CI SLO report against the M1 Woodpecker DB.
#
# Usage:
#   ./ci_slo_report.sh                  # SSH to m1, print markdown
#   ./ci_slo_report.sh --local          # on the M1 itself
#   ./ci_slo_report.sh --md out.md --json out.json
set -eu
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
export PATH

HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
exec /usr/bin/python3 "$HERE/ci_slo_report.py" "$@"
