#!/bin/sh
cd "$(dirname "$0")/../.." || exit 1
grep -q 'most severe first' coordinator/bin/gate_bar.py || {
  echo "gate_bar.py has no one-pass rule"
  exit 1
}
python3 - <<'P'
import sys
sys.path.insert(0, "coordinator/bin")
import gate_policy
b = gate_policy.build_gate_brief({"key": "MO", "projectId": "fixture"}, "shyamsivakumar/mac-ops", 554, 554, "a" * 40, publisher=False, base="main")
assert "most severe first" in b and "Failure paths checked:" in b, "brief lacks bullet"
print("\n".join([l for l in b.splitlines() if l.strip()][-3:]))
P
