#!/bin/sh
Q=${1:-coordinator/bin/coordq}
D=$(mktemp -d); J=$(mktemp -d)
export COORDQ_DIR=$D COORD_JOURNAL_DIR=$J COORDINATOR_DECISIONS=$D/decisions.json
echo '{"cap":1}' > $D/config.json
python3 $Q wait start card-1 --owner shyam || exit 1
python3 - "$D" <<'PY'
import json, sys, time
p = sys.argv[1] + "/queue.json"
q = json.load(open(p))
q["approvalWaits"]["card-1"]["since"] = time.time() - 90 * 60
json.dump(q, open(p, "w"))
PY
python3 $Q wait start card-1 --owner someone-else >/dev/null
python3 $Q waits
python3 $Q wait end card-1
