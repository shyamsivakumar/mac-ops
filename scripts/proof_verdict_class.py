import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "coordinator" / "overnight"))
import lane_driver as lane

ROWS = (
    ("size", "Major: 616 changed lines against a hard 150 cap: runtime 145, the 471-line admission proof script pushes it over."),
    ("size", "Major: 176 counted lines against the 150 aggregate, and a fourth runtime file outside the three-file scope."),
    ("proof", "Major: Two required cases unproved: two lanes competing for one contract, and a timed-out reservation."),
    ("proof", "Major: The proof hashes a body and calls laneStore.apply instead of sending an HMAC-signed save."),
    ("scope", "Major: Edits an existing restart proof so the gate passes, which #2689 forbids."),
    ("scope", "Major: 379 changed code lines across four files and it edits two proofs #2708 excludes."),
    ("logic", "Major: A frozen account still permits a buy when the daily rule is off. Secondary: 161 changed lines over the 150-line cap."),
    ("logic", "Major: bot2_service.js:103 reports the pair blocked when Lane 2 is occupied."),
)
failed = 0
for want, text in ROWS:
    report = f"{text}\n\nCHECK: FAIL {'a' * 40}\nVERDICT: FAIL"
    got = lane.failure_class(report, "ok", {})
    failed += got != want
    print(f"{'ok  ' if got == want else 'FAIL'} want {want:5} got {got:5} {text[:60]}")

structured = '```json\n{"verdict": "FAIL", "findings": [{"severity": "minor", "path": "a.py", "line": 1, "text": "150 cap"}]}\n```\nVERDICT: FAIL'
for report, want in ((structured, "minor_only"), ("VERDICT: FAIL", "logic"), ("fails the same on origin/main\nVERDICT: FAIL", "environment")):
    got = lane.failure_class(report, "ok", {})
    failed += got != want
    print(f"{'ok  ' if got == want else 'FAIL'} want {want:10} got {got:10} {report[:40]!r}")
print("verdict class proof:", "FAILED" if failed else "ok")
sys.exit(1 if failed else 0)
