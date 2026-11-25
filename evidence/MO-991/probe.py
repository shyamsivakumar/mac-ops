"""Fake-driven table for MO-991: gate brief and cmd_close per body line, left section and size."""
import argparse, importlib.machinery, importlib.util, itertools, json, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[2] / "coordinator" / "bin"
sys.path.insert(0, str(BIN))
os.environ["COORD_JOURNAL_DIR"] = tempfile.mkdtemp(prefix="probe-journal-")
os.environ["COORDQ_DIR"] = tempfile.mkdtemp(prefix="probe-queue-")
DECISIONS = os.path.join(tempfile.mkdtemp(prefix="probe-dec-"), "decisions.json")
os.environ["COORDINATOR_DECISIONS"] = DECISIONS
Path(DECISIONS).write_text('{"items": []}')


def load(name):
    loader = importlib.machinery.SourceFileLoader("probe_" + name, str(BIN / name))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


ticket, coordq = load("ticket"), load("coordq")
import gate_policy

HEAD = "a" * 40
REPOS = {"lane": "shyamsivakumar/mac-ops", "reviewer": "shyamsivakumar/zzz-fixture"}


def body(line, left):
    text = "Refs #7\n\nBuilder check: PASS " + HEAD + "\n"
    text += "Partial: yes\n" if line == "present" else "```\nPartial: yes\n```\n" if line == "fenced" else ""
    if left == "listed":
        text += "\n## Left for later\n\n- the second half\n"
    elif left == "empty":
        text += "\n## Left for later\n\n"
    return text


def gate_row(line, left, size, mode):
    pr = {"body": body(line, left)}
    with patch.object(coordq, "pr_size", lambda *a: {"lines": size}):
        partial = coordq.partial_head(REPOS[mode], 8, pr)
    brief = gate_policy.build_gate_brief({"key": "MO"}, REPOS[mode], 7, 8, HEAD, False, partial=partial)
    return partial, "no finding" in brief, "gh issue close" in brief


class Calls:
    def __init__(self, line, left):
        self.pull = {"state": "MERGED", "headRefOid": HEAD, "body": body(line, left), "mergeCommit": {"oid": "m" * 40}}
        self.issue = {"state": "OPEN", "labels": [{"name": "stage:started"}], "comments": []}
        self.log = []

    def gh_json(self, args, **kw):
        return self.pull if args[0] == "pr" else self.issue

    def gh(self, args, **kw):
        self.log.append(args[:2])
        if args[:2] == ["issue", "comment"]:
            self.issue["comments"].append({"body": args[args.index("--body") + 1]})
        if args[:2] == ["issue", "edit"]:
            self.issue["labels"] = [{"name": "stage:backlog"}]
        return ""


def close_row(line, left, repeat=1):
    calls = Calls(line, left)
    reply = f"PROVIDES: PASS {HEAD}\nCHECK: PASS {HEAD}\nVERDICT: PASS"
    fake_check = type("C", (), {"run_check": staticmethod(lambda *a: {"items": []}),
                                "blocking": staticmethod(lambda items: [])})
    args = argparse.Namespace(ref="shyamsivakumar/mac-ops#7", pr=8, head=HEAD, gate_thread="g")
    with patch.object(ticket, "gh_json", calls.gh_json), patch.object(ticket, "gh", calls.gh), \
         patch.object(ticket, "t3_call", lambda *a: {"items": [{"type": "assistant_message", "text": reply}]}), \
         patch.object(ticket, "close_check_module", lambda: fake_check), \
         patch.object(ticket.journal, "emit", lambda *a, **k: calls.log.append(["journal", a[0]])):
        for _ in range(repeat):
            ticket.cmd_close(args)
    kinds = [" ".join(entry) for entry in calls.log]
    return kinds.count("issue close"), kinds.count("issue comment"), kinds.count("issue edit"), kinds.count("journal partial_merged")


print("gate brief: line, left, size, mode -> partial (None no marker, False marker only, True valid claim), partial text, gh issue close in brief")
for line, left, size, mode in itertools.product(("present", "absent", "fenced"), ("listed", "empty", "none"), (199, 200, 300, 301), ("lane", "reviewer")):
    if line != "present" and left != "listed" or (line == "absent" and size != 200):
        continue
    partial, text, closes = gate_row(line, left, size, mode)
    print(f"{line:8} {left:7} {size:3} {mode:8} -> partial={partial!s:5} partial_text={text!s:5} issue_close={closes}")

print("cmd_close: line, left -> issue close, comment, label edit, journal partial_merged (calls)")
for line, left in (("present", "listed"), ("present", "empty"), ("present", "none"), ("fenced", "listed"), ("absent", "none")):
    print(f"{line:8} {left:7} -> {close_row(line, left)}")
print("repeated cmd_close x3 (present, listed) ->", close_row("present", "listed", 3))
calls = Calls("present", "listed")
calls.issue["state"] = "CLOSED"
print("closed by a Closes keyword at merge, no record yet ->", end=" ")
with patch.object(ticket, "gh_json", calls.gh_json), patch.object(ticket, "gh", calls.gh), \
     patch.object(ticket.journal, "emit", lambda *a, **k: calls.log.append(["journal", a[0]])):
    ticket.keep_open_partial("shyamsivakumar/mac-ops", 7, 8, HEAD, "m", "x")
    ticket.keep_open_partial("shyamsivakumar/mac-ops", 7, 8, HEAD, "m", "x")
print(calls.log, "(second call recorded nothing)")
print("marker spellings ->", [gate_policy.partial_claim(t) for t in (
    "- Partial: yes.\r\n### Left for later:\r\n- x", "> **Partial: yes**\n## Left for later\nx", "Partial: yes")])
calls = Calls("present", "listed")
calls.issue["labels"] = [{"name": "stage:todo"}]
with patch.object(ticket, "gh_json", calls.gh_json), patch.object(ticket, "gh", calls.gh), patch.object(ticket.journal, "emit", lambda *a, **k: None):
    ticket.keep_open_partial("shyamsivakumar/mac-ops", 7, 8, HEAD, "m", "x")
print("stage:todo ticket ->", calls.log, calls.issue["labels"])
print("decisions items on the board:", [i["id"] for i in json.load(open(DECISIONS))["items"]])
