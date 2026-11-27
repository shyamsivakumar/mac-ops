"""Proof for #778: run gate_vote.merge_reports on real SRW gate FAIL reports.

Real reports today are prose, not the JSON block the voters are asked for, so
this script lifts each `**Major ...** ... path:line` paragraph into that JSON
block first. Three reports of one PR (three heads) stand in for three voters;
their head hashes are rewritten to the first head so the CHECK lines compare.
"""

import itertools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordinator" / "bin"))
import gate_vote

SEVERITY = re.compile(r"\*\*(critical|major|minor)\b", re.IGNORECASE)
LOCATION = re.compile(r"\[?`?([\w./-]+\.\w+):(\d+)")


def with_json_block(report):
    findings = []
    for paragraph in report.split("\n\n"):
        severity, where = SEVERITY.search(paragraph), LOCATION.search(paragraph)
        if severity:
            findings.append(
                {
                    "id": f"F{len(findings) + 1}",
                    "severity": severity.group(1).lower(),
                    "bar_clause": "n/a",
                    "path": where.group(1) if where else "n/a",
                    "line": int(where.group(2)) if where else None,
                    "text": paragraph.split("**", 2)[-1].strip()[:90],
                    "fixed_when": "n/a",
                }
            )
    outcome = "FAIL" if re.search(r"VERDICT: FAIL\s*$", report) else "PASS"
    block = (
        "```json\n" + json.dumps({"verdict": outcome, "findings": findings}) + "\n```\n"
    )
    body, _, tail = report.rpartition("\n\n")
    return f"{body}\n\n{block}{tail}" if body else report


def head_of(key):
    return key.rsplit(":", 1)[1]


def show(pr, picked):
    head = head_of(picked[0]["key"])
    reports = [
        with_json_block(re.sub(r"\b[0-9a-f]{40}\b", head, row["report"]))
        for row in picked
    ]
    print(f"### {pr}: heads {[head_of(r['key'])[:8] for r in picked]}")
    for order in itertools.islice(itertools.permutations(range(3)), 0, 6, 5):
        merged = gate_vote.merge_reports([reports[i] for i in order], head)
        print(f"voter order {order}:\n{merged}\n")
    for index, row in enumerate(picked):
        report = reports[index]
        outcome, findings = gate_vote.read_verdict(report)
        print(
            f"  voter {head_of(row['key'])[:8]}: {outcome}, findings "
            + "; ".join(f"[{f['severity']}] {f['path']}:{f['line']}" for f in findings)
        )


with open(sys.argv[1]) as rows_file:
    rows = json.load(rows_file)
by_pr = {}
for row in rows:
    by_pr.setdefault(row["key"].split("#")[1].split(":")[0], []).append(row)
for pr in sys.argv[2:]:
    show(pr, by_pr[pr][:3])
