#!/usr/bin/env python3
"""Execute gate definitions only; never import or launch emp-hub.

Optional arguments are activity-view JSON returned by emp_thread_read.
Replay each original run before its manual restatement.
"""
import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
NAMES = {"check_line_ok", "judge_review", "trailing_reports", "gate_report"}
tree = ast.parse((ROOT / "empryo/bin/emp-hub").read_text())
namespace = {"VERDICT_LINE": re.compile(r"VERDICT: (PASS|FAIL)")}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)
                             and n.name in NAMES], type_ignores=[]), "gate-definitions", "exec"), namespace)


def evaluate(items, run, sha=None):
    namespace["read_items"] = lambda thread: items
    message, problem = namespace["gate_report"](
        {"runs": [run]}, lambda text: namespace["judge_review"](text, sha)[0])
    if message is None:
        return False, problem
    return namespace["judge_review"](message["text"], sha)


def main():
    for filename in sys.argv[1:]:
        data = json.loads(Path(filename).read_text())
        assert not data["hasMore"], "activity capture must be complete"
        run = data["recentRuns"][0]
        assert run["ordinal"] == 1, "capture must include the original run (increase runLimit)"
        items = [i for i in data["items"] if i["createdAt"] <= run["completedAt"]]
        sha = "628bd504077dae985466f696bdf7408136c6d9b4" if "SRW-790" in data["thread"]["title"] else None
        result = evaluate(items, run, sha)
        print(f"{data['thread']['threadId']} original run: {result}", flush=True)
        assert result[0], result

    run = {"status": "completed", "startedAt": "2026-01-02T00:00:00Z"}
    sha = "a" * 40

    def item(kind, text="", when="2026-01-02T00:00:01Z"):
        return {"type": kind, "text": text, "createdAt": when}

    start = item("user_message", "Review")
    passed = item("assistant_message", f"CHECK: PASS {sha}\nVERDICT: PASS")
    tool = item("dynamic_tool")
    finished = item("run_finished")
    cases = [
        ("tool after PASS", [start, passed, tool, finished], sha, True),
        ("progress before final report", [start, item("assistant_message", "Working"), tool, passed, tool, finished], sha, True),
        ("last message lacks verdict", [start, passed, tool, item("assistant_message", "Not a verdict"), tool, finished], sha, False),
        ("FAIL", [start, passed, tool, item("assistant_message", "VERDICT: FAIL"), tool, finished], None, False),
        ("wrong CHECK SHA", [start, passed, tool, finished], "b" * 40, False),
        ("missing CHECK", [start, item("assistant_message", "VERDICT: PASS"), tool, finished], sha, False),
        ("text after verdict", [start, item("assistant_message", "VERDICT: PASS\nStill working"), tool, finished], None, False),
        ("disagreeing adjacent reports", [start, passed, item("assistant_message", "VERDICT: FAIL"), tool, finished], None, False),
        ("latest run has no report", [item("assistant_message", "VERDICT: PASS", "2026-01-01T00:00:00Z"), tool, finished], None, False),
        ("user after report", [start, passed, item("user_message", "Review again"), tool, finished], sha, False),
    ]
    for label, items, check_sha, expected in cases:
        result = evaluate(items, run, check_sha)
        print(f"{label}: {'PASS' if result[0] else 'REFUSED'} ({result[1]})", flush=True)
        assert result[0] == expected, label
    result = evaluate([start, passed], {**run, "status": "running"}, sha)
    assert not result[0], "unfinished run"
    print("unfinished run: REFUSED", flush=True)


if __name__ == "__main__":
    main()
