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
    return re.search(r"^CHECK: (?:FAIL|PASS) (\w+)", report, re.MULTILINE).group(1)


def check_pass(report):
    return report.replace("CHECK: FAIL", "CHECK: PASS")


def show(name, report, call):
    new, dropped = gate_score.score_findings(report, call)
    head = head_of(report)
    print(
        f"{name}: findings={len(gate_score.findings_of(report))} dropped={len(dropped)} "
        f"verdict {gate_policy.read_verdict(report)[0]} -> {gate_policy.read_verdict(new)[0]} "
        f"remaining_majors={len(gate_score.findings_of(new))} "
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
        show(name + " CHECK FAIL, all low", report, lambda _p, c=count: json.dumps([0] * c))
        ok = check_pass(report)
        low = lambda _p, c=count: json.dumps([6] * c)
        show(name + " CHECK PASS (edited), all at 6", ok, low)
        show(name + " CHECK PASS (edited), all at 7", ok, lambda _p, c=count: json.dumps([7] * c))
        show(name + " CHECK PASS (edited), first low, rest kept", ok, lambda _p, c=count: json.dumps([2] + [9] * (c - 1)))
        show(name + " CHECK PASS (edited), unparseable", ok, lambda _p: "I cannot score these")
        show(name + " CHECK PASS (edited), wrong length", ok, lambda _p, c=count: json.dumps([1] * (c + 1)))
        show(name + " CHECK PASS (edited), call raises", ok, raises)
    partial = show("fail2 partial drop report body", check_pass(Path(REPORTS[1]).read_text()), lambda _p: "[2, 9]")
    print(partial)
    tail = "\n\nCHECK: PASS abc\nPROVIDES: PASS abc\nVERDICT: FAIL"
    consecutive = "Major - a.py:1 first bug.\nMajor - b.py:2 second bug." + tail
    print("two consecutive Majors, parsed:", len(gate_score.findings_of(consecutive)))
    show_cases = (
        ("two consecutive Majors, first scored low", consecutive, "[2, 9]"),
        ("two consecutive Majors, both scored low", consecutive, "[2, 3]"),
        ("bulleted Majors, first scored low", "- Major: a.py:1 x.\n- Major: b.py:2 y." + tail, "[2, 9]"),
        ("numbered Majors, first scored low", "1. Major: a.py:1 x.\n2. Critical: b.py:2 y." + tail, "[2, 9]"),
    )
    for label, text, answer in show_cases:
        new, dropped = gate_score.score_findings(text, lambda _p, a=answer: a)
        print(
            f"{label}: findings={len(gate_score.findings_of(text))} dropped={len(dropped)} "
            f"verdict -> {gate_policy.read_verdict(new)[0]} unchanged={new == text}"
        )
    variants = [
        "Major \u2014 a.py:1 x.", "[major] a.py:1 x.", "**Critical**: a.py:1 x.", "- major: a.py:1 x.",
        "1) MAJOR a.py:1 x.", "`Major` a.py:1 x.", "> Critical - a.py:1 x.", "[Critical] a.py:1 x.",
    ]
    print("all-format variants, each alone, scored low flips only when nothing else blocks:")
    for variant in variants:
        text = variant + tail
        new, dropped = gate_score.score_findings(text, lambda _p: "[1]")
        print(f"  {variant!r}: findings={len(gate_score.findings_of(text))} dropped={len(dropped)} verdict -> {gate_policy.read_verdict(new)[0]}")
    for first in variants[:4]:
        for second in variants[4:]:
            text = first + "\n" + second + tail
            new, dropped = gate_score.score_findings(text, lambda _p: "[1, 9]")
            print(f"  mixed {first!r} + {second!r}, first scored low: findings={len(gate_score.findings_of(text))} dropped={len(dropped)} verdict -> {gate_policy.read_verdict(new)[0]}")
    mixed = "Major \u2014 a.py:1 first.\n[major] b.py:2 second.\n" + "Left for later\n\nMinor \u2014 c.py:3 tidy." + tail
    new, dropped = gate_score.score_findings(mixed, lambda _p: "[2, 9]")
    print(f"mixed Major and [major], one scored low: dropped={len(dropped)} verdict -> {gate_policy.read_verdict(new)[0]}")
    new, dropped = gate_score.score_findings(mixed, lambda _p: "[2, 3]")
    print(f"mixed Major and [major], both scored low, minor kept: dropped={len(dropped)} verdict -> {gate_policy.read_verdict(new)[0]}")
    json_left = (
        "Major \u2014 a.py:1 first bug.\n\n```json\n"
        + json.dumps({"verdict": "FAIL", "findings": [
            {"id": "F1", "severity": "Major", "bar_clause": "x", "path": "a.py", "line": 1, "text": "first bug.", "fixed_when": "y"},
            {"id": "F2", "severity": "critical", "bar_clause": "x", "path": "b.py", "line": 2, "text": "second bug.", "fixed_when": "y"}]})
        + "\n```" + tail
    )
    new, dropped = gate_score.score_findings(json_left, lambda _p: "[1, 9]")
    print(f"json block with a kept critical, one dropped: dropped={len(dropped)} verdict -> {gate_policy.read_verdict(new)[0]}")
    word_cases = (
        ("### Critical: heading plus Major: line, Major scored low", "### Critical: a.py:1 x.\n\nMajor: b.py:2 y." + tail, "[1]"),
        ("table row with Critical plus Major: line, Major scored low", "| Critical | a.py:1 |\n\nMajor: b.py:2 y." + tail, "[1]"),
        ("prose 'no major risk' left after the only finding is dropped", "Major: a.py:1 x.\n\nI see no major risk elsewhere." + tail, "[1]"),
        ("Major line with a ### Critical heading directly under it, Major scored low", "Major: a.py:1 x.\n### Critical: b.py:2 y." + tail, "[1]"),
        ("clean report, every finding dropped, no other severity word", "Major: a.py:1 x.\n\nThe diff is otherwise fine." + tail, "[1]"),
    )
    for label, text, answer in word_cases:
        new, dropped = gate_score.score_findings(text, lambda _p, a=answer: a)
        print(f"{label}: dropped={len(dropped)} verdict -> {gate_policy.read_verdict(new)[0]}")
    footer_text = "Major: a.py:1 x.\nBuilder check: PASS abc\nCHECK: PASS abc\nPROVIDES: PASS abc\nVERDICT: FAIL"
    reply_cases = (
        ("reply 'Initial score [3]. final score [9]'", "Major: a.py:1 x." + tail, "Initial score [3]. final score [9]"),
        ("reply with a fenced json list", "Major: a.py:1 x." + tail, "```json\n[2]\n```"),
        ("reply with a bare fence", "Major: a.py:1 x." + tail, "```\n[2]\n```"),
        ("reply with a score of 11", "Major: a.py:1 x." + tail, "[11]"),
        ("reply with a boolean", "Major: a.py:1 x." + tail, "[true]"),
        ("reply with a float", "Major: a.py:1 x." + tail, "[2.0]"),
        ("reply with trailing prose", "Major: a.py:1 x." + tail, "[2] done"),
        ("footer directly after the last finding, scored low", footer_text, "[2]"),
    )
    for label, text, answer in reply_cases:
        new, dropped = gate_score.score_findings(text, lambda _p, a=answer: a)
        print(
            f"{label}: dropped={len(dropped)} verdict -> {gate_policy.read_verdict(new)[0]} "
            f"unchanged={new == text}"
        )
        if label.startswith("footer"):
            print("   footer lines kept:", [l for l in new.splitlines() if l.startswith(("CHECK", "PROVIDES", "VERDICT", "Builder"))])
    json_report = (
        "Major - a.py:1 first bug.\nMajor - b.py:2 second bug.\n\n```json\n"
        + json.dumps({"verdict": "FAIL", "findings": [
            {"id": "F1", "severity": "major", "bar_clause": "x", "path": "a.py", "line": 1, "text": "first bug.", "fixed_when": "y"}]})
        + "\n```" + tail
    )
    new, dropped = gate_score.score_findings(json_report, lambda _p: "[1]")
    print(
        "mismatch (2 Major lines in the text, 1 finding in the json block, scored low): "
        f"dropped={len(dropped)} unchanged={new == json_report} verdict={gate_policy.read_verdict(new)[0]}"
    )
    passing = "All good.\n\nCHECK: PASS abc\nPROVIDES: PASS abc\nVERDICT: PASS"
    show_new = gate_score.score_findings(passing, lambda _p: "[1]")
    print("a PASS report is untouched:", show_new == (passing, []))
elif mode == "real":
    report = check_pass(Path(REPORTS[1]).read_text())
    print("model spec:", next(iter(gate_score.models.pi_routes("quick"))))
    seen = {}

    def spy(prompt):
        seen["answer"] = gate_score.pi_call(prompt)
        return seen["answer"]

    show("fail2 CHECK PASS edited (real cheap model)", report, spy)
    print("raw model answer:", repr(seen.get("answer")))
elif mode == "lane":
    import lane_driver as ld

    ld.journal.factory_experiments = lambda: [{"name": "score2-trial", "side": "gate", "split": 50, "names": ["score2"]}]
    arms = {"42": "treatment", "7": "control"}
    ld.journal.assigned_arm = lambda _repo, ticket, gate=False: arms.get(str(ticket))
    prs = {
        7: {"body": "Refs #42"},
        42: {"body": "Refs #7"},
        50: {"body": "no ticket named"},
    }
    ld.open_prs = lambda _repo: prs
    ok = check_pass(Path(REPORTS[1]).read_text())
    failed_check = Path(REPORTS[1]).read_text()
    head = head_of(ok)
    tmp = tempfile.mkdtemp()
    ld.RECEIPTS = os.path.join(tmp, "receipts.json")
    Path(ld.RECEIPTS).write_text(
        json.dumps({**{f"gate:r/x#{n}:{head}": f"t{n}" for n in prs}, **{f"base:t{n}": "main" for n in prs}})
    )
    ld.gate_in_flight = lambda _t: False
    ld.prompt_pull = lambda *_a, **_k: None
    calls = []

    def fake_pi(_prompt):
        calls.append(1)
        return "[1, 2]"

    ld.gate_score.pi_call = fake_pi
    ld.last_reply = lambda _t: ok
    for label, number in (
        ("PR 7, ticket 42 (treatment)", 7),
        ("PR 42, ticket 7 (control; PR number equals the treated ticket)", 42),
        ("PR 50, no Refs (not in the arm)", 50),
    ):
        ledger = {}
        verdict, _gate, _reply = ld.gate_verdict("r/x", number, head, "main", ledger)
        print(f"{label}: verdict={verdict} model_calls={len(calls)} ledger_keys={sorted(ledger)}")
    ld.last_reply = lambda _t: failed_check
    ledger = {}
    verdict, _gate, _reply = ld.gate_verdict("r/x", 7, head, "main", ledger)
    print(f"PR 7, treatment, CHECK: FAIL report, low scores: verdict={verdict}")
    ld.last_reply = lambda _t: ok
    calls.clear()
    ld.gate_score.pi_call = lambda _prompt: calls.append(1) or ""
    ledger = {}
    for tick in (1, 2, 3):
        verdict, _gate, _reply = ld.gate_verdict("r/x", 7, head, "main", ledger)
        print(f"PR 7, model returns empty, tick {tick}: verdict={verdict} model_calls={len(calls)} score2={ledger.get('score2:t7')!r}")

    def raising(_prompt):
        calls.append(1)
        raise OSError("pi missing")

    ld.gate_score.pi_call = raising
    calls.clear()
    ledger = {}
    for tick in (1, 2):
        verdict, _gate, _reply = ld.gate_verdict("r/x", 7, head, "main", ledger)
        print(f"PR 7, model call raises, tick {tick}: verdict={verdict} model_calls={len(calls)} score2={ledger.get('score2:t7')!r}")
    rows = [
        json.loads(line)
        for f in glob.glob(os.path.join(os.environ["COORD_JOURNAL_DIR"], "events-*.jsonl"))
        for line in Path(f).read_text().splitlines()
    ]
    print("journal rows:", [(r["event"], r["pr"], len(r["data"].get("dropped") or [])) for r in rows])
