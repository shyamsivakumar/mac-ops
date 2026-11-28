import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coordinator" / "bin"))
import gate_policy

HEAD = "a" * 40
FILES = [
    {"filename": "coordinator/bin/ticket", "status": "modified", "additions": 100, "deletions": 20},
    {"filename": "scripts/proof_big.sh", "status": "added", "additions": 300, "deletions": 0},
    {"filename": "evidence/MO-1/check-proof.md", "status": "added", "additions": 40, "deletions": 0},
    {"filename": "README.md", "status": "modified", "additions": 5, "deletions": 0},
]


def brief(**kwargs):
    return gate_policy.build_gate_brief({"key": "MO"}, "shyamsivakumar/mac-ops", 1, 2, HEAD, False, **kwargs)


plain = brief()
sized = brief(sizes=gate_policy.size_text(FILES, 150, 3))
line = next(row for row in sized.splitlines() if row.startswith("Computed counts"))
print(line)
checks = {
    "runtime 120 in 1 file": "runtime 120 code lines in 1 code files" in line,
    "proof 340": "proof, fixture and evidence lines 340" in line,
    "caps named": "caps 150 lines, 3 files" in line,
    "no brief change without sizes": "Computed counts" not in plain,
    "rest of the brief is kept": sized.replace(line + "\n", "") == plain,
}
for name, ok in checks.items():
    print("ok  " if ok else "FAIL", name)
sys.exit(0 if all(checks.values()) else 1)
