#!/bin/bash
set -e
Q="${1:-coordinator/bin/coordq}"
T=$(mktemp -d)
export COORD_JOURNAL_DIR=$T/j COORDQ_DIR=$T/q COORDINATOR_DECISIONS=$T/decisions.json
board() { echo "{\"items\":[$1]}" >"$COORDINATOR_DECISIONS"; }
item() { echo "{\"id\":\"$1\",\"group\":\"$2\",\"title\":\"t\",\"why\":\"w\",\"options\":[]}"; }
board "$(item a coordinator),$(item b mac-ops),$(item c mac-ops)"
python3 "$Q" decision sync
python3 "$Q" decision sync
python3 "$Q" decision answered a b
board "$(item a coordinator),$(item c mac-ops)"
python3 "$Q" decision sync
board "$(item a coordinator)"
python3 "$Q" decision sync
board "$(item a coordinator),$(item b mac-ops)"
python3 "$Q" decision sync
echo "journal rows (event item kind):"
python3 -c "
import glob, json, sys
for p in sorted(glob.glob(sys.argv[1] + '/events-*.jsonl')):
    for line in open(p):
        r = json.loads(line)
        print(r['event'], r['item'], r['kind'])
" "$T/j"
python3 "$Q" actrate --days 7
