"""Proof for #778: the 2-of-3 rule on findings with real paths from SRW#2702 gate reports.

Lines are moved by hand around the real ones to show the window of 5 and the
severity match. The CHECK and PROVIDES lines are the ones the gate emits today.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordinator" / "bin"))
import gate_vote
from gate_policy import complete_pass, verdict

HEAD = "e2adfac8d754ec1f09bba7b92731ab594fb6b55d"
PROOF = "scripts/bot2_two_lane_admission_proof.cjs"
RUNTIME = "bot2/trade_machine.js"


def report(outcome, *findings):
    rows = [
        {
            "id": f"F{i}",
            "severity": s,
            "bar_clause": "n/a",
            "path": p,
            "line": l,
            "text": f"{s} at {p}",
            "fixed_when": "n/a",
        }
        for i, (s, p, l) in enumerate(findings, 1)
    ]
    block = "```json\n" + json.dumps({"verdict": outcome, "findings": rows}) + "\n```"
    return f"{block}\nsummary\n\nPROVIDES: PASS {HEAD}\nCHECK: PASS {HEAD}\nVERDICT: {outcome}"


CASES = {
    "two agree, line 271 vs 274 (within 5), same severity: FAIL": [
        report("FAIL", ("major", PROOF, 271), ("major", RUNTIME, 482)),
        report("FAIL", ("major", PROOF, 274)),
        report("PASS"),
    ],
    "271 vs 277 (6 apart): no agreement, PASS": [
        report("FAIL", ("major", PROOF, 271)),
        report("FAIL", ("major", PROOF, 277)),
        report("PASS"),
    ],
    "same line, major vs minor: no agreement, PASS": [
        report("FAIL", ("major", PROOF, 271)),
        report("PASS", ("minor", PROOF, 271)),
        report("PASS"),
    ],
    "two agree on a minor only: kept, still PASS": [
        report("PASS", ("minor", RUNTIME, 482)),
        report("PASS", ("minor", RUNTIME, 480)),
        report("PASS"),
    ],
    "one voter died without a verdict: merge of two, both must agree": [
        report("FAIL", ("major", PROOF, 271)),
        "the thread ended with no verdict",
        report("FAIL", ("major", PROOF, 268)),
    ],
    "two voters dead: fewer than 2 readable, FAIL not the primary alone": [report("PASS"), "no verdict", ""],
    "bare VERDICT: PASS without its own CHECK and PROVIDES lines is not counted, and no line is borrowed": [
        report("PASS"),
        "all fine\n\nVERDICT: PASS",
        "all fine\n\nVERDICT: PASS",
    ],
    "valid voters 1 and 2, voter 3 bare PASS: merge of 2, lines are voter 1 and 2's own": [
        report("PASS"),
        report("PASS"),
        "all fine\n\nVERDICT: PASS",
    ],
    "one voter CHECK FAIL: merged CHECK FAIL, findings still voted": [
        report("PASS"),
        report("PASS").replace(f"CHECK: PASS {HEAD}", f"CHECK: FAIL {HEAD}"),
        report("PASS"),
    ],
}
for name, reports in CASES.items():
    merged = gate_vote.merge_reports(reports, HEAD)
    print(
        f"--- {name}\n{merged}\nlane reads: verdict={verdict(merged)} complete_pass={complete_pass(merged, HEAD)}\n"
    )
