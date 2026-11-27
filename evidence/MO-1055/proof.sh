#!/bin/sh
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
grep -q verdict_block_missing "$ROOT/coordinator/bin/gate_score.py" || {
  echo "gate_score.py has no missing-block guard"
  exit 1
}
PYTHONDONTWRITEBYTECODE=1 python3 - "$ROOT" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/coordinator/bin")
import gate_score, gate_vote
H = "abc123"
block = '```json\n{"verdict": "FAIL", "findings": [{"id": "F1", "severity": "major", "bar_clause": "x", "path": "a.py", "line": 3, "text": "bad edge", "fixed_when": "y"}]}\n```'
tail = f"CHECK: PASS {H}\nPROVIDES: PASS {H}\nVERDICT: FAIL"
withblock = f"{block}\nsummary\n{tail}"
prose = f"[major] a.py:3 bad edge\n{tail}"
low = lambda _p: "[1]"
new, dropped = gate_score.score_findings(withblock, low)
print("block scored, dropped:", len(dropped))
new, dropped = gate_score.score_findings(prose, low)
print("prose unchanged:", new == prose, "dropped:", len(dropped), "findings_of:", gate_score.findings_of(prose))
print("1 block ballot + 2 prose:", gate_vote.merge_reports([withblock, prose, prose], H).splitlines()[0])
print("2 block ballots + 1 prose:", gate_vote.merge_reports([withblock, withblock, prose], H).splitlines()[0])
PY
