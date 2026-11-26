import glob
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for sub in ("coordinator/bin", "coordinator/overnight"):
    sys.path.insert(0, os.path.join(ROOT, sub))
os.environ["COORD_JOURNAL_DIR"] = tempfile.mkdtemp()

import gate_policy
import gate_score

REPORTS = sorted(
    glob.glob(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports", "fail*.txt")
    )
)
mode = sys.argv[1]


def head_of(report):
    return re.search(r"^CHECK: FAIL (\w+)", report, re.MULTILINE).group(1)


def show(name, report, call):
    new, dropped = gate_score.score_findings(report, call)
    head = head_of(report)
    print(
        f"{name}: findings={len(gate_score.findings_of(report))} dropped={len(dropped)} "
        f"verdict {gate_policy.read_verdict(report)[0]} -> {gate_policy.read_verdict(new)[0]} "
        f"complete_pass={gate_policy.complete_pass(new, head)} unchanged={new == report}"
    )
    for title in dropped:
        print("   dropped:", title)
    return new


def raises(_prompt):
    raise OSError("model unreachable")


if mode == "fake":
    for path in REPORTS:
        name = os.path.basename(path)
        report = Path(path).read_text()
        count = len(gate_score.findings_of(report))
        show(name + " all low", report, lambda _p, c=count: json.dumps([2] * c))
        show(
            name + " one kept",
            report,
            lambda _p, c=count: json.dumps([2] * (c - 1) + [9]),
        )
        show(name + " unparseable", report, lambda _p: "I cannot score these")
        show(
            name + " wrong length",
            report,
            lambda _p, c=count: json.dumps([1] * (c + 1)),
        )
        show(name + " call raises", report, raises)
    passing = "All good.\n\nCHECK: PASS abc\nPROVIDES: PASS abc\nVERDICT: PASS"
    show_new = gate_score.score_findings(passing, lambda _p: "[1]")
    print("a PASS report is untouched:", show_new == (passing, []))
elif mode == "real":
    report = Path(REPORTS[1]).read_text()
    print("model spec:", next(iter(gate_score.models.pi_routes("quick"))))
    seen = {}

    def spy(prompt):
        seen["answer"] = gate_score.pi_call(prompt)
        return seen["answer"]

    show("fail2 (real cheap model)", report, spy)
    print("raw model answer:", repr(seen.get("answer")))
elif mode == "lane":
    import lane_driver as ld

    if not hasattr(ld.journal, "treatment_names"):
        ld.journal.treatment_names = lambda arm, _side, _name: arm == "treatment"
    report = Path(REPORTS[1]).read_text()
    head = head_of(report)
    tmp = tempfile.mkdtemp()
    ld.RECEIPTS = os.path.join(tmp, "receipts.json")
    Path(ld.RECEIPTS).write_text(
        json.dumps({f"gate:r/x#1:{head}": "thread1", "base:thread1": "main"})
    )
    ld.gate_in_flight = lambda _t: False
    ld.last_reply = lambda _t: report
    ld.gate_score.pi_call = lambda _prompt: "[1, 2]"
    ld.prompt_pull = lambda *_a, **_k: None
    for label, arm in (
        ("no experiment (assigned_arm None)", None),
        ("control arm", "control"),
        ("treatment arm", "treatment"),
    ):
        ledger = {}
        ld.journal.assigned_arm = lambda *_args, a=arm, **_kwargs: a
        verdict, gate, reply = ld.gate_verdict("r/x", 1, head, "main", ledger)
        print(f"{label}: verdict={verdict} ledger_keys={sorted(ledger)}")
    ld.gate_score.pi_call = lambda _prompt: "garbage"
    ledger = {}
    verdict, gate, reply = ld.gate_verdict("r/x", 1, head, "main", ledger)
    print(
        f"treatment, model returns garbage: verdict={verdict} ledger_keys={sorted(ledger)}"
    )
    rows = [
        json.loads(l)
        for f in glob.glob(
            os.path.join(os.environ["COORD_JOURNAL_DIR"], "events-*.jsonl")
        )
        for l in Path(f).read_text().splitlines()
    ]
    print("journal rows:", [(r["event"], r["data"].get("dropped")) for r in rows])
