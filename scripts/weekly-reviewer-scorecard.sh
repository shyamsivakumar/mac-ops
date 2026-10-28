#!/usr/bin/env bash
# Weekly reviewer agreement scorecard (MO-10/MO-18). Automation-ready: run via
#   ~/.local/bin/heavy --review /path/to/mac-ops/scripts/weekly-reviewer-scorecard.sh
# or register on the board with herdr-projects automations add (see docs/reviewer-audit.md).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEEK="${1:-$(date +%Y-%m-%d)}"
OUT="${MO18_SCORECARD_OUT:-${HOME}/.herdr-projects/reports/mac-ops/reviewer-weekly/${WEEK}}"
BASELINE="${MO18_BASELINE:-${HOME}/.herdr-projects/reports/mac-ops/10/scorecard.json}"
cd "$ROOT"
# Each shadow repeat already runs through heavy --review; do not wrap the whole job
# in an outer heavy (that blocks on one review slot for hours).
exec python3 mo10 scorecard \
  --heavy \
  --review-policy board \
  --baseline-scorecard "$BASELINE" \
  --out "$OUT"
