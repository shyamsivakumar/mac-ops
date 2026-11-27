#!/bin/bash
# usage: proof.sh <tree>   (a checkout of mac-ops; code commit 169bca12e06444f803d27cf14363e0ae12936ceb)
tree=$(cd "$1" && pwd)
tmp=$(mktemp -d)
export COORD_JOURNAL_DIR=$tmp/journal COORDINATOR_DECISIONS=$tmp/decisions.json
echo '{"items":[]}' >"$COORDINATOR_DECISIONS"
cd "$tree" || exit 1
python3 - <<'P'
import sys
sys.path.insert(0, "coordinator/bin")
import journal
for card, text in (("1101", "No playbook for Cloud Run deploys"), ("1102", "no playbook for cloud run deploys!"), ("1103", "How to rotate keys")):
    journal.emit_gap("worker", card, text, "playbooks/ and wiki")
P
echo "--- curator --dry-run"
coordinator/bin/curator --dry-run
echo "--- board after dry-run"
cat "$COORDINATOR_DECISIONS"
echo "--- curator"
coordinator/bin/curator
echo "--- board"
python3 -c "import json,sys;print([i['id'] for i in json.load(open(sys.argv[1]))['items']])" "$COORDINATOR_DECISIONS"
