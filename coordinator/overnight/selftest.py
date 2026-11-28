import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import runpy
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def panel_source():
    """Return the coordinator panel's source.

    The check runs in the checkout and in the installed layout, where the
    panel lives beside the other Herdr files and not in the checkout."""
    for candidate in (ROOT.parent / "mods" / "coordinator" / "main.js",
                      Path.home() / ".config" / "herdr-app" / "mods" / "coordinator" / "main.js"):
        if candidate.is_file():
            return candidate.read_text()
    raise AssertionError("the coordinator panel is not found")


def load_runner():
    """Return the overnight runner as a module, so an eval runs the real path."""
    path = ROOT / "overnight" if (ROOT / "overnight").is_file() else ROOT.parent / "overnight" / "overnight"
    loader = importlib.machinery.SourceFileLoader("overnight_runner", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_ticket():
    path = ROOT / "ticket" if (ROOT / "ticket").is_file() else ROOT.parent / "bin" / "ticket"
    loader = importlib.machinery.SourceFileLoader("fixture_ticket", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_coordq():
    """Return coordq as a module, so an eval runs the real dispatch path."""
    path = ROOT / "coordq" if (ROOT / "coordq").is_file() else ROOT.parent / "bin" / "coordq"
    loader = importlib.machinery.SourceFileLoader("fixture_coordq", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@contextlib.contextmanager
def fixture_models():
    """The one model list from the checkout, with no blocked provider.

    The evals forbid live files, so the list and the blocked state are read
    once here and the module answers from them."""
    seed = ROOT.parent / "models.json"
    env = {"COORDINATOR_MODELS": str(seed)} if seed.is_file() else {}
    with patch.dict(os.environ, env):
        import lane_driver as lane
        lists = lane.model_list.load()
        with patch.object(lane.model_list, "entries", side_effect=lambda name: lists[name]), \
             patch.object(lane.model_list, "blocked_identities", return_value=set()):
            yield


def fixer_identity():
    """The provider and model of a thread already on the first available fix model."""
    import lane_driver as lane
    selection = lane.model_list.first_available("fix")["selection"]
    return {"providerInstanceId": selection["instanceId"], "model": selection["model"]}


def exact(actual, expected):
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


@contextlib.contextmanager
def scratch_board(scratch):
    """Point the lane's decisions board at a scratch file.

    The lane raises one item on the decisions board when a pull request
    uses its review rounds. A test must never write the board Shyam
    reads, so the board path is a scratch file for the whole eval.
    """
    import lane_driver as lane
    board = Path(scratch) / "decisions.json"
    board.write_text(json.dumps({"items": []}))
    with patch.object(lane, "DECISIONS_PATH", str(board)):
        yield board


def start_routing():
    import lane_driver as lane
    ticket = load_ticket()
    repos = ["shyamsivakumar/mac-ops", "shyamsivakumar/strategy-replay-workbench",
             "shyamsivakumar/fantasy-football-toolkit", "shyamsivakumar/catalouge",
             "digitized/Concerning", "fixture/sixth"]
    board = json.loads(json.dumps([
        dict(repo=repo, number=n, key=f"F-{n}", stage=stage, problems=problems,
             priority=2, title="bot", type="standard", builderAlias="implementation",
             builderSelection={"model": "fixture-implementation"}, body="fixture", url="fixture")
        for repo in repos for n, stage, problems in
        [(1, "backlog", []), (2, "todo", ["blocked"]), (3, "todo", []), (4, "todo", [])]
    ]))
    board.insert(0, dict(repo=repos[1], number=468, key="SRW-468", stage="todo", problems=[], priority=1))
    actions = []

    def run(cmd, timeout=150):
        if cmd[:2] != ["ticket", "start"]:
            raise AssertionError(f"unexpected subprocess: {cmd}")
        actions.append(cmd)
        return "ready" if cmd[-1] == "--dry-run" else "launched"

    with patch.object(lane, "run", run), patch.object(lane, "DRY", False):
        for repo in repos:
            lane.start_next(repo, board, {})
    exact(actions, [cmd for repo in repos for cmd in
                    (["ticket", "start", f"{repo}#3", "--dry-run"],
                     ["ticket", "start", f"{repo}#3"])])
    cfg = {"repos": {repo: {"projectId": repo} for repo in repos}}
    with patch.object(ticket, "default_branch", return_value="main"), \
         patch.object(ticket, "brief_reviewer", return_value="astra"):
        for item in board:
            if item["number"] != 3:
                continue
            _, _, payload = ticket.build_start(cfg, item, 1, {})
            exact(payload["workspaceStrategy"], {"type": "worktree", "baseRef": "origin/main", "startFromOrigin": True})
            exact(payload["modelSelection"], {"model": "fixture-implementation"})
    for kind, label, expected in [("standard", None, "task/standard"), ("risky", None, "task/risky"),
                                  ("chore", "cursor", "default"), ("chore", "kimi", "task/standard")]:
        item = dict(board[3], type=kind, builder=label, reviewer=None)
        builder, reviewer = ticket.resolve_models(cfg, item)
        item.update(builderAlias=builder["id"], reviewerAlias=reviewer["id"], builderSelection=builder["selection"])
        commands = []
        def launch(command, timeout):
            payload = json.loads(command[2])
            exact(payload["modelSelection"]["model"], expected)
            exact(payload["workspaceStrategy"], {"type": "worktree", "baseRef": "origin/main", "startFromOrigin": True})
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "fixture receipt", "")
        from argparse import Namespace
        with contextlib.ExitStack() as stack:
            for name, value in {"load_config": cfg, "repo_config": {}, "with_ticket_lock": None,
                                "fetch_issue": {}, "validate_start": item, "authed_login": "fixture",
                                "ledger_of": [], "assert_not_active": None, "default_branch": "main",
                                "post_comment": None, "gh": ""}.items():
                stack.enter_context(patch.object(ticket, name, return_value=value))
            stack.enter_context(patch.object(ticket, "run", launch))
            ticket.cmd_start(Namespace(ref=f"{item['repo']}#{item['number']}", force_text_blockers=False,
                                       print_brief=False, dry_run=False, alongside=False))
        exact(len(commands), 1)
    # A ticket labelled before the router entry existed still starts.
    exact(ticket.builder_alias("kimi"), "router")
    exact(ticket.builder_alias("deepseek"), "router")
    exact(ticket.builder_alias("cursor"), "cursor")
    labels_cfg = {"labels": {"stage": ["todo"], "type": ["standard"], "priority": ["1"]}}
    exact(ticket.label_problems(labels_cfg, {"stage": ["todo"], "type": ["standard"],
                                             "priority": ["1"], "builder": ["kimi"], "reviewer": []}), [])
    morph = {"pi:morph-dsv41flash", "pi:morph-dsv41flash-1017"}
    for kind, walk in [("standard", ["cursor", "terra"]), ("risky", ["cursor", "sol"])]:
        blocked = set(morph)
        for expected_id in walk:
            exact(lane.model_list.first_available("build", None, blocked, kind)["id"], expected_id)
            blocked.add(lane.model_list.identity(lane.model_list.first_available("build", None, blocked, kind)["selection"]))
    exact(lane.model_list.first_available("fix")["selection"]["model"], "task/standard")
    exact(lane.model_list.entries("fix")[-1]["selection"]["options"], [{"id": "reasoningEffort", "value": "max"}])
    actions.clear()
    chains = [dict(repo=repos[1], number=n, key=f"F-{n}", stage="todo", problems=[],
                   priority=1, title=title) for n, title in [(10, "bot"), (11, "census"), (12, "dashboard")]]
    with patch.object(lane, "run", run), patch.object(lane, "DRY", False):
        lane.start_next(repos[1], chains, {}, {"bot"})
    exact(actions, [["ticket", "start", f"{repos[1]}#11", "--dry-run"],
                    ["ticket", "start", f"{repos[1]}#11"]])
    actions.clear()
    snapshot = {"tickets": chains, "repos": {repos[1]: {"prs": [], "issues": []}}}
    with patch.object(lane, "watchdog"), patch.object(lane, "drift_ff"), \
         patch.object(lane, "board_snapshot", return_value=snapshot), \
         patch.object(lane, "LANE_REPOS", [repos[1]]), patch.object(lane, "ORDER", {}), \
         patch.object(lane, "CFG", {repos[1]: {"projectId": "fixture", "key": "SRW"}}), \
         patch.object(lane, "recover_dead_runs"), patch.object(lane, "settle_merged_prs"), \
         patch.object(lane, "t3", return_value={"threads": [{"title": "bot"}]}), \
         patch.object(lane, "stall_receipts", return_value={}), \
         patch.object(lane, "run", run), patch.object(lane, "DRY", False):
        lane.run_pass({})
        for invalid in ({}, {"threads": None}, {"threads": {}}, {"threads": [None]}, {"threads": [{}]}):
            actions.clear()
            with patch.object(lane, "busy", return_value="unknown"), patch.object(lane, "t3", return_value=invalid):
                lane.run_pass({})
            exact(actions, [])
        with patch.object(lane, "t3", return_value={"threads": [{"title": "bot"}]}):
            lane.run_pass({})
    exact(actions, [["ticket", "start", f"{repos[1]}#11", "--dry-run"],
                    ["ticket", "start", f"{repos[1]}#11"]])
    with patch.object(lane, "SNAPSHOT", {"repos": {repos[0]: {"issues": [{"number": 9, "labels": []}], "prs": []}}}), \
         patch("builtins.open", __import__("unittest.mock", fromlist=["mock_open"]).mock_open(read_data=json.dumps({f"ticket:{repos[0]}#9:a1": "dead"}))), \
         patch.object(lane, "t3", return_value={}), patch.object(lane, "DRY", True):
        result = lane.unstick(repos[0], {})
        exact(result, "DRY start #9")
        actions.clear()
        with patch.object(lane, "DRY", False), patch.object(lane, "run", run):
            lane.unstick(repos[0], {})
        exact(actions, [["ticket", "start", f"{repos[0]}#9"]])

    orphan_snapshot = {"tickets": [], "repos": {repos[1]: {"prs": [], "issues": [
        {"number": 9, "title": "bot repair", "labels": []}]}}}
    with patch.object(lane, "watchdog"), patch.object(lane, "drift_ff"), \
         patch.object(lane, "board_snapshot", return_value=orphan_snapshot), \
         patch.object(lane, "LANE_REPOS", [repos[1]]), patch.object(lane, "ORDER", {}), \
         patch.object(lane, "CFG", {repos[1]: {"projectId": "fixture", "key": "SRW"}}), \
         patch.object(lane, "recover_dead_runs"), patch.object(lane, "settle_merged_prs"), \
         patch.object(lane, "run", run), patch.object(lane, "DRY", False), \
         patch("builtins.open", __import__("unittest.mock", fromlist=["mock_open"]).mock_open(
             read_data=json.dumps({f"ticket:{repos[1]}#9:a1": "dead"}))):
        def threads(tool, args):
            return {"threads": [{"title": "bot"}]} if tool == "t3_thread_list" else {}
        with patch.object(lane, "t3", side_effect=threads):
            for title in ("bot repair", "", None):
                orphan_snapshot["repos"][repos[1]]["issues"][0]["title"] = title
                actions.clear()
                ledger = {}
                lane.run_pass(ledger)
                exact(actions, [])
                exact(ledger, {})
            orphan_snapshot["repos"][repos[1]]["issues"][0]["title"] = "census repair"
            actions.clear()
            lane.run_pass({})
            exact(actions, [["ticket", "start", f"{repos[1]}#9"]])

        orphan_snapshot["repos"][repos[1]]["prs"] = [{"number": 20, "isDraft": False, "body": ""}]
        orphan_snapshot["repos"][repos[1]]["issues"][0]["title"] = "bot repair"
        for after in ({"threads": [{"title": "bot"}]}, {},
                      {"threads": [{"title": "bot"}, {"title": "census"}, {"title": "dashboard"}]}):
            events = []
            def pr_action(repo, number, ledger):
                events.append("pr-launch")
                return "gate launched"
            def post_action_threads(tool, args):
                events.append("refresh" if tool == "t3_thread_list" else "read")
                return after if tool == "t3_thread_list" else {}
            actions.clear()
            ledger = {}
            with patch.object(lane, "busy", return_value=""), \
                 patch.object(lane, "act_on_pr", side_effect=pr_action), \
                 patch.object(lane, "t3", side_effect=post_action_threads):
                lane.run_pass(ledger)
            exact(events, ["pr-launch", "refresh"])
            exact(actions, [])
            exact(ledger, {})


def pr_reads(lane, row):
    lane.PASS_PRS.clear()
    return lambda command, **_: [row] if command[:3] == ["gh", "pr", "list"] else row


def dead_run_recovery():
    import lane_driver as lane
    repo = "shyamsivakumar/mac-ops"
    dead = {"threadId": "fixture-dead", "title": "review #7", "settled": False}
    thread = {**dead, "providerInstanceId": "claudeAgent", "model": "claude-opus-5-5",
              "worktreePath": "/tmp/fixture-worktree", "pullRequests": []}
    launches, settled = [], []

    def t3(tool, args):
        if tool == "t3_thread_list":
            return {"threads": [dead]} if args.get("statuses") == ["failed", "interrupted"] else {"threads": []}
        if tool == "t3_thread_read" and args.get("view") == "messages":
            return {"items": [{"type": "assistant_message", "text": "provider individual spend limit"}]}
        if tool == "t3_thread_read":
            return {"thread": thread}
        if tool == "t3_thread_organize":
            settled.append(args["threadId"])
            return {}
        raise AssertionError(f"unexpected T3 call {tool}")

    def run(cmd):
        if cmd[0] == "git":
            exact(cmd, ["git", "-C", "/Users/shyamsivakumar/Code/" + lane.PATHS[repo],
                        "worktree", "list", "--porcelain"])
            return "worktree /tmp/fixture-worktree\n"
        launches.append(json.loads(cmd[2]))
        return "fixture-relaunch"

    with patch.object(lane, "LANE_REPOS", [repo]), \
         patch.object(lane, "CFG", {repo: {"projectId": "fixture-project"}}), \
         patch.object(lane, "DRY", False), patch.object(lane, "t3", side_effect=t3), \
         patch.object(lane, "last_reply", return_value="provider individual spend limit"), \
         patch.object(lane, "stall_receipts", return_value={f"ticket:{repo}#7:a1": "fixture-dead"}), \
         patch.object(lane, "read_json", return_value={"state": "OPEN"}), patch.object(lane, "run", side_effect=run):
        ledger = {}
        lane.recover_dead_runs(ledger)
        lane.recover_dead_runs(ledger)
    exact(len(launches), 1)
    exact(launches[0]["modelSelection"], lane.model_list.first_available("build")["selection"])
    exact(launches[0]["workspaceStrategy"], {"type": "existing_worktree", "worktreePath": "/tmp/fixture-worktree"})
    exact(ledger[f"dead-relaunch-thread:fixture-dead"], "fixture-relaunch")
    exact(settled, ["fixture-dead", "fixture-dead"])
    dead_run_no_receipt()


def dead_run_no_receipt():
    import lane_driver as lane
    repo = "shyamsivakumar/mac-ops"
    catalog = "shyamsivakumar/catalouge"
    threads = [
        {"threadId": "fixture-merged", "title": "ship #11", "settled": False},
        {"threadId": "fixture-open", "title": "review #12", "settled": False,
         "pullRequests": [{"repository": repo, "number": 13}]},
        {"threadId": "fixture-key", "title": "CTL-7 hand launch", "settled": False},
        {"threadId": "fixture-nothing", "title": "hand launch", "settled": False},
        {"threadId": "fixture-closed-key", "title": "MO-8 hand launch", "settled": False},
        {"threadId": "fixture-landed-key", "title": "MO-9 hand launch", "settled": False},
        {"threadId": "fixture-full", "title": "MO-10 hand launch", "settled": False}]
    states = {
        (repo, 11): {"kind": "pr", "state": "closed", "merged": True},
        (repo, 12): {"kind": "pr", "state": "open", "merged": False},
        (repo, 13): {"kind": "pr", "state": "open", "merged": False},
        (catalog, 7): {"kind": "issue", "state": "closed", "merged": False},
        (repo, 8): {"kind": "issue", "state": "closed", "merged": False},
        (repo, 9): {"kind": "issue", "state": "open", "merged": False},
        (repo, 10): {"kind": "issue", "state": "closed", "merged": False}}
    # A closed issue can close before its pull request lands, and a merged
    # pull request reports MERGED, not CLOSED.
    linked = {(catalog, 7): [{"number": 8, "state": "OPEN", "mergedAt": None}],
              (repo, 8): [{"number": 15, "state": "CLOSED", "mergedAt": None}],
              (repo, 9): [{"number": 16, "state": "MERGED", "mergedAt": "2026-11-17T00:00:00Z"}]}
    reads, settled = [], []

    def reference(target, number):
        reads.append((target, number))
        return states.get((target, number))

    def ticket_prs(target, number):
        reads.append((target, number))
        return linked.get((target, number), []), (target, number) == (repo, 10)

    def ticket_numbers(target, token):
        return {"CTL-7": [7], "MO-8": [8], "MO-9": [9], "MO-10": [10]}.get(token, [])

    def t3(tool, args):
        if tool == "t3_thread_list":
            return {"threads": threads} if args.get("statuses") == ["failed", "interrupted"] else {"threads": []}
        if tool == "t3_thread_organize":
            settled.append(args["threadId"])
            return {}
        raise AssertionError(f"unexpected T3 call {tool}")

    ledger = {}
    with patch.object(lane, "LANE_REPOS", [repo]), \
         patch.object(lane, "CFG", {repo: {"projectId": "fixture", "key": "MO"},
                                    catalog: {"projectId": "fixture-key", "key": "CTL"}}), \
         patch.object(lane, "DRY", False), patch.object(lane, "t3", side_effect=t3), \
         patch.object(lane, "stall_receipts", return_value={}), \
         patch.object(lane, "dead_reference", side_effect=reference), \
         patch.object(lane, "dead_ticket_prs", side_effect=ticket_prs), \
         patch.object(lane, "dead_ticket_numbers", side_effect=ticket_numbers):
        lines = io.StringIO()
        with contextlib.redirect_stdout(lines):
            lane.recover_dead_runs(ledger)
        first = [line for line in lines.getvalue().splitlines() if line]
        reads.clear()
        lines = io.StringIO()
        with contextlib.redirect_stdout(lines):
            lane.recover_dead_runs(ledger)
        second = lines.getvalue().strip()
    exact(settled, ["fixture-merged", "fixture-closed-key", "fixture-landed-key"])
    exact(second, "")
    exact(reads, [])
    exact(len(first), 7)
    exact("settle, PR shyamsivakumar/mac-ops#11 merged" in first[0], True)
    exact("flagged once" in first[1] and "PR shyamsivakumar/mac-ops#13 is open" in first[1], True)
    exact("flagged once" in first[2] and "PR shyamsivakumar/catalouge#8 is open" in first[2], True)
    exact("no pull request or ticket in the title" in first[3], True)
    exact("settle, issue shyamsivakumar/mac-ops#8 closed" in first[4], True)
    exact("settle, PR shyamsivakumar/mac-ops#16 merged" in first[5], True)
    exact("flagged once" in first[6] and "an unseen open one cannot be ruled out" in first[6], True)
    exact(ledger["dead-run:fixture-merged"].startswith("settled "), True)
    exact(ledger["dead-run:fixture-open"].startswith("flagged "), True)
    exact(ledger["dead-run:fixture-key"].startswith("flagged "), True)
    exact(ledger["dead-run:fixture-nothing"].startswith("flagged "), True)
    exact(ledger["dead-run:fixture-closed-key"].startswith("settled "), True)
    exact(ledger["dead-run:fixture-landed-key"].startswith("settled "), True)
    exact(ledger["dead-run:fixture-full"].startswith("flagged "), True)


_REAL_OPEN = open
LIVE_STATE = ("queue", "decisions.json", "dispatch-receipts", "lanes-ledger",
              "loop/", ".coordinator/tickets.json")


def live_state_only(path, *args, **kwargs):
    """Open a file unless it is coordinator state this eval must not touch.

    The lane legitimately reads model lists and the gateway's own files now, so
    the ban is narrowed to the live state: the queue, the decisions board, the
    receipts, the ledger and the tickets config.
    """
    name = str(path)
    mode = args[0] if args else kwargs.get("mode", "r")
    writing = any(flag in mode for flag in "wax+")
    if writing and any(marker in name for marker in LIVE_STATE):
        raise AssertionError(f"live filesystem forbidden (write): {name}")
    return _REAL_OPEN(path, *args, **kwargs)


def gate_pipeline():
    import lane_driver as lane
    repo = "shyamsivakumar/mac-ops"
    head = "a" * 40
    failures = []
    full = f"PROVIDES: PASS {head}\nCHECK: PASS {head}\nVERDICT: PASS"
    cases = [
        ("checked-head", repo, "absent", "", {}, [], None),
        ("pass", repo, "PASS", full, {}, ["merge", "provides", "ff"], "src/ticket"),
        ("prompt-pass", repo, "PASS", f"CHECK: PASS {head}\nVERDICT: PASS", {}, ["decisions"],
         "coordinator/config/AGENT-RULES.md"),
        ("fail", repo, "FAIL", "finding\nVERDICT: FAIL", {}, ["builder"], "src/ticket"),
        ("no-verdict", repo, "none", "interrupted", {}, [], None),
        ("second-no-verdict", repo, "none", "interrupted", {}, [], None),
        ("pass-then-no-verdict-attempt", repo, "none", "interrupted", {}, ["merge", "provides", "ff"], None),
        ("fail-then-no-verdict-attempt", repo, "none", "interrupted", {}, [], None),
        ("manual", "digitized/Concerning", "PASS", full, {}, [], None),
        ("ascend", "ascend/fixture", "absent", "", {}, [], None),
        ("stray-pass-ignored", repo, "absent", "", {}, [], None),
        ("earlier-fail-later-pass", repo, "PASS", full, {}, ["decisions"], None),
        ("retry-replaced-pass", repo, "PASS", full, {}, ["merge", "provides", "ff"], None),
        ("merge-timeout-but-merged", repo, "PASS", full, {}, ["merge", "provides", "ff"], None),
        ("older-running-newer-pass", repo, "PASS", full, {}, [], None),
        ("older-pass-newer-pass", repo, "PASS", full, {}, ["merge", "provides", "ff"], None),
        ("pass-without-provides", repo, "none", f"CHECK: PASS {head}\nVERDICT: PASS", {}, [], None),
        ("pass-check-wrong-head", repo, "none", f"PROVIDES: PASS {head}\nCHECK: PASS {'b' * 40}\nVERDICT: PASS", {}, [], None),
        ("no-receipts-file", repo, "absent", "", {}, [], None),
        ("retargeted-after-pass", repo, "PASS", full, {}, [], None),
        ("retargeted-regated-pass", repo, "PASS", full, {}, ["merge", "provides", "ff"], None),
        ("trailing-space-pass", repo, "PASS", full.replace(f"PROVIDES: PASS {head}", f"PROVIDES: PASS {head}  "), {}, ["merge", "provides", "ff"], None),
        ("markdown-verdict-with-trailing-sentence", repo, "PASS", full.replace("VERDICT: PASS", "**VERDICT: PASS** for PR #20. I did not land it."), {}, ["merge", "provides", "ff"], None),
        ("indented-verdict", repo, "none", full.replace("\nVERDICT", "\n  VERDICT"), {}, [], None),
        ("older-pass-not-superseded", repo, "PASS", full, {}, ["merge", "provides", "ff"], None),
        ("older-fail-superseded", repo, "FAIL", "finding\nVERDICT: FAIL", {}, [], None),
    ]
    gate_key = f"gate:{repo}#20:{head}"
    extra = {"stray-pass-ignored": {"stray": "VERDICT: PASS"},
             "earlier-fail-later-pass": {gate_key + ":old:retry": "old"},
             "retry-replaced-pass": {gate_key + ":old:retry": "old"},
             "older-running-newer-pass": {gate_key + ":old:retry": "old"},
             "older-pass-newer-pass": {gate_key + ":old:retry": "old"},
             "pass-then-no-verdict-attempt": {gate_key + ":old:retry": "old"},
             "fail-then-no-verdict-attempt": {gate_key + ":old:retry": "old"}}
    replies = {"stray": full, "old": "dead\nVERDICT: FAIL"}
    replies_by_case = {"retry-replaced-pass": {"old": "interrupted"}, "older-pass-newer-pass": {"old": full},
                       "pass-then-no-verdict-attempt": {"old": full}}
    live_by_case = {"older-running-newer-pass": {"old"}}
    for name, target, verdict, reply, ledger, expected, changed in cases:
        actions = []
        receipts = {} if verdict == "absent" else {f"gate:{target}#20:{head}": "gate", "base:gate": "other" if name == "retargeted-regated-pass" else "main"}
        receipts.update(extra.get(name, {}))
        receipts.update({f"base:{v}": "main" for k, v in extra.get(name, {}).items() if k.startswith("gate:")})
        thread_replies = {**replies, **replies_by_case.get(name, {}), "gate": reply}
        pr = dict(number=20, state="OPEN", headRefOid=head, changedFiles=1,
                  body=f"Refs #10\nBuilder check: PASS {head}", mergeable="MERGEABLE")
        newer = [dict(number=21, state="OPEN", body="Refs #10")] if name.startswith("older-") and "superseded" in name else []
        snapshot = {"repos": {target: {"prs": [pr, *newer], "issues": [dict(number=10, labels=[])]}}}

        def command(cmd, timeout=150, target=target, changed=changed, actions=actions,
                    head=head, reply=reply, verdict=verdict, name=name):
            if cmd == ["gh", "pr", "view", "20", "-R", target, "--json", "baseRefName,headRefOid"]:
                # The pre-merge guard: the base and head the review was taken
                # against, read in one call immediately before the merge.
                return json.dumps({"baseRefName": "other" if name == "retargeted-regated-pass" else "main", "headRefOid": head})
            if cmd == ["gh", "pr", "view", "20", "-R", target, "--json", "baseRefName"]:
                # The post-merge guard: a merged pull request cannot be
                # retargeted, so this base is the one the merge landed on.
                return json.dumps({"baseRefName": "other" if name == "retargeted-regated-pass" else "main"})
            if cmd[:2] == ["gh", "api"]:
                # The changed paths of the pull request: the case decides
                # whether they carry one prompt path or only code. The lane
                # reads the pinned merge base and head trees first, so that a
                # file list read by pull-request number never decides a merge;
                # the slurped list is still served for a caller without a pin.
                endpoint = cmd[-1]
                path = changed or "a.py"
                if "/files?per_page=100" in endpoint:
                    exact(cmd[3], "--slurp")
                    return json.dumps([[{"filename": changed}]] if changed else [[]])
                if "/compare/" in endpoint:
                    return json.dumps({"merge_base_commit": {"sha": "base"}})
                if endpoint.endswith("/git/trees/base?recursive=1"):
                    return json.dumps({"tree": [{"type": "blob", "path": path, "sha": "1"}]})
                if endpoint.endswith("/git/trees/%s?recursive=1" % head):
                    return json.dumps({"tree": [{"type": "blob", "path": path, "sha": "2"}]})
                raise AssertionError(f"unexpected gh api read: {cmd}")
            if cmd == [lane.COORDQ, "list"]:
                return ""
            if cmd[:2] == ["ticket", "gate"]:
                if "--print-model" in cmd:
                    return json.dumps(lane.model_list.reviewers(["morph/morph-kimik31"]))
                return f"Gate exact head {head}"
            if cmd[:2] == ["ticket", "close"]:
                actions.append("provides")
                return "closed"
            if cmd == ["gh", "pr", "view", "20", "-R", target, "--json", "state"]:
                return json.dumps({"state": "MERGED"})
            if cmd[:3] == ["gh", "pr", "merge"]:
                exact(cmd[cmd.index("--match-head-commit") + 1], head)
                actions.append("merge")
                if name == "merge-timeout-but-merged":
                    raise subprocess.TimeoutExpired(cmd, 150)
                return "merged"
            if cmd[0] == "git" and "worktree" in cmd:
                return "worktree /fixture/main\0HEAD fixture\0branch refs/heads/main\0\0"
            if cmd[0] == "git" and "symbolic-ref" in cmd:
                exact(cmd[2], "/fixture/main")
                return "refs/heads/main"
            if cmd[0] == "git" and "--ff-only" in cmd:
                actions.append("ff")
                return "updated"
            if cmd[:2] == [lane.COORDQ, "start"]:
                payload = json.loads(cmd[2])
                if "threadId" in payload:
                    exact(payload["threadId"], "live-builder")
                    if reply not in payload["message"]:
                        raise AssertionError("builder did not receive findings")
                    actions.append("builder")
                else:
                    exact(head in payload["message"], True)
                    actions.append(payload["modelSelection"]["instanceId"])
                return "fixture-receipt"
            raise AssertionError(f"unexpected command: {cmd}")

        def threads(tool, args, thread_replies=thread_replies, name=name):
            live = live_by_case.get(name, ())
            if tool == "t3_thread_read":
                if args["threadId"] == "live-builder":
                    return {"thread": {**fixer_identity(), "status": "running", "sendable": True}}
                return {"thread": {"status": "running" if args["threadId"] in live else "completed"},
                        "items": [{"type": "assistant_message", "text": thread_replies[args["threadId"]]}]}
            raise AssertionError(f"unexpected T3 tool: {tool}")

        def decision(item, actions=actions):
            # The board write is the one live file this eval must not touch.
            exact(item["id"] in ("prompt-merge-FIX-20", "lane-gate-split-FIX-20"), True)
            exact(item["group"], "Coordinator")
            exact(item["kind"], "action")
            exact(item.get("options"), None)
            actions.append("decisions")
            return "wrote"

        try:
            with tempfile.TemporaryDirectory() as scratch, \
                 scratch_board(scratch), \
                 patch.object(lane, "RECEIPTS", str(Path(scratch) / "receipts.json")), \
                 patch.object(lane, "CFG", {target: dict(key="FIX", projectId="fixture")}), \
                 patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "DRY", False), \
                 patch.object(lane, "builder_thread", return_value=("10", "live-builder")), \
                 patch.object(lane, "publish_decision", decision), \
                 patch.object(lane, "read_json", side_effect=pr_reads(lane, dict(number=20, state="OPEN", headRefName="builder/fixture",
                                                baseRefName="other" if name.startswith("retargeted") else "main"))), \
                 patch.object(lane, "run", command), patch.object(lane, "t3", threads), \
                 patch("builtins.open", side_effect=live_state_only):
                if name != "no-receipts-file":
                    Path(scratch, "receipts.json").write_text(json.dumps(receipts))
                lane.act_on_pr(target, 20, dict(ledger))
            exact(actions, expected)
            try:
                exact(actions + ["forbidden-action"], expected)
            except AssertionError:
                pass
            else:
                raise AssertionError("negative control accepted extra action")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
    if failures:
        raise AssertionError("; ".join(failures))
    completion_boundary()
    main_update_boundary()
    gatekeep_retarget()
    overnight_act()


def merged_restart():
    import lane_driver as lane
    head = "a" * 40
    now = time.time()

    def days_ago(days):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - days * 86400))

    merged = [dict(number=20, headRefOid=head, body="Refs #10", mergedAt=days_ago(2), baseRefName="main"),
              dict(number=21, headRefOid="b" * 40, body="Refs #10", mergedAt=days_ago(4), baseRefName="main")]
    gate_key = {f"gate:shyamsivakumar/mac-ops#20:{head}": "gate", "base:gate": "main"}
    passing = f"PROVIDES: PASS {head}\nCHECK: PASS {head}\nVERDICT: PASS"
    for repo, key, receipts, reply, expected, board in [
        ("shyamsivakumar/mac-ops", "MO", gate_key, passing, ["provides", "ff"], None),
        ("shyamsivakumar/mac-ops", "MO", gate_key, passing, ["provides"], "close-failed"),
        ("shyamsivakumar/mac-ops", "MO", gate_key, passing, ["provides", "ff"], "ff-failed"),
        ("shyamsivakumar/mac-ops", "MO", gate_key, "", [], "running"),
        ("shyamsivakumar/mac-ops", "MO", {}, "", [], "owner"),
        ("shyamsivakumar/strategy-replay-workbench", "SRW", {}, "", [], "decisions"),
    ]:
        actions = []
        searches = []
        checklist = {"items": [
            dict(item="scope", status="pass", detail="every file is named"),
            dict(item="proof file", status="skipped", detail="there is no proof file to read"),
            dict(item="cost note", status="skipped", required=False, detail="the report does not exist yet"),
            dict(item="checks", status="fail", detail="a check failed")]}

        def command(cmd, timeout=150, actions=actions, board=board, searches=searches):
            if cmd[:3] == ["gh", "pr", "list"]:
                exact(cmd[cmd.index("--limit") + 1], "300")
                searches.append(cmd[cmd.index("--search") + 1])
                return json.dumps(merged)
            if cmd[:2] == ["ticket", "close"]:
                exact(cmd[3:5], ["--pr", "20"])
                actions.append("provides")
                if board == "close-failed":
                    raise subprocess.CalledProcessError(1, cmd, output="refused: the close checklist failed")
                return "closed"
            if cmd[0] == "git" and "worktree" in cmd:
                return "worktree /fixture/main\0HEAD fixture\0branch refs/heads/main\0\0"
            if cmd[0] == "git" and "symbolic-ref" in cmd:
                return "refs/heads/main"
            if cmd[0] == "git" and "--ff-only" in cmd:
                actions.append("ff")
                if board == "ff-failed":
                    raise subprocess.CalledProcessError(1, cmd, output="not a fast-forward")
                return "updated"
            raise AssertionError(f"unexpected command: {cmd}")

        def threads(tool, args, reply=reply, board=board):
            status = "running" if board == "running" else "completed"
            return {"thread": {"status": status}, "items": [{"type": "assistant_message", "text": reply}]}

        ledger = {}
        with tempfile.TemporaryDirectory() as scratch, scratch_board(scratch) as decisions, \
             patch.dict(os.environ, {"COORDINATOR_OWNER_BOARD": str(Path(scratch) / "owner.json")}), \
             patch.object(lane, "RECEIPTS", str(Path(scratch) / "receipts.json")), \
             patch.object(lane, "CFG", {repo: dict(key=key, projectId="fixture")}), \
             patch.object(lane, "SNAPSHOT", {"repos": {repo: {"issues": [dict(number=10, labels=[])]}}}), \
             patch.object(lane, "DRY", False), \
             patch.object(lane.close_check, "run_check", lambda *args, checklist=checklist: checklist), \
             patch.object(lane, "run", command), patch.object(lane, "t3", threads):
            Path(scratch, "receipts.json").write_text(json.dumps(receipts))
            for _ in range(2):
                lane.settle_merged_prs(repo, ledger)
                exact(actions, expected)
            exact(searches, [f"merged:>={days_ago(lane.SETTLE_LOOKBACK_DAYS)[:10]}"] * 2)
            item_id = f"lane-merged-unreviewed-{key}-20"
            owner_path = Path(scratch, "owner.json")
            owner = json.loads(owner_path.read_text())["items"] if owner_path.exists() else []
            exact([i["id"] for i in owner], [item_id] if board == "owner" else
                  ["lane-close-failed-MO-20"] if board == "close-failed" else [])
            exact([i["id"] for i in json.loads(decisions.read_text())["items"]],
                  [item_id] if board == "decisions" else [])
            exact(sorted(k for k in ledger if k.startswith("after-merge:")),
                  [] if board == "running" else [f"after-merge:{repo}#20:{head}"])
            if board == "close-failed":
                why = owner[0]["why"]
                exact("proof file: skipped - there is no proof file to read" in why, True)
                exact("checks: fail - a check failed" in why, True)
                exact("scope: pass" in why or "cost note" in why, False)
            if board == "owner":
                exact("no gate attempt for this head has a recorded base" in owner[0]["why"], True)
                exact("(ticket MO-10)" in owner[0]["title"], True)
            if board == "ff-failed":
                exact(ledger[f"after-merge:{repo}#20:{head}"], "closed")


def merge_pass():
    import lane_driver as lane
    head = "a" * 40
    full = f"PROVIDES: PASS {head}\nCHECK: PASS {head}\nVERDICT: PASS"

    def replay(repo, reply=full, brief="lane-merges", passes=1, merge_fails=False, checkout=True,
               earlier=None, finished=True, ledger=None, live_base="main"):
        key = f"gate:{repo}#20:{head}"
        receipts = {key: "gate", "base:gate": "main", "brief:gate": brief} if brief else {}
        replies = {"gate": reply}
        for thread, text in (earlier or {}).items():
            receipts.update({f"{key}:old": thread, f"base:{thread}": "main"})
            replies[thread] = text
        actions, gh_calls = [], []

        def command(cmd, timeout=150):
            if cmd[0] == "gh":
                gh_calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "view"]:
                fields = cmd[-1]
                return json.dumps({"baseRefName,headRefOid": {"baseRefName": "main", "headRefOid": head},
                                   "state": {"state": "OPEN" if merge_fails else "MERGED"},
                                   "baseRefName": {"baseRefName": "main"}}[fields])
            if cmd[:3] == ["gh", "pr", "merge"]:
                exact(cmd[cmd.index("--match-head-commit") + 1], head)
                actions.append("merge")
                if merge_fails:
                    raise subprocess.CalledProcessError(1, cmd)
                return "merged"
            if cmd[:2] == ["ticket", "close"]:
                actions.append("close")
                return "closed"
            if cmd[0] == "git" and "worktree" in cmd:
                return "worktree /fixture/main\0HEAD fixture\0branch refs/heads/main\0\0"
            if cmd[0] == "git" and "symbolic-ref" in cmd:
                return "refs/heads/main"
            if cmd[0] == "git" and "--ff-only" in cmd:
                actions.append("ff")
                return "updated"
            raise AssertionError(f"unexpected command: {cmd}")

        def read(cmd, **_):
            gh_calls.append(cmd)
            row = dict(number=20, state="OPEN", headRefName="builder/x", baseRefName=live_base, headRefOid=head,
                       body="Refs #10", changedFiles=1)
            return [row] if cmd[:3] == ["gh", "pr", "list"] else row

        def threads(tool, args):
            return {"thread": {"status": "completed" if finished else "running"},
                    "items": [{"type": "assistant_message", "text": replies[args["threadId"]]}]}

        ledger = {} if ledger is None else ledger
        output = io.StringIO()
        lane.PASS_PRS.clear()
        with tempfile.TemporaryDirectory() as scratch, scratch_board(scratch) as board, \
             patch.dict(os.environ, {"COORDINATOR_OWNER_BOARD": str(Path(scratch) / "owner.json")}), \
             patch.object(lane, "RECEIPTS", str(Path(scratch) / "receipts.json")), \
             patch.object(lane, "CFG", {repo: dict(key="NING" if "Concerning" in repo else "TNR", projectId="fixture",
                                                   **({"merge": "manual"} if "Concerning" in repo else {}))}), \
             patch.object(lane, "PATHS", {repo: "fixture"} if checkout else {}), \
             patch.object(lane.os.path, "isdir", return_value=True), \
             patch.object(lane, "prompt_pull", return_value=lane.prompt_paths.CLEAR), \
             patch.object(lane, "DRY", False), patch.object(lane, "read_json", read), \
             patch.object(lane, "run", command), patch.object(lane, "t3", threads), \
             contextlib.redirect_stdout(output):
            Path(scratch, "receipts.json").write_text(json.dumps(receipts))
            for _ in range(passes):
                try:
                    lane.merge_pass(repo, ledger)
                except subprocess.CalledProcessError:
                    pass
            owner = Path(scratch, "owner.json")
            items = [i["id"] for path in (board, owner) if path.exists() for i in json.loads(path.read_text())["items"]]
        return actions, len(gh_calls), items, output.getvalue(), ledger

    repo = "shyamsivakumar/tunerise"
    ledger = {}
    actions, calls, items, _, ledger = replay(repo, ledger=ledger)
    exact(actions, ["merge", "close", "ff"])
    exact(items, [])
    actions, calls, _, _, _ = replay(repo, ledger=ledger)
    exact((actions, calls), ([], 0))
    exact(replay(repo, live_base="other")[0], [])
    exact(replay(repo, brief="reviewer-merges")[:3], ([], 0, []))
    seen = []
    for allowed, expected in (({"shyamsivakumar/mac-ops"}, []), (None, ["shyamsivakumar/tunerise"])):
        with patch.object(lane, "MERGE_REPOS", ["shyamsivakumar/tunerise"]), \
             patch.object(lane, "merge_pass", lambda target, ledger: seen.append(target)):
            lane.restrict_merge_repos(allowed)
            lane.merge_passes({})
        exact(seen, expected)
        seen.clear()
    exact(replay(repo, brief=None)[:3], ([], 0, []))
    exact(replay(repo, finished=False)[:3], ([], 0, []))
    exact(replay(repo, reply="interrupted")[:3], ([], 0, []))
    actions, calls, items, _, _ = replay("digitized/Concerning")
    exact((actions, items), ([], ["manual-merge-NING-20"]))
    actions, calls, items, _, _ = replay(repo, earlier={"old": "dead\nVERDICT: FAIL"})
    exact((actions, calls, items), ([], 0, ["lane-gate-split-TNR-20"]))
    actions, _, _, shown, _ = replay(repo, checkout=False)
    exact(actions, ["merge", "close"])
    exact("no local checkout for " + repo in shown, True)
    for passes, expected in ((lane.MERGE_WAIT_PASSES - 1, []), (lane.MERGE_WAIT_PASSES, ["merge-pass-stuck-TNR-20"])):
        actions, _, items, _, _ = replay(repo, merge_fails=True, passes=passes)
        exact((actions, items), (["merge"] * passes, expected))


def main_update_boundary():
    import lane_driver as lane
    repo = "shyamsivakumar/mac-ops"
    canonical = "/Users/shyamsivakumar/Code/mac-ops"
    feature = f"worktree {canonical}\0HEAD old\0branch refs/heads/feature\0\0"
    main = "worktree /fixture/main worktree\0HEAD old\0branch refs/heads/main\0\0"
    listing_cmd = ["git", "-C", canonical, "worktree", "list", "--porcelain", "-z"]
    verify_cmd = ["git", "-C", "/fixture/main worktree", "symbolic-ref", "--quiet", "HEAD"]
    pull_cmd = ["git", "-C", "/fixture/main worktree", "pull", "--ff-only", "origin", "main"]
    fetch_cmd = ["git", "-C", canonical, "fetch", "origin", "main:main"]
    for listing, branch, expected, refused in [
        (feature + main, "refs/heads/main", [listing_cmd, verify_cmd, pull_cmd], False),
        (feature, "", [listing_cmd, fetch_cmd], False),
        (feature + main, "refs/heads/feature", [listing_cmd, verify_cmd], True),
        ("", "", [listing_cmd], True),
    ]:
        commands = []
        def command(cmd, timeout=150):
            commands.append(cmd)
            if cmd == listing_cmd:
                return listing
            if cmd == verify_cmd:
                return branch
            if cmd not in (pull_cmd, fetch_cmd):
                raise AssertionError(f"unexpected main update command: {cmd}")
            return "updated"
        with patch.object(lane, "run", command):
            try:
                lane.fast_forward_main(repo)
            except RuntimeError:
                exact(refused, True)
            else:
                exact(refused, False)
        exact(commands, expected)


def completion_boundary():
    from argparse import Namespace
    ticket = load_ticket()
    head = "a" * 40
    proof = f"PROVIDES: PASS {head}\nCHECK: PASS {head}\nVERDICT: PASS"
    bare = f"CHECK: PASS {head}\nVERDICT: PASS"
    # Replay of mac-ops#632, whose ticket has no Provides section. The brief now
    # always asks for the PROVIDES line and says a ticket with no claims passes
    # that check trivially, so the reply it prescribes is a complete PASS. Every
    # brief mode asks for the line, so no reviewer can return a PASS without it.
    briefs = {
        "lane": ticket.gate_brief("shyamsivakumar/mac-ops", {"key": "FIX"}, 10, 20, head, "main", False, False),
        "manual": ticket.gate_brief("shyamsivakumar/mac-ops", {"key": "FIX", "merge": "manual"}, 10, 20, head, "main", False, False),
        "prompt": ticket.gate_brief("shyamsivakumar/mac-ops", {"key": "FIX"}, 10, 20, head, "main", False, False, prompt=True),
        "ascend": ticket.gate_brief("ascend/fixture", {"key": "FIX"}, 10, 20, head, "main", False, True),
        "reviewer": ticket.gate_brief("shyamsivakumar/fixture", {"key": "FIX"}, 10, 20, head, "main", False, False),
    }
    for brief in briefs.values():
        exact(f"`PROVIDES: PASS {head}`" in brief, True)
        exact("no Provides section has no claims, so it passes this check trivially" in brief, True)
        exact("A PASS reply without the PROVIDES line is read as no verdict." in brief, True)
    merged = dict(state="MERGED", headRefOid=head, body="Refs #10", mergeCommit={"oid": "b" * 40})
    # The bare reply is refused on a code pull request: `prompt_cases` below
    # covers it with prompt "clear", so a reply missing PROVIDES on a ticket
    # that does have claims is still no verdict.
    cases = [(merged, proof, True), (dict(merged, state="OPEN"), proof, False),
             (dict(merged, headRefOid="c" * 40), proof, False),
             (dict(merged, body="Refs #11"), proof, False),
             (dict(merged, mergeCommit=None), proof, False),
             (merged, proof.replace("PROVIDES: PASS", "PROVIDES: FAIL"), False),
             (merged, proof.replace("CHECK: PASS", "CHECK: FAIL"), False),
             (merged, proof.replace("VERDICT: PASS", "VERDICT: FAIL"), False)]
    prompt_cases = [(bare, "hold", True), (bare, "clear", False), (bare, "unknown", False)]
    for pull, reply, allowed, prompt in ([(*case, "clear") for case in cases]
                                         + [(merged, r, a, s) for r, s, a in prompt_cases]):
        actions = []
        args = Namespace(ref="shyamsivakumar/mac-ops#10", pr=20, head=head, gate_thread="gate")
        def close(cmd):
            exact(cmd[:3], ["issue", "close", "10"])
            actions.append("close")
            return "closed"

        class Checklist:
            """The close checklist the close step now runs, stubbed to pass."""
            def run_check(self, *args, **kwargs):
                return {"items": [{"item": "proof file", "status": "pass", "detail": "fixture"}]}
            def failures(self, items):
                return []
            def blocking(self, items):
                return []
            def report(self, items, target=""):
                return "fixture"

        with patch.object(ticket, "gh_json", return_value=pull), \
             patch.object(ticket, "t3_call", return_value={"items": [dict(type="assistant_message", text=reply)]}), \
             patch.object(ticket, "close_check_module", return_value=Checklist()), \
             patch.object(ticket, "prompt_pull", return_value=prompt), \
             patch.object(ticket, "gh", side_effect=close):
            try:
                ticket.cmd_close(args)
            except ticket.Refuse:
                exact(allowed, False)
            else:
                exact(allowed, True)
        exact(actions, ["close"] if allowed else [])


def no_parking(status="interrupted"):
    import lane_driver as lane
    repo = "shyamsivakumar/mac-ops"
    head = "a" * 40
    # Earlier lane work on this pull request that was not a review round:
    # the lane nudged the builder twice and the builder answered. A fix
    # round would be a review round, and two of those are the reviews
    # the convergence rule leaves for this pull request, so the capped
    # case is asserted in the gate-round-cap eval and not here.
    ledger = {f"continue:{repo}#20:old1": "sent", f"continue:{repo}#20:old2": "sent"}
    snapshot = {"repos": {repo: {"prs": [dict(number=20, state="OPEN", headRefOid=head,
        body=f"Builder check: PASS {head}", mergeable="MERGEABLE")],
        "issues": [dict(number=10, labels=[])]}}}
    actions = []

    def command(cmd, timeout=150):
        if cmd == [lane.COORDQ, "list"]:
            return ""
        exact(cmd[0:2], [lane.COORDQ, "start"])
        exact(cmd[3:5], ["--tool", "t3_thread_send"])
        payload = json.loads(cmd[2])
        exact(payload["threadId"], "builder")
        actions.append("continue" if payload["message"].startswith("Continue") else "fix")
        return "sent"

    with tempfile.TemporaryDirectory() as scratch, \
         scratch_board(scratch), \
         patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "DRY", False), \
         patch.object(lane, "CFG", {repo: {"key": "MO"}}), \
         patch.object(lane, "builder_thread", return_value=("10", "builder")), \
         patch.object(lane, "gate_verdict", return_value=("FAIL", None, "findings")), \
         patch.object(lane, "read_json", side_effect=pr_reads(lane, dict(number=20, state="OPEN", headRefName="builder/fixture", baseRefName="main"))), \
         patch.object(lane, "run", command), \
         patch.object(lane, "t3", return_value={"thread": {**fixer_identity(), "status": status}}), \
         patch("builtins.open", side_effect=AssertionError("live filesystem forbidden")):
        lane.act_on_pr(repo, 20, ledger)
        exact(actions, ["fix"])
        lane.act_on_pr(repo, 20, ledger)
        lane.act_on_pr(repo, 20, ledger)
        exact(actions, ["fix", "continue"])
        snapshot["repos"][repo]["prs"][0].update(headRefOid="b" * 40, body=f"Builder check: PASS {'b' * 40}")
        lane.act_on_pr(repo, 20, ledger)
        lane.act_on_pr(repo, 20, ledger)
        lane.act_on_pr(repo, 20, ledger)
        exact(actions, ["fix", "continue", "fix", "continue"])
        exact(sorted(ledger), sorted([f"continue:{repo}#20:{h}" for h in ["old1", "old2"]] +
                                    [f"fix:{repo}#20:{h}" for h in [head, "b" * 40]] +
                                    [f"continue:{repo}#20:{h}" for h in [head, "b" * 40]] +
                                    [f"rounds:{repo}#20"]))
    try:
        exact(actions + ["park"], ["fix", "continue", "fix", "continue"])
    except AssertionError:
        pass
    else:
        raise AssertionError("negative control accepted parking")


def turncap(early_interrupt=False):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import mock_open
    import turn_cap
    cap = turn_cap.load_handler()
    if early_interrupt:
        path = Path(cap.__file__)
        source = path.read_text()
        exact(source.count("age > CAP_SECONDS"), 1)
        exec(compile(source.replace("age > CAP_SECONDS", "age > 0"), str(path), "exec"), cap.__dict__)
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)

    class Clock:
        @staticmethod
        def now(tz=None):
            return now

    failures = []
    for seconds, waiting in [(600, False), (601, False), (1200, False),
                             (1201, False), (1800, True)]:
        state = dict(handled=[], wrapped={}, wrapped_at={}, finalized=[])
        thread = dict(threadId="fixture", title="ticket:fixture/repo#1:a1",
                      status="running", message="WAITING: heavy busy" if waiting else "")
        started = now - timedelta(seconds=seconds)
        actions = []
        logs = mock_open()
        def call(cli, tool, args):
            actions.append((tool, args))
            return {"delivery": "started"}
        with patch.object(cap, "datetime", Clock), \
             patch.object(cap, "current_run", return_value=("run", 1, started, started, False)), \
             patch.object(cap, "call", side_effect=call), \
             patch.object(cap, "save_state"), patch.object(cap.time, "sleep"), \
             patch.object(cap.time, "time", return_value=now.timestamp()), \
             patch("builtins.open", logs):
            cap.handle_thread("t3", thread, state, False)
            cap.handle_thread("t3", thread, state, False)

        try:
            expected = [] if waiting or seconds <= 1200 else [
                ("t3_thread_interrupt", {"threadId": "fixture", "runId": "run"})]
            exact(actions, expected)
            lines = [entry.args[0] for entry in logs().write.call_args_list]
            expected_lines = [] if waiting or seconds <= 600 else [
                f"- cap mis-sized 2026-11-15T00:00Z | t3 | {thread['title']} | run | {seconds / 60:.1f} min\n"] * 2
            if seconds > 1200 and not waiting:
                expected_lines += [
                    f"- cap hit 2026-11-15T00:00Z | t3 | {thread['title']} | run | {seconds / 60:.1f} min\n"] * 2
            exact(lines, expected_lines)
            exact(state.get("parked", []), ["fixture"] if seconds > 1200 and not waiting else [])
            exact(state.get("attempts", 0), 0)
        except AssertionError as exc:
            failures.append(f"runtime={seconds}, heavy_wait={waiting}: {exc}")
    state = dict(handled=[], wrapped={}, wrapped_at={}, finalized=[], attempts=7)
    thread = dict(threadId="paused", title="ticket:fixture/repo#2:a1", message="")
    origin = datetime(2026, 11, 15, tzinfo=timezone.utc)
    actions = []
    logs = mock_open()
    with patch.object(cap, "datetime", Clock), \
         patch.object(cap, "current_run", return_value=("paused-run", 1, origin, origin, False)), \
         patch.object(cap, "call", side_effect=lambda *args: actions.append(args)), \
         patch.object(cap, "save_state"), patch("builtins.open", logs):
        for seconds, waiting, paused, waiting_since in [
            (590, True, 0, origin.timestamp() + 590),
            (2390, True, 0, origin.timestamp() + 590),
            (2390, False, 1800, None),
            (2400, False, 1800, None),
            (2401, False, 1800, None),
            (3000, False, 1800, None),
            (3001, False, 1800, None),
            (3002, False, 1800, None),
        ]:
            now = origin + timedelta(seconds=seconds)
            thread["message"] = "WAITING: heavy busy" if waiting else ""
            cap.handle_thread("t3", thread, state, False)
            exact(state["clocks"]["paused:paused-run"],
                  {"paused": paused, "waiting_since": waiting_since})
            exact(state["attempts"], 7)
            exact(actions, [] if seconds <= 3000 else [
                ("t3mcp", "t3_thread_interrupt", {"threadId": "paused", "runId": "paused-run"})])
            exact(state.get("parked", []), [] if seconds <= 3000 else ["paused"])
            expected_lines = [] if seconds <= 2400 else [
                "- cap mis-sized 2026-11-15T00:40Z | t3 | ticket:fixture/repo#2:a1 | paused-run | 10.0 min\n"] * 2
            if seconds > 3000:
                expected_lines += [
                    "- cap hit 2026-11-15T00:50Z | t3 | ticket:fixture/repo#2:a1 | paused-run | 20.0 min\n"] * 2
            exact([c.args[0] for c in logs().write.call_args_list], expected_lines)
    if failures:
        raise AssertionError("; ".join(failures))


def hourly_selftest_fixture():
    path = ROOT / "coord-tick"
    if not path.is_file():
        path = ROOT.parent / "pi/bin/coord-tick"
    loader = importlib.machinery.SourceFileLoader("fixture_coord_tick", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    tick = importlib.util.module_from_spec(spec)
    loader.exec_module(tick)
    actions = []
    with patch.object(tick, "tick_alarm", return_value=""), \
         patch.object(tick, "child_env", return_value={}), \
         patch.object(tick.signal, "signal"), \
         patch.object(tick, "take_lock", return_value=123), \
         patch.object(tick.fcntl, "flock"), patch.object(tick.os, "close"), \
         patch.object(tick, "log"), \
         patch.object(tick, "tick_selftest", side_effect=lambda: actions.append("selftest") or "PASS"), \
         patch.object(tick, "model_available", side_effect=lambda env: actions.append("model") or False), \
         patch.object(tick, "run_tick", side_effect=AssertionError("live tick forbidden")):
        exact(tick.main(), 75)
        exact(actions, ["selftest", "model"])
    import tempfile
    import hourly_selftest as adapter
    from types import SimpleNamespace
    # The expected names come from the suite, not from the adapter, so the
    # fixture cannot agree with a wrong adapter.
    exact(sorted(adapter.EXPECTED), sorted(EVALS))
    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory) / "state.json"
        decisions = Path(directory) / "decisions.json"
        decisions.write_text(json.dumps({"items": [{"id": "unrelated"}]}))
        now = [10000]
        calls = []
        outcome = [SimpleNamespace(returncode=0, stdout="".join("PASS " + name + "\n" for name in sorted(adapter.EXPECTED)))]

        def runner(command, **options):
            exact(command, ["fixture-only"])
            exact(options, {"capture_output": True, "text": True, "timeout": 120, "check": False})
            calls.append(command)
            if isinstance(outcome[0], Exception):
                raise outcome[0]
            return outcome[0]

        def run():
            return adapter.hourly(state, decisions, ["fixture-only"], clock=lambda: now[0], runner=runner)

        exact(run(), "PASS")
        exact(json.loads(state.read_text()), {"last_run": 10000, "passed": True})
        exact(run(), "not-due")
        exact(len(calls), 1)
        now[0] += 3599
        exact(run(), "not-due")
        for failure in (SimpleNamespace(returncode=1, stdout="FAIL watchdog\n"),
                        subprocess.TimeoutExpired("fixture", 120), OSError("fixture"),
                        SimpleNamespace(returncode=0, stdout="PASS invented\n")):
            now[0] += 3600
            outcome[0] = failure
            exact(run(), "FAIL")
            exact([item["id"] for item in json.loads(decisions.read_text())["items"]],
                  ["unrelated", adapter.ALARM])
            exact(run(), "not-due")
        now[0] += 3600
        outcome[0] = SimpleNamespace(returncode=0, stdout="".join("PASS " + name + "\n" for name in sorted(adapter.EXPECTED)))
        exact(run(), "PASS")
        exact(json.loads(decisions.read_text())["items"], [{"id": "unrelated"}])
        with patch.object(adapter, "hourly", return_value="PASS"):
            outcome[0] = SimpleNamespace(returncode=1, stdout="FAIL watchdog\n")
            now[0] += 3600
            try:
                exact(run(), "FAIL")
            except AssertionError:
                pass
            else:
                raise AssertionError("negative control accepted unconditional PASS")
    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory) / "state.json"
        decisions = Path(directory) / "decisions.json"
        decisions.write_text(json.dumps({"items": [{"id": "old"}]}))

        def raising_runner(command, **options):
            decisions.write_text(json.dumps({"items": [{"id": "old"}, {"id": "new"}]}))
            return SimpleNamespace(returncode=1, stdout="")

        exact(adapter.hourly(state, decisions, ["x"], clock=lambda: 1, runner=raising_runner), "FAIL")
        exact([item["id"] for item in json.loads(decisions.read_text())["items"]], ["old", "new", adapter.ALARM])
        exact(json.loads(state.read_text()), {"last_run": 1, "passed": False})
        decisions.write_text("{broken")
        exact(adapter.hourly(state, decisions, ["x"], clock=lambda: 9999, runner=lambda *a, **k: SimpleNamespace(returncode=1, stdout="")), "FAIL")
        exact(decisions.read_text(), "{broken")
        exact(json.loads(state.read_text()), {"last_run": 9999, "passed": False, "board": "failed"})
        missing = Path(directory) / "missing.json"
        exact(adapter.hourly(state, missing, ["x"], clock=lambda: 99999, runner=lambda *a, **k: SimpleNamespace(returncode=1, stdout="")), "FAIL")
        exact([item["id"] for item in json.loads(missing.read_text())["items"]], [adapter.ALARM])
    # The adapter must run the executable beside it: a stub that prints the
    # suite's own names passes, and a missing executable fails with a reason
    # of its own.
    stub_source = ("NAMES = %s\n"
                   "for name in NAMES:\n"
                   "    print('PASS ' + name)\n" % json.dumps(sorted(EVALS)))
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        (home / "Code/coordinator").mkdir(parents=True)
        decisions = home / "Code/coordinator/decisions.json"
        decisions.write_text(json.dumps({"items": [{"id": "unrelated"}]}))
        bindir = home / "bin"
        bindir.mkdir()
        stub = bindir / "overnight"
        stub.write_text(stub_source)
        script = bindir / "hourly_selftest.py"
        script.write_text("# stand-in for the installed adapter\n")
        commands = []

        def stub_runner(command, **options):
            commands.append(command)
            exact(Path(command[1]).resolve(), stub.resolve())
            source = stub.read_text()
            exact(source, stub_source)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exec(compile(source, str(stub), "exec"), {"__name__": "__main__"})
            output = buffer.getvalue()
            exact(output, "".join("PASS " + name + "\n" for name in sorted(EVALS)))
            return subprocess.CompletedProcess(command, 0, output, "")

        with patch.object(adapter, "__file__", str(script)), \
             patch.object(Path, "home", return_value=home), \
             patch.object(adapter.subprocess, "run", stub_runner):
            exact(adapter.tick_selftest(), "PASS")
        exact(len(commands), 1)
        exact(commands[0][2], "selftest")
        exact(json.loads((home / ".local/state/mac-ops/overnight-selftest.json").read_text())["passed"], True)
        exact(json.loads(decisions.read_text()), {"items": [{"id": "unrelated"}]})
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        (home / "Code/coordinator").mkdir(parents=True)
        decisions = home / "Code/coordinator/decisions.json"
        decisions.write_text(json.dumps({"items": [{"id": "unrelated"}]}))
        bindir = home / "bin"
        bindir.mkdir()
        script = bindir / "hourly_selftest.py"
        script.write_text("# stand-in for the installed adapter\n")
        with patch.object(adapter, "__file__", str(script)), \
             patch.object(Path, "home", return_value=home), \
             patch.object(adapter.subprocess, "run",
                          side_effect=AssertionError("no process may start")):
            exact(adapter.tick_selftest(), "FAIL")
        items = json.loads(decisions.read_text())["items"]
        exact([item["id"] for item in items], ["unrelated", adapter.ALARM])
        why = items[-1]["why"]
        exact("overnight executable not found" in why, True)
        exact(why == "fixture suite failed", False)
        exact(json.loads((home / ".local/state/mac-ops/overnight-selftest.json").read_text())["passed"], False)


def watchdog():
    hourly_selftest_fixture()
    import alarms
    import lane_driver as lane
    import os
    import time
    from unittest.mock import mock_open

    limits = {"tick": 65, "gatekeep": 120, "dispatch": 10, "lanes": 10}
    labels = {"tick": "dev.coordinator.tick", "gatekeep": "dev.coordinator.gatekeep",
              "dispatch": "dev.coordinator.dispatch", "lanes": "dev.coordinator.lanes"}
    exact({name: minutes for name, (_, minutes, _) in lane.WATCH.items()}, limits)
    exact({name: label for name, (_, _, label) in lane.WATCH.items()}, labels)
    # launchd prints its status in more than one shape and every shape
    # carries the same number.
    exact(lane.exit_status("0"), 0)
    exact(lane.exit_status("78: EX_CONFIG"), 78)
    exact(lane.exit_status("(never exited)"), None)
    exact(lane.signal_status("9"), 9)
    exact(lane.signal_status("Killed: 9"), 9)
    exact(lane.signal_status(None), 0)
    now = 1000000
    other = {"id": "unrelated", "title": "preserve"}
    state = {"items": [other]}
    mtimes = {path: now for path, _, _ in lane.WATCH.values()}
    decisions = "/Users/shyamsivakumar/Code/coordinator/decisions.json"
    # The mute state lives in its own file, so the pass writes it there
    # and not to the live shift's folder.
    scratch = tempfile.mkdtemp(prefix="overnight-mute-")
    mute = str(Path(scratch) / "mute-state.json")
    # The launchd state of every job, by label. None means launchd cannot
    # run. "not-loaded" means the job is no longer held by launchd.
    # "unreadable" means launchctl failed for another reason.
    jobs = {label: {"loaded": True, "runs": 12, "exit": 0, "running": False}
            for label in labels.values()}
    elapsed = {}

    class Result:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(cmd, **kwargs):
        if cmd[0] == "launchctl":
            label = cmd[2].split("/")[-1]
            spec = jobs[label]
            if spec is None:
                raise OSError("launchctl is not available")
            if spec == "not-loaded":
                return Result(113, "", 'Could not find service "%s" in domain '
                             'for user gui: 501\n' % label)
            if spec == "unreadable":
                return Result(1, "", "Operation not permitted\n")
            body = "\tstate = running\n" if spec["running"] else "\tstate = not running\n"
            if spec.get("pid"):
                body += "\tpid = %d\n" % spec["pid"]
            body += "\truns = %d\n" % spec["runs"]
            if spec.get("exit_text") is not None:
                body += "\tlast exit code = %s\n" % spec["exit_text"]
            elif spec.get("exit") is not None:
                body += "\tlast exit code = %d\n" % spec["exit"]
            if spec.get("signal_text") is not None:
                body += "\tlast terminating signal = %s\n" % spec["signal_text"]
            elif spec.get("signal"):
                body += "\tlast terminating signal = %d\n" % spec["signal"]
            return Result(0, body)
        if cmd[0] == "ps":
            pid = int(cmd[-1])
            if pid not in elapsed:
                raise OSError("ps is not available")
            seconds = elapsed[pid]
            return Result(0, "%02d:%02d:%02d\n" % (seconds // 3600,
                                                   (seconds % 3600) // 60,
                                                   seconds % 60))
        raise AssertionError(f"unexpected subprocess: {cmd}")

    def opened(path, mode="r"):
        if mode == "w":
            # The board is replaced from a temporary file of this
            # writer's own, so two writers never share one.
            exact(str(path) in (decisions + ".tmp", f"{decisions}.{os.getpid()}.tmp"), True)
        else:
            exact(str(path), decisions)
        if mode == "r":
            return io.StringIO(json.dumps(state))
        return mock_open()()

    def saved(value, handle, **kwargs):
        state.clear()
        state.update(json.loads(json.dumps(value)))

    # The board is read and written through the alarm module, so the
    # fixture gives it the in-memory board the rest of the pass sees.
    def read_board(path):
        return b"", json.loads(json.dumps(state))

    def write_board(path, board):
        state.clear()
        state.update(json.loads(json.dumps(board)))
        return True

    def alarm(title):
        cause = title.split("Factory job stopped or failing: ", 1)[1]
        return [other, {"id": "factory-watchdog", "group": "Coordinator",
                        "kind": "action", "title": title,
                        "cause": alarms.cause_of(cause),
                        "why": "A coordinator job is stopped or failing. The coordinator is routing a fix; nothing for you unless this stays up."}]

    def pass_once():
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            lane.watchdog()
        return buffer.getvalue()

    with patch("builtins.open", side_effect=opened),          patch.object(lane, "inbox_liveness", return_value=None),          patch.object(time, "time", return_value=now),          patch.object(os.path, "getmtime", side_effect=lambda path: mtimes[path]),          patch.object(lane.json, "dump", side_effect=saved),          patch.object(os, "replace") as replace,          patch.object(lane.subprocess, "run", side_effect=fake_run),          patch.object(alarms, "MUTE_PATH", mute),          patch.object(alarms, "read_board", side_effect=read_board),          patch.object(alarms, "write_board", side_effect=write_board):
        # A quiet log is not a dead job. Every job is loaded and exits
        # clean, so the stale gatekeep log must not raise an alarm.
        stale = {path: now - 200 * 60 for path in mtimes}
        mtimes.update(stale)
        output = pass_once()
        exact(state["items"], [other])
        exact("WATCHDOG" in output, False)
        exact("WATCH gatekeep: signal=launchd" in output, True)
        exact("alarm=" in output, False)

        # A job launchd no longer holds is a dead job, and the alarm names
        # it. The item stays a single item over repeated passes.
        jobs["dev.coordinator.gatekeep"] = "not-loaded"
        output = pass_once()
        expected = alarm("Factory job stopped or failing: gatekeep stopped "
                         "(launchd job dev.coordinator.gatekeep is not loaded)")
        exact(state["items"], expected)
        exact("WATCHDOG" in output, True)
        pass_once()
        exact(state["items"], expected)
        exact(len([item for item in state["items"]
                   if item["id"] == "factory-watchdog"]), 1)

        # A job that launchd holds but that fails is a dead job too.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 13,
                                            "exit": 1, "running": False}
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: gatekeep "
                                    "failing (last exit code 1)"))
        exact("WATCHDOG" in output, True)

        # A job that launchd killed with a signal never reports an exit
        # code, and it is a dead job.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 13,
                                            "exit": None, "signal": 9,
                                            "running": False}
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: gatekeep "
                                    "killed (last terminating signal 9)"))
        exact("WATCHDOG" in output, True)

        # launchd prints the name with the signal when it knows it.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 13,
                                            "exit": None, "signal_text": "Killed: 9",
                                            "running": False}
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: gatekeep "
                                    "killed (last terminating signal 9)"))
        exact("WATCHDOG" in output, True)

        # launchd prints the name with the exit code when it knows it.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 13,
                                            "exit_text": "78: EX_CONFIG",
                                            "running": False}
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: gatekeep "
                                    "failing (last exit code 78)"))
        exact("WATCHDOG" in output, True)

        # A job that never ran reports no exit code. It is not a failure
        # while it is running, so a run that is on time raises nothing.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 0,
                                            "exit_text": "(never exited)",
                                            "running": True, "pid": 6161}
        elapsed[6161] = 5
        output = pass_once()
        exact(state["items"], [other])
        exact("WATCHDOG" in output, False)

        # The run in flight decides. A job that is running now is judged by
        # that run, so what an earlier run left behind raises nothing: a
        # previous nonzero exit, then a previous signal.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 13,
                                            "exit": 1, "running": True,
                                            "pid": 6161}
        output = pass_once()
        exact(state["items"], [other])
        exact("WATCHDOG" in output, False)
        exact("signal=launchd" in output, True)

        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 13,
                                            "exit": None, "signal": 9,
                                            "running": True, "pid": 6161}
        output = pass_once()
        exact(state["items"], [other])
        exact("WATCHDOG" in output, False)

        # The same previous failures raise the alarm once the job is idle
        # again, so a job that keeps failing is never silenced.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 13,
                                            "exit": 1, "running": False}
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: gatekeep "
                                    "failing (last exit code 1)"))
        exact("WATCHDOG" in output, True)

        # A run that never ended and overran its limit is stuck, whatever
        # the log says.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 0,
                                            "exit_text": "(never exited)",
                                            "running": True, "pid": 6161}
        elapsed[6161] = 200 * 60
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: gatekeep "
                                    "stuck (running 200 min, limit 120)"))
        exact("WATCHDOG" in output, True)
        del elapsed[6161]

        # A job that never ran and is not running now leaves the log age as
        # the only evidence, so a stale log still alarms.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 0,
                                            "exit_text": "(never exited)",
                                            "running": False}
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: gatekeep "
                                    "silent 200 min (limit 120)"))
        exact("signal=log-age" in output, True)
        exact("WATCHDOG" in output, True)

        # A job that is still running past its limit is stuck, whatever its
        # log says.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 14, "exit": 0,
                                            "running": True, "pid": 4242}
        elapsed[4242] = 200 * 60
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: gatekeep "
                                    "stuck (running 200 min, limit 120)"))
        exact("WATCHDOG" in output, True)

        # A job that is running and that nobody can time is not known to be
        # healthy, so the log age decides and a stale log still alarms.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 14, "exit": 0,
                                            "running": True, "pid": 5151}
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: gatekeep "
                                    "silent 200 min (limit 120)"))
        exact("signal=log-age" in output, True)
        exact("WATCHDOG" in output, True)

        # The healthy job raises nothing, so the item goes away.
        jobs["dev.coordinator.gatekeep"] = {"loaded": True, "runs": 15,
                                            "exit": 0, "running": False}
        output = pass_once()
        exact(state["items"], [other])
        exact("WATCHDOG" in output, False)

        # When launchd cannot say, the log age is the only evidence left,
        # so a stale log still alarms.
        for label in labels.values():
            jobs[label] = None
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: tick silent "
                                    "200 min (limit 65); gatekeep silent 200 min "
                                    "(limit 120); dispatch silent 200 min (limit 10); "
                                    "lanes silent 200 min (limit 10)"))
        exact("signal=log-age" in output, True)
        exact("WATCHDOG" in output, True)

        # A launchctl failure that is not a missing service is a failure to
        # read, not a stopped job, so the log age decides.
        for label in labels.values():
            jobs[label] = "unreadable"
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: tick silent "
                                    "200 min (limit 65); gatekeep silent 200 min "
                                    "(limit 120); dispatch silent 200 min (limit 10); "
                                    "lanes silent 200 min (limit 10)"))
        exact("signal=log-age" in output, True)

        # A job that launchd holds but that never ran reports no exit code,
        # so the log age decides and a fresh log raises nothing.
        for label in labels.values():
            jobs[label] = {"loaded": True, "runs": 0, "exit": None,
                            "running": False}
        for path in mtimes:
            mtimes[path] = now
        output = pass_once()
        exact(state["items"], [other])
        exact("WATCHDOG" in output, False)

        # The silence limit is a limit: a log exactly at the limit is quiet
        # enough, a log one minute past it is not.
        jobs["dev.coordinator.gatekeep"] = None
        mtimes[lane.WATCH["gatekeep"][0]] = now - limits["gatekeep"] * 60
        output = pass_once()
        exact(state["items"], [other])
        exact("WATCHDOG" in output, False)
        mtimes[lane.WATCH["gatekeep"][0]] = now - (limits["gatekeep"] + 1) * 60
        output = pass_once()
        exact(state["items"], alarm("Factory job stopped or failing: gatekeep "
                                    "silent 121 min (limit 120)"))
        exact("WATCHDOG" in output, True)

        for label in labels.values():
            jobs[label] = {"loaded": True, "runs": 16, "exit": 0, "running": False}
        for path in mtimes:
            mtimes[path] = now
        pass_once()
        exact(state["items"], [other])
        # The pass replaces the board file and the mute state file, each
        # from its own temporary file, and nothing else.
        replaced = {(str(call.args[0]), str(call.args[1])) for call in replace.call_args_list}
        exact(replaced - {(decisions + ".tmp", decisions),
                          (f"{decisions}.{os.getpid()}.tmp", decisions),
                          (mute + ".tmp", mute),
                          (f"{mute}.{os.getpid()}.tmp", mute)}, set())


def zero_merge():
    """Run the merge-alert fixture in a folder that is always cleaned up.

    The folder holds the mute state the fixture writes, so it is a
    temporary directory rather than a directory the run leaves behind:
    the cleanup runs after a failed assertion too."""
    with tempfile.TemporaryDirectory(prefix="zero-merge-mute-") as scratch:
        zero_merge_fixture(Path(scratch))


def zero_merge_fixture(scratch):
    import datetime as dt
    import os
    import lane_driver as lane
    other = {"id": "unrelated"}
    state = {"items": [other]}
    owner = {"items": []}
    def held():
        return state["items"] + owner["items"]
    now = dt.datetime(2026, 11, 15, 12, tzinfo=dt.timezone.utc)
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    snapshot = {"repos": {"fixture/one": {"prs": [{"number": 1}]},
                          "fixture/two": {"prs": []}}}
    rows = []
    calls = []
    def read(command):
        exact(command, ["gh", "pr", "list", "-R", command[4], "--state", "merged",
            "--search", "merged:>=2026-11-15T11:00:00Z", "--limit", "1", "--json", "mergedAt"])
        calls.append(command[4])
        return rows if command[4] == "fixture/two" else []
    def opened(path, mode="r"):
        exact(path, "/Users/shyamsivakumar/Code/coordinator/decisions.json" + (".tmp" if mode == "w" else ""))
        return io.StringIO(json.dumps(state) if mode == "r" else "")
    def saved(value, handle, **kwargs):
        state.clear()
        state.update(json.loads(json.dumps(value)))
    # The alarm's key names the repos that are waiting, so a stall on one
    # repo does not silence a stall on another. The title stays one title.
    alert = {"id": "factory-zero-merge", "group": "Coordinator", "kind": "action",
        "title": "No merge in 60 minutes with open PRs",
        "cause": "No merge in 60 minutes with open PRs: fixture/one",
        "why": "The coordinator must inspect blocked PRs and restore merge progress: fixture/one"}
    # The alarm's mute state goes to a file of its own, so the eval never
    # reads or writes the live shift's folder.
    mute = str(scratch / "mute-state.json")

    def read_board(path):
        return b"", json.loads(json.dumps(owner if Path(path).name == "mac-ops-owner.json" else state))

    def write_board(path, board):
        target = owner if Path(path).name == "mac-ops-owner.json" else state
        target.clear()
        target.update(json.loads(json.dumps(board)))
        return True

    def swap_alarm(path, alarm_id, action, item):
        state["items"] = [i for i in state["items"] if i.get("id") != alarm_id]
        return "wrote"

    import alarms
    with patch.object(dt, "datetime", Clock), patch.object(lane, "read_json", side_effect=read), \
         patch("builtins.open", side_effect=opened), patch.object(lane.json, "dump", side_effect=saved), \
         patch.object(alarms, "MUTE_PATH", mute), \
         patch.object(lane, "DECISIONS_PATH", str(Path(mute).parent / "decisions.json")), \
         patch.object(alarms, "read_board", side_effect=read_board), \
         patch.object(alarms, "write_board", side_effect=write_board), \
         patch.object(alarms, "swap_alarm", side_effect=swap_alarm), \
         patch.object(lane.os, "replace") as replace:
        for stamps, expected in [([], [other, alert]),
                (["2026-11-15T10:59:59Z"], [other, alert]),
                (["2026-11-15T11:00:00Z"], [other]),
                (["2026-11-15T11:59:00Z"], [other]),
                ([], [other, alert])]:
            rows = [{"mergedAt": stamp} for stamp in stamps]
            lane.zero_merge(snapshot)
            exact(held(), expected)
        exact(calls, ["fixture/one", "fixture/two"] * 5)
        with patch.object(lane, "read_json", side_effect=RuntimeError("fixture read failure")):
            try:
                lane.zero_merge(snapshot)
            except RuntimeError as exc:
                exact(str(exc), "fixture read failure")
            else:
                raise AssertionError("read failure was swallowed")
        exact(held(), [other, alert])

        snapshot["repos"]["fixture/one"]["prs"] = []
        # A healthy tick raises nothing, so it says nothing about an alarm:
        # "with open PRs: none" is not a stall.
        healthy = io.StringIO()
        with contextlib.redirect_stdout(healthy):
            lane.zero_merge(snapshot)
        exact(held(), [other])
        exact(len(calls), 10)
        # A board that cannot be written is reported, not swallowed: the
        # alarm is nowhere, and the tick has to say so.
        with patch.object(alarms, "board_update", return_value="failed"):
            try:
                lane.zero_merge(snapshot)
            except RuntimeError as exc:
                exact("could not be published" in str(exc), True)
            else:
                raise AssertionError("a failed publication was swallowed")
        exact("ZERO-MERGE No merge" in healthy.getvalue(), False)
        # The board is written through the alarm module's own writer, and
        # the mute state beside it, each from a temporary file of its own.
        replaced = {(str(call.args[0]), str(call.args[1])) for call in replace.call_args_list}
        # The mute state was written: the exact pair was seen, and nothing
        # else was replaced for it.
        exact((f"{mute}.{os.getpid()}.tmp", mute) in replaced, True)

        # The changed cause reaches the board. The alarm for one waiting
        # repo is answered, a second repo starts waiting, and the next
        # pass must raise an alarm whose cause names both repos. A
        # producer that kept using the first repo as its cause would fail
        # here, and would have silenced the newly stalled repo.
        import alarms as mute_rules
        snapshot["repos"]["fixture/one"]["prs"] = [{"number": 1}]
        snapshot["repos"]["fixture/two"]["prs"] = []
        rows = []
        lane.zero_merge(snapshot)
        first = [i for i in held() if i["id"] == "factory-zero-merge"]
        exact(len(first), 1)
        exact(first[0]["cause"], "No merge in 60 minutes with open PRs: fixture/one")
        # The answer goes to the mute state the shift keeps. The replace
        # above is observed by a mock, so the eval writes the record the
        # panel writes, rather than replacing the file and losing it.
        answers = mute_rules.load_state()
        answered = mute_rules.key_of("factory-zero-merge", first[0]["cause"])
        mute_rules.acknowledge(answers, answered, now)
        Path(mute).write_text(json.dumps({mute_rules.STATE_KEY: answers}))
        exact(mute_rules.muted(mute_rules.load_state(), answered, now), True)
        # The answered cause is quiet: the same wait raises no board item.
        lane.zero_merge(snapshot)
        exact([i for i in held() if i["id"] == "factory-zero-merge"], [])
        # A repository that starts waiting is a different cause, so it
        # alarms at once under its own key.
        snapshot["repos"]["fixture/two"]["prs"] = [{"number": 2}]
        lane.zero_merge(snapshot)
        raised = [i for i in held() if i["id"] == "factory-zero-merge"]
        exact(len(raised), 1)
        exact(raised[0]["cause"], "No merge in 60 minutes with open PRs: fixture/one, fixture/two")
        exact(state["items"], [other])
        state["items"].append(dict(alert))
        lane.zero_merge(snapshot)
        exact([i["id"] for i in state["items"]], ["unrelated"])
        exact([i["id"] for i in owner["items"]], ["factory-zero-merge"])


def board_integrity():
    import board_integrity as audit
    def issue(n, title, stages):
        return dict(number=n, title=title, state="OPEN", labels=[{"name": "stage:" + stage} for stage in stages])
    rows = [issue(1, "MO-1 missing", []), issue(2, "MO-2 duplicate", ["todo", "started"]),
            issue(3, "bad key", ["todo"]), issue(4, "MO-4 duplicate", ["todo"]),
            issue(5, "MO-4 duplicate", ["todo"]), issue(6, "MO-6 started", ["todo"]),
            issue(7, "MO-7 parked", ["backlog"]), issue(8, "MO-8 blocked", ["todo"]),
            issue(9, "MO-9 merged", ["todo"])]
    rows[7]["blockedBy"] = {"totalCount": 1, "nodes": [{"number": 7}]}
    snapshot = {"tickets": [{"repo": "fixture/repo", "number": 6, "stage": "started"}],
                "repos": {"fixture/repo": {"key": "MO", "issues": rows, "prs": [
                    {"number": 10, "state": "OPEN", "body": "Refs #7"},
                    {"number": 11, "state": "MERGED", "body": "Refs #9"}]}}}
    expected = sorted(["fixture/repo#1: expected exactly one stage",
        "fixture/repo#2: expected exactly one stage", "fixture/repo#3: malformed key",
        "fixture/repo: duplicate key MO-4: [4, 5]", "fixture/repo#6: started lost stage:started",
        "fixture/repo#8: blocked by parked #7 with open PR #10",
        "fixture/repo#9: merged PR #11 issue still open"])
    exact(audit.defects(snapshot), expected)
    with patch("sys.stdin", io.StringIO(json.dumps(snapshot))), contextlib.redirect_stdout(io.StringIO()) as output:
        exact(audit.main(), 1)
    exact(output.getvalue().splitlines(), expected)
    clean = {"tickets": [], "repos": {"fixture/repo": {"key": "MO", "issues": [issue(1, "MO-1 healthy", ["started"])], "prs": []}}}
    with patch("sys.stdin", io.StringIO(json.dumps(clean))):
        exact(audit.main(), 0)
    runner = load_runner()
    states = {7: "CLOSED", 8: "OPEN"}
    def answer(command, *args, **kwargs):
        numbers = re.findall(r"issue\(number: (\d+)\)", " ".join(command))
        body = json.dumps({"data": {"repository": {f"i{n}": ({"number": int(n), "state": states[int(n)], "title": "t"} if int(n) in states else None) for n in numbers}}})
        if len(numbers) == len(states):
            return body
        raise runner.RepoError("gh api graphql failed (1): could not resolve", stdout=body)
    with patch.object(runner, "run", answer):
        exact(runner.read_blocker_states("o/r", {7, 8}, 9e9), ({7}, ""))
        exact(runner.read_blocker_states("o/r", {7, 8, 9}, 9e9), ({7}, ""))
    with patch.object(runner, "run", lambda *a, **k: None):
        exact(runner.read_blocker_states("o/r", {7}, 9e9), (set(), "o/r: the blocker states could not be read"))
    text = "## Blocked by\n\n#7, #8, #9, MO-3\n"
    exact(runner.blockers_for(text, "o/r", "MO", {"o/r": {8}}, {"o/r": {7}}, {}, {}),
          ["MO-3 could not be read", "o/r#8 is still open", "o/r#9 could not be read"])


def api_budget():
    from live_smoke import fixture as live_fixture
    live_fixture()
    import datetime as dt
    import lane_driver as lane
    from unittest.mock import mock_open
    repo = "fixture/repo"
    ledger = {}
    commands = []
    def read(command, fresh=False):
        commands.append(command)
        return {"issues": []} if command[0] == "ticket" else []
    with patch.object(lane, "LANE_REPOS", [repo]), patch.object(lane, "read_json", side_effect=read):
        for number in range(1, 12):
            lane.board_snapshot(ledger)
            exact(ledger["_pass"], number)
            exact(len(commands), ((number - 1) // 5 + 1) * 3)
    now = dt.datetime(2026, 11, 16, tzinfo=dt.timezone.utc)
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    tickets = [dict(repo=repo, number=n, key=f"F-{n}", stage="todo", problems=[]) for n in range(1, 6)]
    commands.clear()
    def refused(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 2, "refused: fixture", "")
    ledger = {}
    with patch.object(dt, "datetime", Clock), patch.object(lane, "unstick", return_value="nothing ready"), \
         patch.object(lane, "api_remaining", return_value={"core": lane.API_FLOOR + 500, "graphql": lane.API_FLOOR + 500}), \
         patch.object(subprocess, "run", side_effect=refused):
        lane.start_next(repo, tickets, ledger)
        exact(commands, [["ticket", "start", f"{repo}#{n}", "--dry-run"] for n in (1, 2, 3)])
        for seconds, expected in [(1799, [4, 5]), (1800, [1, 2, 3])]:
            now = Clock(2026, 11, 16, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=seconds)
            commands.clear()
            lane.start_next(repo, tickets, ledger)
            exact(commands, [["ticket", "start", f"{repo}#{n}", "--dry-run"] for n in expected])
    for resource in ("core", "graphql"):
        remaining = {"core": lane.API_FLOOR, "graphql": lane.API_FLOOR}
        remaining[resource] -= 1
        with patch.object(lane, "api_remaining", return_value=remaining):
            for action in (lambda: lane.read_json(["gh", "fixture"]),
                           lambda: lane.run(["ticket", "start", "fixture/repo#1", "--dry-run"])):
                try:
                    action()
                except lane.ApiBudgetExhausted:
                    pass
                else:
                    raise AssertionError("read continued below floor")
    with patch.object(lane, "api_remaining", return_value={"core": lane.API_FLOOR, "graphql": lane.API_FLOOR}), \
         patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "[]", "")) as called:
        exact(lane.read_json(["gh", "fixture"]), [])
        exact(called.call_count, 1)
    for exhausted in (False, True):
        quota = [{"core": 1000, "graphql": 1000}, {"core": 990, "graphql": 995}]
        with patch("builtins.open", mock_open(read_data='{"repos": {}}')), \
             patch.object(lane.json, "dump"), patch.object(lane, "DRY", True), \
             patch.object(lane, "api_remaining", side_effect=quota), \
             patch.object(lane, "run_pass", side_effect=lane.ApiBudgetExhausted("fixture") if exhausted else None), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            lane.main()
        exact(output.getvalue().splitlines(), (["API BUDGET fixture"] if exhausted else []) + [
            f"API USAGE used={{'core': 10, 'graphql': 5}} remaining={{'core': 990, 'graphql': 995}} floor={lane.API_FLOOR}"])


def ff_drift():
    import lane_driver as lane
    repo = "fixture/repo"
    path = "/Users/shyamsivakumar/Code/fixture"
    local, origin = "a" * 40, "b" * 40
    forwards = []
    ancestor = True

    def run(cmd, **kwargs):
        if cmd == ["git", "-C", path, "fetch", "origin", "main"]:
            return ""
        if cmd == ["git", "-C", path, "rev-parse", "main", "origin/main"]:
            return f"{local} {origin}"
        if cmd == ["git", "-C", path, "merge-base", "--is-ancestor", local, origin]:
            if not ancestor:
                raise subprocess.CalledProcessError(1, cmd)
            return ""
        raise AssertionError(f"unexpected command: {cmd}")

    with patch.object(lane, "PATHS", {repo: "fixture"}), \
         patch.object(lane, "LANE_REPOS", [repo]), \
         patch.object(lane, "CFG", {repo: {"key": "FIX"}}), \
         patch.object(lane, "DRY", False), \
         patch.object(lane.os.path, "isdir", return_value=True), \
         patch.object(lane, "fast_forward_main", side_effect=forwards.append), \
         patch.object(lane, "run", side_effect=run):
        lane.drift_ff({})
        exact(forwards, [repo])
        local = origin
        lane.drift_ff({})
        exact(forwards, [repo])
        origin = "d" * 40
        ancestor = False
        lane.drift_ff({})
        exact(forwards, [repo])


def script_results():
    import script_results as results
    records = [{"repo": "fixture/repo", "issue": n, "deadline": deadline,
                "state": "WAITING", **extra}
               for n, deadline, extra in [(1, 99, {}), (2, 100, {}),
                   (3, 101, {}), (4, 99, {"result": "PASS"}),
                   (5, 101, {"result": "FAIL"})]]
    exact(results.reconcile(records, 100), [
        {"action": "recut", "repo": "fixture/repo", "issue": 1},
        {"action": "recut", "repo": "fixture/repo", "issue": 5}])
    exact([row["state"] for row in records], ["FAIL", "WAITING", "WAITING", "PASS", "FAIL"])
    exact(results.reconcile(records, 100), [])
    for outcome, status, reason in [(subprocess.CompletedProcess([], 0), "PASS", "artifact"),
            (subprocess.CompletedProcess([], 7), "FAIL", "exit 7"),
            (subprocess.TimeoutExpired(["fixture-script"], 2), "FAIL", "timeout"),
            (OSError("missing"), "FAIL", "launch error: missing")]:
        calls = []
        def run(command, **kwargs):
            calls.append((command, kwargs))
            if command == ["fixture-script"]:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            if command[:3] != ["gh", "issue", "comment"]:
                raise AssertionError(command)
            return subprocess.CompletedProcess(command, 0)
        with patch.object(results.subprocess, "run", run):
            exact(results.run_script("fixture/repo", 1, "abc", 2, ["fixture-script"], "artifact"),
                  int(status == "FAIL"))
        exact(calls, [(["fixture-script"], {"timeout": 2, "check": False}),
            (["gh", "issue", "comment", "1", "--repo", "fixture/repo", "--body",
              f"RESULT: {status} abc {reason}"], {"timeout": 60, "check": True})])


def consolidation_guard():
    import lane_driver as lane
    ticket = load_ticket()
    cfg = {}
    item = {"body": "Implement the scoped fixture. Report leftover work in the PR.",
            "url": "https://fixture/issue/1", "reviewerAlias": "astra-api"}
    builder = ticket.assemble_brief(cfg, item, "fixture-run", {"comments": []})
    gate = ticket.gate_brief("fixture/repo", {"key": "FIX"}, 1, 2,
                             "a" * 40, "main", False, False)
    import ast
    queue_path = Path(__file__).resolve().parents[1] / "bin" / "coordq"
    tree = ast.parse(queue_path.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "gate_args")
    namespace = {"GATE_BAR": ticket.GATE_BAR}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(queue_path), "exec"), namespace)
    for ascend in (False, True):
        settings = {"key": "FIX", "projectId": "fixture", "ascend": ascend}
        briefs = (ticket.gate_brief("shyamsivakumar/fixture", settings, 1, 2, "a" * 40, "main", False, ascend),
                  namespace["gate_args"](settings, "shyamsivakumar/fixture", 1, 2, "a" * 40, False, "fixture")["message"])
        for emitted in briefs:
            exact("Builder check: PASS " + "a" * 40 in emitted, True)
            if ascend:
                exact("gh pr merge" in emitted, False)
                exact("gh issue close" in emitted, False)
            else:
                exact("--match-head-commit " + "a" * 40 in emitted, True)
                exact("verify every Provides claim" in emitted, True)
                exact("false, missing or unverified, close nothing" in emitted, True)
                exact(emitted.index("verify every Provides claim") < emitted.index("gh issue close"), True)
    lane_brief = ticket.gate_brief("shyamsivakumar/mac-ops", {"key": "FIX"}, 1, 2, "a" * 40, "main", False, False)
    exact("gh pr merge" in lane_brief, False)
    exact("fast-forward" in lane_brief and "git merge --ff-only" in lane_brief, False)
    exact("PROVIDES: PASS " + "a" * 40 in lane_brief, True)
    other_brief = ticket.gate_brief("shyamsivakumar/tunerise", {"key": "FIX"}, 1, 2, "a" * 40, "main", False, False)
    exact("gh pr merge" in other_brief, False)
    exact("PROVIDES: PASS " + "a" * 40 in other_brief, True)
    exact(all(word in builder for word in ("Partial: yes", "## Left for later", "300", "Refs #n")), True)
    import gate_policy
    for text, claim in (("Partial: yes\n## Left for later\n- x\n## Next\ny", "- x"), ("Partial: yes", ""),
                        ("```\nPartial: yes\n```\n## Left for later\n- x", None), ("Refs #1", None)):
        exact(gate_policy.partial_claim(text), claim)
    exact(gate_policy.partial_claim("> **Partial: yes**.\r\n### Left for later:\r\n- x"), "- x")
    sized = lambda lines: (lambda: [{"filename": "coordinator/bin/x.py", "additions": lines, "deletions": 0}])
    exact([gate_policy.partial_state(body, sized(n)) for body, n in (("Partial: yes\n## Left for later\n- x", 199), ("Partial: yes\n## Left for later\n- x", 200),
           ("Partial: yes\n## Left for later\n- x", 301), ("Partial: yes", 250), ("Refs #1", 250))], [False, True, False, False, None])
    log = []
    closed = {"state": "CLOSED", "stateReason": "COMPLETED", "labels": [{"name": "stage:todo"}], "comments": []}
    with patch.object(ticket, "gh_json", lambda args, **kw: closed), patch.object(ticket, "gh", lambda args, **kw: log.append(args[:2])), \
         patch.object(ticket.alarms, "route_update", lambda *a, **k: "wrote"), patch.object(ticket.journal, "emit", lambda *a, **k: log.append([a[0]])), \
         contextlib.redirect_stdout(io.StringIO()):
        ticket.keep_open_partial("shyamsivakumar/mac-ops", 7, 8, "a" * 40, "m", "x")
    exact([entry for entry in log if entry != ["label", "create"]], [["issue", "reopen"], ["issue", "edit"], ["issue", "comment"], ["partial_merged"]])
    log.clear()
    closed.update(stateReason="NOT_PLANNED", comments=[])
    with patch.object(ticket, "gh_json", lambda args, **kw: closed), patch.object(ticket, "gh", lambda args, **kw: log.append(args[:2])), \
         patch.object(ticket.alarms, "route_update", lambda *a, **k: "wrote"), patch.object(ticket.journal, "emit", lambda *a, **k: None), \
         contextlib.redirect_stdout(io.StringIO()):
        ticket.keep_open_partial("shyamsivakumar/mac-ops", 7, 8, "a" * 40, "m", "x")
    exact(["reopen" in entry for entry in log].count(True), 0)
    brief_of = lambda repo, **kw: gate_policy.build_gate_brief({"key": "FIX"}, repo, 1, 2, "a" * 40, False, **kw)
    for repo in ("shyamsivakumar/zzz-fixture", "shyamsivakumar/mac-ops"):
        plain, partial = brief_of(repo), brief_of(repo, partial=True)
        exact(plain == brief_of(repo, partial=None) and "Partial: yes" not in plain, True)
        marked = brief_of(repo, partial=False)
        exact("the issue stays open" in marked or "Nothing closes the issue" in marked, True)
        exact("gh issue close" not in marked and "no finding" not in marked, True)
        exact("gh issue close" in partial, False)
        exact("Nothing closes the issue" in partial and "Work listed there is no finding" in partial, True)
        exact("PROVIDES: PASS " + "a" * 40 in partial, True)
    for brief in (builder, gate):
        exact(re.findall(r"(?i)(?:gh\s+issue\s+create|(?:create|file|open)\s+(?:a\s+|new\s+)?(?:issues?|tickets?))", brief), [])
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return "fixture-receipt"
    with patch.object(lane, "run", run), patch.object(lane, "DRY", False), \
         patch.object(lane, "CFG", {"fixture/repo": {"projectId": "fixture", "key": "FIX"}}):
        ledger = {}
        lane.park("fixture/repo", 2, 1, "a" * 40, "fixture verdict", ledger)
        lane.park("fixture/repo", 2, 1, "a" * 40, "fixture verdict", ledger)
    launches = [command for command in calls if command[:2] == [lane.COORDQ, "start"]]
    exact(len(launches), 1)
    message = json.loads(launches[0][2])["message"]
    exact("at most 2 ordered tickets" in message, True)
    exact("never create a third ticket" in message, True)


def worktree_base_ref():
    """A worktree launch always names the ref it branches from.

    T3 0.1.10 refuses a worktree launch with no baseRef, so a hand-built
    payload that leaves it out is dropped after three attempts. coordq fills
    the lane default at dispatch, keeps a caller's own baseRef and
    startFromOrigin, and leaves every other strategy and tool alone.
    """
    import ast
    import copy
    queue_path = Path(__file__).resolve().parents[1] / "bin" / "coordq"
    tree = ast.parse(queue_path.read_text())
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "worktree_base")
    # The default is read from coordq and checked against the literal here, so
    # the eval cannot agree with a wrong default.
    constant = next(node for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(getattr(target, "id", None) == "DEFAULT_BASE_REF" for target in node.targets))
    default_ref = ast.literal_eval(constant.value)
    exact(default_ref, "origin/main")
    namespace = {"DEFAULT_BASE_REF": default_ref}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(queue_path), "exec"), namespace)
    fill = namespace["worktree_base"]
    launch = "t3_thread_launch"
    default = {"type": "worktree", "baseRef": "origin/main", "startFromOrigin": True}
    # A worktree launch with no baseRef gets the lane default.
    exact(fill(launch, {"workspaceStrategy": {"type": "worktree"}}),
          {"workspaceStrategy": default})
    # An empty baseRef is a missing one.
    exact(fill(launch, {"workspaceStrategy": {"type": "worktree", "baseRef": ""}}),
          {"workspaceStrategy": default})
    # A caller's own baseRef and startFromOrigin are kept as given. The input
    # is a copy, so a function that changed it in place would not also change
    # the expected value.
    own = {"workspaceStrategy": {"type": "worktree", "baseRef": "origin/builder/fixture",
                                 "startFromOrigin": False}}
    exact(fill(launch, copy.deepcopy(own)), own)
    exact(fill(launch, {"workspaceStrategy": {"type": "worktree", "baseRef": "origin/builder/fixture"}}),
          {"workspaceStrategy": {"type": "worktree", "baseRef": "origin/builder/fixture"}})
    # A caller's own startFromOrigin is kept when only the baseRef is filled.
    exact(fill(launch, {"workspaceStrategy": {"type": "worktree", "startFromOrigin": False}}),
          {"workspaceStrategy": {"type": "worktree", "baseRef": "origin/main",
                                 "startFromOrigin": False}})
    # A root or existing_worktree strategy is left alone.
    for strategy in ({"type": "root"}, {"type": "existing_worktree", "worktreePath": "/fixture"}):
        args = {"workspaceStrategy": strategy}
        exact(fill(launch, copy.deepcopy(args)), args)
    # No other tool gets a baseRef, and a launch with no strategy is left alone.
    for tool in ("t3_thread_send", "t3_thread_list"):
        args = {"workspaceStrategy": {"type": "worktree"}}
        exact(fill(tool, copy.deepcopy(args)), args)
    exact(fill(launch, {"message": "brief"}), {"message": "brief"})


def gate_round_cap():
    """The convergence rule in the lane: three failed reviews, then one item.

    The convergence rule (Shyam, 2026-11-18): after 3 review rounds
    without PASS the pull request is re-cut or brought to Shyam, and it is
    not reviewed a 4th time as it is. The first review of a pull request
    is round 1, so the lane sends two fix rounds (the answers to rounds 1
    and 2) and the third failed review raises one decisions item instead
    of a third fix round.
    """
    import lane_driver as lane
    repo = "shyamsivakumar/mac-ops"
    heads = ["a" * 40, "b" * 40, "c" * 40, "d" * 40]
    sent = []
    current = [""]
    files = None
    parked = []
    with tempfile.TemporaryDirectory() as scratch, scratch_board(scratch) as decisions:
        board = decisions.with_name("mac-ops-owner.json")

        def command(cmd, timeout=150):
            if cmd[:3] == ["gh", "pr", "view"]:
                return json.dumps({"state": "OPEN", "mergedAt": None})
            if cmd[:2] == ["gh", "api"]:
                # The prompt classification this branch adds reads the pinned
                # trees; every head here is code-only against its base.
                endpoint = cmd[-1]
                if endpoint.endswith("/files?per_page=100"):
                    if files is None:
                        raise subprocess.CalledProcessError(1, cmd)
                    return json.dumps(files)
                if "/compare/" in endpoint:
                    return json.dumps({"merge_base_commit": {"sha": "base"}})
                if endpoint.endswith("/git/trees/base?recursive=1"):
                    return json.dumps({"tree": [{"type": "blob", "path": "a.py", "sha": "1"}]})
                if "/git/trees/" in endpoint:
                    return json.dumps({"tree": [{"type": "blob", "path": "a.py", "sha": "2"}]})
            if cmd[:2] == ["ticket", "close"]:
                return "closed"
            if cmd[:2] == ["ticket", "gate"]:
                return json.dumps([{"selection": {"model": "m"}}]) if "--print-model" in cmd else f"brief {current[0]}"
            raise AssertionError(f"unexpected command: {cmd}")

        def threads(tool, args):
            raise AssertionError(f"unexpected T3 tool: {tool}")

        def send(thread_id, message, title, ledger, lkey, **kwargs):
            sent.append(lkey)
            # The real send records the message in the ledger, and the
            # ledger is where the lane counts the fix rounds of a pull
            # request.
            ledger[lkey] = "sent"
            return "sent"

        def act(number, head, ledger, verdict=("FAIL", {"threadId": "gate"}, "finding\nVERDICT: FAIL"), labels=(), board=True, dry=False, body="", issue_labels=(), **fields):
            """Run the lane over one pull request at one head."""
            current[0] = head
            pr = dict(number=number, state="OPEN", headRefOid=head, labels=[{"name": n} for n in labels],
                      body=f"Refs #10\n{body}\nBuilder check: PASS {head}", mergeable="MERGEABLE", **fields)
            snapshot = {"repos": {repo: {"prs": [pr], "issues": [dict(number=10, labels=[{"name": n} for n in issue_labels])]}}}
            with patch.object(lane, "CFG", {repo: dict(key="FIX", projectId="fixture")}), \
                 patch.object(lane, "round_cap_to_board", lambda _: board), \
                 patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "DRY", dry), \
                 patch.object(lane, "builder_thread", return_value=("10", "live-builder")), \
                 patch.object(lane, "gate_verdict", return_value=verdict), \
                 patch.object(lane, "read_json", side_effect=pr_reads(lane, dict(number=number, state="OPEN", headRefName="builder/fixture", baseRefName="main"))), \
                 patch.object(lane, "run", command), patch.object(lane, "t3", threads), \
                 patch.object(lane, "send", send), \
                 patch.object(lane, "park", lambda *args: parked.append(args[1]) or "parked"):
                return lane.act_on_pr(repo, number, ledger)

        ledger = {}
        for head in heads:
            act(20, head, ledger)
        # Two fix rounds: the answers to the first and the second review.
        exact(sent, [f"fix:{repo}#20:{heads[0]}", f"fix:{repo}#20:{heads[1]}"])
        # The third failed review and the fourth raise one decisions item
        # between them, and the board holds that one item.
        items = json.loads(board.read_text())["items"]
        exact(len(items), 1)
        exact(items[0]["kind"], "ask")
        exact(items[0]["title"].startswith("Shyam,"), True)
        exact(len(items[0]["options"]), 3)
        # The fix rounds of the pull request are its failed reviews before
        # the one in hand.
        exact(lane.failed_reviews(repo, 20, ledger), (4, heads[3]))
        # A new head after the cap gets no 4th review. The lane asks no
        # reviewer for a model or for a brief, so no such command runs,
        # and no fix round is sent.
        result = act(20, "e" * 40, ledger, verdict=("absent", None, ""))
        exact(result, "#20: no fix round, the decisions item is on the board")
        exact(sent, [f"fix:{repo}#20:{heads[0]}", f"fix:{repo}#20:{heads[1]}"])
        exact(len(json.loads(board.read_text())["items"]), 1)
        # A pull request that two earlier lane sessions already sent two
        # fix rounds to has had two reviews. The third failed review
        # raises the decisions item, and no third fix round is sent.
        earlier = {f"fix:{repo}#21:{heads[0]}": "sent", f"fix:{repo}#21:{heads[1]}": "sent"}
        result = act(21, heads[2], earlier)
        exact(sent, [f"fix:{repo}#20:{heads[0]}", f"fix:{repo}#20:{heads[1]}"])
        exact(lane.failed_reviews(repo, 21, earlier), (3, heads[2]))
        exact(result.endswith("one decisions item is on the board"), True)
        # A pull request with three historical fix rounds, a new head and
        # no item on the board reaches the cap before any verdict. The lane
        # publishes the item then, and it does not report an item that was
        # never written.
        history = {f"fix:{repo}#22:{head}": "sent" for head in heads[:3]}
        result = act(22, "f" * 40, history, verdict=("absent", None, ""))
        exact(result, f"#22: no fix round after {lane.GATE_ROUND_CAP} failed reviews, one decisions item is on the board")
        exact(sorted(item["id"] for item in json.loads(board.read_text())["items"]),
              [f"lane-gate-rounds-shyamsivakumar-mac-ops-{number}" for number in (20, 21, 22)])
        exact(sent, [f"fix:{repo}#20:{heads[0]}", f"fix:{repo}#20:{heads[1]}"])
        # A pull request with three historical fix rounds whose current
        # head is the third one, a FAIL verdict and an interrupted builder
        # reaches the cap before the same-head retry. The lane raises the
        # item and sends no "Continue fixing".
        same_head = {f"fix:{repo}#23:{head}": "sent" for head in heads[:3]}
        result = act(23, heads[2], same_head)
        exact(result, f"#23: no fix round after {lane.GATE_ROUND_CAP} failed reviews, one decisions item is on the board")
        exact(sorted(item["id"] for item in json.loads(board.read_text())["items"])[-1],
              "lane-gate-rounds-shyamsivakumar-mac-ops-23")
        exact(sent, [f"fix:{repo}#20:{heads[0]}", f"fix:{repo}#20:{heads[1]}"])
        # The gate:keep-fixing label lifts the cap for one pull request: it
        # gets its fix round, the card of PR 24 is withdrawn, and the waiver
        # is journaled once per head. Without the label PR 23 is unchanged.
        waived = {f"fix:{repo}#24:{head}": "sent" for head in heads[:3]}
        act(24, heads[2], waived)
        exact(f"rounds-decision:{repo}#24" in waived, True)
        emitted = []
        with patch.object(lane.journal, "emit", lambda event, *a, **kw: emitted.append(event)):
            result = act(24, heads[3], waived, labels=["gate:keep-fixing"])
            act(24, heads[3], waived, verdict=("absent", None, ""), labels=["gate:keep-fixing"])
        exact(result.startswith("#24 fix:"), True)
        exact(f"fix:{repo}#24:{heads[3]}" in waived, True)
        exact(f"rounds-decision:{repo}#24" in waived, False)
        exact(emitted.count("gate_cap_waived"), 1)
        exact("lane-gate-rounds-shyamsivakumar-mac-ops-24" in [
            item["id"] for item in json.loads(board.read_text())["items"]], False)
        exact(lane.cap_waived({"labels": [{"name": "gate:keep-fixing"}]}), True)
        exact(lane.cap_waived({"labels": []}), False)
        # A capped pull request that later passes while the board removal
        # fails is not merged: the command stub raises on any merge call.
        # The ledger key stays, so the next pass retries the removal.
        passing = ("PASS", {"threadId": "gate"}, "VERDICT: PASS")
        with patch.object(lane.alarms, "board_update", return_value="failed"):
            result = act(20, heads[3], ledger, verdict=passing)
        exact("no merge until it is" in result, True)
        exact(f"rounds-decision:{repo}#20" in ledger, True)
        exact(len(json.loads(board.read_text())["items"]), 4)
        exact(lane.clear_gate_round_decision(repo, 20, ledger), True)
        exact(f"rounds-decision:{repo}#20" in ledger, False)
        exact(len(json.loads(board.read_text())["items"]), 3)

        # A first-review FAIL parks only when the pull request is over the
        # 150 code line cap, is not type:large or gate:whole, and the lead
        # finding of the report is the size stop. The files are read once
        # per head and the journal class is size only for the parked one.
        files = [{"filename": "a.py", "status": "modified", "additions": 200, "deletions": 0}]
        sized = ("FAIL", {"threadId": "gate"}, "Major — a.py:1 crosses the ticket's explicit 150-line stop.\n\nVERDICT: FAIL")
        buggy = ("FAIL", {"threadId": "gate"}, "Major — a.py:9 loses a write.\n\nThe diff also exceeds the 150-line limit.\n\nVERDICT: FAIL")
        before = list(sent)
        emitted = []
        with patch.object(lane.journal, "emit", lambda event, *a, **kw: emitted.append(kw)):
            fresh = {}
            exact(act(40, heads[0], fresh, verdict=sized), "parked")
            files = None
            exact(act(40, heads[0], fresh, verdict=sized), "parked")
        exact((parked, sent, fresh[f"size:{repo}#40:{heads[0]}"]), ([40, 40], before, "recut"))
        exact([row.get("class") for row in emitted if row.get("verdict") == "FAIL"], ["size"])
        exact(lane.route_for("size"), "recut")
        exact(lane.route_for("logic"), "today")
        files = [{"filename": "a.py", "status": "modified", "additions": 200, "deletions": 0}]
        act(41, heads[0], {}, verdict=sized, body="Partial: yes\n\n## Left for later\n\nthe rest")
        act(42, heads[0], {}, verdict=buggy)
        act(43, heads[0], {}, verdict=sized, issue_labels=["type:large"])
        act(44, heads[0], {}, verdict=sized, labels=["gate:whole"])
        files = [{"filename": "a.py", "status": "modified", "additions": 20, "deletions": 0}]
        act(45, heads[0], {}, verdict=sized)
        files = None
        act(46, heads[0], {}, verdict=sized)
        exact((parked, sent[len(before):]), ([40, 40], [f"fix:{repo}#{n}:{heads[0]}" for n in range(41, 47)]))

        check_pass = f"CHECK: PASS {heads[2]}"
        none_line = f"finding\n{check_pass}\n{lane.OPEN_FINDINGS_NONE}\nVERDICT: FAIL"
        merged = []

        def merge(repo_, number_, head_, base_):
            merged.append((number_, head_))
            return True, f"merged #{number_}"

        def at_cap(number, report):
            ledger = {f"fix:{repo}#{number}:{heads[0]}": "sent", f"fix:{repo}#{number}:{heads[1]}": "sent"}
            with patch.object(lane, "merge_on_reviewed_base", merge), \
                 patch.object(lane, "fast_forward_main", lambda r: None):
                result = act(number, heads[2], ledger, verdict=("FAIL", {"threadId": "gate"}, report))
            return result, ledger

        def round_item(number):
            return f"lane-gate-rounds-shyamsivakumar-mac-ops-{number}" in [
                item["id"] for item in json.loads(board.read_text())["items"]]

        # (a) round 3 FAIL with the none line merges, pinned at its head.
        result, _ = at_cap(30, none_line)
        exact(merged, [(30, heads[2])])
        exact(round_item(30), False)
        # (b) open findings stop at the round item.
        result, _ = at_cap(31, none_line.replace("none", "1"))
        exact(merged, [(30, heads[2])])
        exact(round_item(31), True)
        # (c) no such line stops at the round item.
        result, _ = at_cap(32, "finding\nMajor: x\nVERDICT: FAIL")
        exact(merged, [(30, heads[2])])
        exact(round_item(32), True)
        # The line must sit right before the final VERDICT line.
        at_cap(33, f"{lane.OPEN_FINDINGS_NONE}\nfinding\nVERDICT: FAIL")
        exact(merged, [(30, heads[2])])
        at_cap(37, f"finding\n{check_pass}\n{lane.OPEN_FINDINGS_NONE}  \n\nVERDICT: FAIL")
        exact(merged[-1], (37, heads[2]))
        merged.pop()
        # A failed or missing check, a wrong head, a leading space, or a
        # trailing token after the verdict never authorize the merge.
        bad = {
            38: f"CHECK: FAIL {heads[2]}\n{lane.OPEN_FINDINGS_NONE}\nVERDICT: FAIL",
            39: f"{lane.OPEN_FINDINGS_NONE}\nVERDICT: FAIL",
            40: f"CHECK: PASS {heads[1]}\n{lane.OPEN_FINDINGS_NONE}\nVERDICT: FAIL",
            41: f"{check_pass}\n {lane.OPEN_FINDINGS_NONE}\nVERDICT: FAIL",
            42: f"{check_pass}\n{lane.OPEN_FINDINGS_NONE}\nVERDICT: unknown VERDICT: FAIL",
            43: f"{check_pass}\nCHECK: FAIL {heads[2]}\n{lane.OPEN_FINDINGS_NONE}\nVERDICT: FAIL",
        }
        for number, report in bad.items():
            at_cap(number, report)
            exact(round_item(number), True)
        exact(merged, [(30, heads[2])])
        # A ledger key with no card on the board is not proof the card is
        # there: the item is raised again, and the ledger key stays. A
        # second pass finds the card and raises no second one.
        missing = {f"rounds:{repo}#24": {"count": 3, "head": heads[2]},
                   f"rounds-decision:{repo}#24": "lane-gate-rounds-shyamsivakumar-mac-ops-24"}
        result = act(24, heads[3], missing, verdict=("absent", None, ""))
        exact(result, "#24: no fix round, the decisions item was raised again")
        exact(round_item(24), True)
        exact(f"rounds-decision:{repo}#24" in missing, True)
        result = act(24, heads[3], missing, verdict=("absent", None, ""))
        exact(result, "#24: no fix round, the decisions item is on the board")
        exact(sum(1 for item in json.loads(board.read_text())["items"]
                  if item["id"] == "lane-gate-rounds-shyamsivakumar-mac-ops-24"), 1)
        # (d) round 1 FAIL with the none line is a normal fix round.
        sent.clear()
        with patch.object(lane, "merge_on_reviewed_base", merge):
            act(34, heads[0], {}, verdict=("FAIL", {"threadId": "gate"}, none_line))
        exact(sent, [f"fix:{repo}#34:{heads[0]}"])
        exact(merged, [(30, heads[2])])
        # (e) a prompt PR with the none line waits for Shyam.
        with patch.object(lane, "prompt_pull", return_value=lane.prompt_paths.HOLD):
            result, _ = at_cap(35, none_line)
        exact(result, "skip #35: gate PASS, prompt change, Shyam merges")
        exact(merged, [(30, heads[2])])
        # A repository the owner does not build in is not asked on the board:
        # the lane writes the round cap to its ledger and coordq status lists it.
        import importlib.machinery, importlib.util
        loader = importlib.machinery.SourceFileLoader("coordq_status", str(Path(__file__).parents[1] / "bin" / "coordq"))
        coordq = importlib.util.module_from_spec(importlib.util.spec_from_loader("coordq_status", loader))
        loader.exec_module(coordq)
        cards = len(json.loads(board.read_text())["items"])
        key = f"roundcap:{repo}#50"
        two = {f"fix:{repo}#50:{head}": "sent" for head in heads[:2]}
        result = act(50, heads[2], two, board=False)
        exact(result.endswith("the round cap is on coordq status"), True)
        exact(len(json.loads(board.read_text())["items"]), cards)
        exact(f"rounds-decision:{repo}#50" in two, False)
        entry = two[key]
        exact({k: entry[k] for k in ("repo", "pr", "head", "rounds", "gate", "lines")},
              {"repo": repo, "pr": 50, "head": heads[2], "rounds": 3, "gate": "gate", "lines": None})
        exact([c["pr"] for c in coordq.round_caps({**two, f"roundcap:{repo}#4": "bad"})], [50])
        good = {"repo": repo, "pr": 7, "head": "h", "rounds": 3, "at": 1.5}
        bad = {f"roundcap:x#{i}": {**good, **change} for i, change in enumerate(
            ({"repo": 5}, {"pr": "7"}, {"pr": True}, {"rounds": 3.0}, {"rounds": True}, {"at": "1"}, {"at": None}))}
        exact([c["pr"] for c in coordq.round_caps({**bad, "roundcap:ok": good})], [7])
        entry["at"] = 1.0
        act(50, heads[2], two, verdict=("absent", None, ""), board=False)
        exact((two[key]["at"], two[key]["gate"]), (1.0, "gate"))
        act(50, heads[3], two, verdict=("absent", None, ""), board=False)
        exact((two[key]["head"], two[key]["at"] > 1.0), (heads[3], True))
        act(50, heads[3], two, labels=["gate:keep-fixing"], board=False)
        exact(key in two, False)
        act(50, heads[2], two, board=False)
        lane.clear_gate_round_decision(repo, 50, two)
        exact(key in two, False)
        dry = {f"fix:{repo}#50:{head}": "sent" for head in heads[:3]}
        exact(act(50, heads[2], dry, verdict=("absent", None, ""), board=False, dry=True),
              "DRY #50: no fix round, the round cap goes to coordq status")
        exact(key in dry, False)
        exact(len(json.loads(board.read_text())["items"]), cards)
        # A card an earlier version raised is taken off the board, and a
        # removal that fails is retried on the next pass.
        old = {f"fix:{repo}#51:{head}": "sent" for head in heads[:3]}
        act(51, heads[2], old)
        exact(round_item(51), True)
        with patch.object(lane, "CFG", {repo: {"build": "here"}, "o/r": {}}):
            exact((lane.round_cap_to_board(repo), lane.round_cap_to_board("o/r")), (True, False))
        with patch.object(lane.alarms, "board_update", return_value="failed"):
            result = act(51, heads[2], old, board=False)
        exact("could not be taken off the board" in result, True)
        exact((round_item(51), f"rounds-decision:{repo}#51" in old, f"roundcap:{repo}#51" in old), (True, True, True))
        act(51, heads[2], old, board=False)
        exact((round_item(51), f"rounds-decision:{repo}#51" in old, f"roundcap:{repo}#51" in old), (False, False, True))
        # A pass that read a repository's open list drops the keys of pull
        # requests no longer in it; a full or missing list is not read whole.
        for prs, left in (({repo: {"prs": [{"number": 1}]}}, [1]),
                          ({repo: {"prs": [{"number": n} for n in range(100, 100 + lane.OPEN_PR_LIMIT)]}}, [1, 2]),
                          ({}, [1, 2])):
            pruned = {f"roundcap:{repo}#{n}": {"repo": repo, "pr": n} for n in (1, 2)}
            lane.prune_round_caps({"repos": prs}, pruned)
            exact(sorted(v["pr"] for v in pruned.values()), left)
        pruned = {f"roundcap:{repo}#1": "bad", f"roundcap:{repo}#2": {"repo": repo, "pr": 1}, "other": "x"}
        lane.prune_round_caps({"repos": {}}, pruned)
        exact(sorted(pruned), ["other", f"roundcap:{repo}#2"])
    gatekeep_round_cap()
    prereview_gate_cases()
    publisher_status_outcomes()


def publisher_status_outcomes():
    """A publisher repo gates and merges only on its published status.

    The body line `Builder check: PASS <head>` stands in for the status in
    a repo that publishes none, and never in a repo that does."""
    import lane_driver as lane
    coordq = load_coordq()
    srw, other = "shyamsivakumar/strategy-replay-workbench", "shyamsivakumar/mac-ops"
    head = "a" * 40
    line = f"Builder check: PASS {head}"
    states = ("success", "failure", "error", "pending", "missing")

    class Run:
        def __init__(self, stdout=""):
            self.stdout, self.stderr, self.returncode = stdout, "", 0

    def case(repo, key, state, body_line):
        body = "Refs #10\n" + (line if body_line else "")
        pr = {"draft": False, "number": 20, "head": {"sha": head}, "body": body,
              "changed_files": 1, "base": {"ref": "main"}}
        statuses = [] if state == "missing" else [{"context": "srw/agent-check", "state": state}]

        def run(argv, **kwargs):
            endpoint = argv[-1]
            if argv[:3] == ["gh", "api", "user"]:
                return Run("me\n")
            if endpoint == f"repos/{repo}/pulls?state=open&per_page=100":
                return Run(json.dumps([[pr]]))
            if endpoint == f"repos/{repo}/commits/{head}/statuses?per_page=100":
                return Run(json.dumps([statuses]))
            if endpoint == f"repos/{repo}/issues/10/comments?per_page=100" or endpoint.endswith("/files?per_page=100"):
                return Run("[[]]")
            raise AssertionError(f"unexpected read: {endpoint}")

        with tempfile.TemporaryDirectory() as scratch, \
             patch.object(coordq, "DIR", scratch), \
             patch.object(coordq, "load_receipts", lambda: {}), \
             patch.object(coordq, "builder_thread_for_issue", return_value=None), \
             patch.object(coordq, "backstop_model", return_value={"instanceId": "fixture", "model": "m"}), \
             patch.object(coordq, "gate_proof", return_value=("none", "", "path")), \
             patch.object(coordq, "gate_prompt_state", return_value=coordq.prompt_paths.CLEAR), \
             patch.object(coordq, "gate_args", return_value={"modelSelection": {"instanceId": "fixture", "model": "m"}, "title": "t"}), \
             patch.object(coordq.gh_gateway, "run", run), \
             patch.object(coordq.gh_gateway, "remaining_or_none", return_value=None), \
             contextlib.redirect_stderr(io.StringIO()):
            events = [e["kind"] for e in coordq.gate_candidates({"repos": {repo: {"key": key, "projectId": "fixture"}}}, {})]
        publisher = repo == srw or bool(statuses)
        gated = state == "success" if publisher else body_line
        exact(events, ["candidate"] if gated else (["skip"] if repo == srw else []))

        rollup = [{"context": "srw/agent-check", "state": state.upper()}] if statuses else []
        row = dict(number=20, state="OPEN", headRefOid=head, headRefName="builder/x", baseRefName="main",
                   labels=[], mergeable="MERGEABLE", body=body, statusCheckRollup=rollup)
        sent, merges = [], []
        with patch.object(lane, "CFG", {repo: dict(key=key, projectId="fixture")}), \
             patch.object(lane, "SNAPSHOT", {"repos": {repo: {"prs": [row], "issues": []}}}), \
             patch.object(lane, "builder_thread", return_value=("10", "live-builder")), \
             patch.object(lane, "superseded_by", return_value=False), \
             patch.object(lane, "issue_record", return_value={}), patch.object(lane, "issue_held", return_value=False), \
             patch.object(lane, "gate_verdict", return_value=("PASS", {"threadId": "gate"}, "VERDICT: PASS")), \
             patch.object(lane, "read_json", pr_reads(lane, row)), \
             patch.object(lane, "send", lambda *a, **k: sent.append(a[1]) or "sent"), \
             patch.object(lane, "merge_passed_pr", lambda *a: merges.append(a[2]) or "merged"):
            lane.act_on_pr(repo, 20, {})
        if repo == srw and state == "missing" and not body_line:
            bare = {**row, "body": "Refs #10"}
            exact(lane.pr_action(bare, "builder", repo=None), ("check-missing", "check"))
            exact(lane.pr_action(bare, "builder", repo=srw), ("check-missing", "none"))
        exact((bool(merges), len(sent)), (gated, int(publisher and state == "failure" or not publisher and not body_line)))

    for repo, key in ((srw, "SRW"), (other, "FIX")):
        for state in states:
            for body_line in (True, False):
                case(repo, key, state, body_line)


def gatekeep_retarget():
    """A head gated on one base is gated again once the pull request moves to another.

    The recorded gate reviewed `main`. The pull request now targets `other`
    with the same head, so gatekeep queues one new gate for that base, and
    the next run queues nothing more while that gate waits to launch.
    """
    coordq = load_coordq()
    repo = "shyamsivakumar/mac-ops"
    head = "a" * 40
    pr = {"draft": False, "number": 20, "head": {"sha": head}, "body": f"Refs #10\nBuilder check: PASS {head}\n",
          "changed_files": 1, "base": {"ref": "other"}}
    plain = f"gate:{repo}#20:{head}"
    receipt = {"kind": "receipt", "attempt": 1, "requestId": "req-1"}
    comment = {"user": {"login": "me"}, "body": "attempt 1\n<!-- coordinator-ticket " + json.dumps(receipt) + " -->"}
    receipts = {"req-1": "builder-1", plain: "gate", "base:gate": "main"}

    class Run:
        def __init__(self, stdout=""):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = 0

    def run(argv, **kwargs):
        if argv[:3] == ["gh", "api", "user"]:
            return Run("me\n")
        endpoint = argv[-1]
        if endpoint == f"repos/{repo}/pulls?state=open&per_page=100":
            return Run(json.dumps([[pr]]))
        if endpoint == f"repos/{repo}/issues/10/comments?per_page=100":
            return Run(json.dumps([[comment]]))
        if endpoint == f"repos/{repo}/commits/{head}/statuses?per_page=100":
            return Run("[[]]")
        if endpoint.endswith("/files?per_page=100"):
            return Run("[[]]")
        raise AssertionError(f"unexpected read: {endpoint}")

    def gatekeep(scratch):
        with patch.object(coordq, "DIR", scratch), \
             patch.object(coordq, "load_receipts", lambda: receipts), \
             patch.object(coordq.gh_gateway, "run", run), \
             patch.object(coordq.gh_gateway, "remaining_or_none", return_value=None), \
             patch.object(coordq, "read_builder_thread", return_value=({"providerInstanceId": "fixture", "model": "m"}, [])), \
             patch.object(coordq, "router_chain", return_value=[]), \
             patch.object(coordq, "gate_proof", return_value=("none", "", "path")), \
             patch.object(coordq, "gate_prompt_state", return_value=coordq.prompt_paths.CLEAR), \
             patch.object(coordq, "backstop_model", return_value={"instanceId": "fixture", "model": "m"}), \
             patch.object(coordq, "gate_args", return_value={"clientRequestId": plain, "modelSelection": {"instanceId": "fixture", "model": "m"}, "title": "t"}), \
             patch.object(coordq.model_list, "is_blocked", return_value=False), \
             contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            settings = Path(scratch) / "gatekeep-config.json"
            settings.write_text(json.dumps({"repos": {repo: {"key": "FIX", "projectId": "fixture"}}}))
            coordq.cmd_gatekeep(argparse.Namespace(config=str(settings), dry_run=False))
        return json.loads(Path(scratch, "queue.json").read_text())

    with tempfile.TemporaryDirectory() as scratch:
        queue = gatekeep(scratch)
        exact([item["args"]["clientRequestId"] for item in queue["items"]], [f"{plain}:other"])
        exact(list(queue["gatedHeads"]), [f"{plain}:other"])
        exact(len(gatekeep(scratch)["items"]), 1)


def prereview_gate_cases():
    """A head that touches loop code waits for its pre-review, and a pre-review that cannot finish never holds the gate."""
    coordq = load_coordq()
    repo = "shyamsivakumar/mac-ops"
    head = "b" * 40
    gate_key = f"gate:{repo}#30:{head}"
    key = f"prereview:{repo}#30:{head}"
    settings = {"key": "MO", "projectId": "p"}
    loop = {"head": head, "paths": ["coordinator/bin/coordq", "docs/x.md"], "builderModels": ["claude"]}
    other = {"head": head, "paths": ["coordinator/bin/journal.py"], "builderModels": ["claude"]}
    selection = {"instanceId": "codex", "model": "gpt-x"}
    thread = {"status": "running"}

    def gate(event=loop, dry=False):
        return coordq.prereview_gate(settings, repo, "30", event, gate_key, dry)

    def rows(scratch):
        found = []
        for name in sorted(os.listdir(scratch)):
            if name.endswith(".jsonl"):
                found += [json.loads(line)["event"] for line in Path(scratch, name).read_text().splitlines()]
        return found

    with tempfile.TemporaryDirectory() as scratch, \
         patch.object(coordq, "DIR", scratch), \
         patch.dict(os.environ, {"COORD_JOURNAL_DIR": scratch}), \
         patch.object(coordq, "reviewer_model", lambda models: selection), \
         patch.object(coordq, "call", lambda tool, args, rules=None: (0, json.dumps({"thread": thread}))):
        exact((gate(other), coordq.load().get("prereviewHeads")), (True, None))
        exact((gate(dry=True), coordq.load().get("prereviewHeads"), coordq.load()["items"]), (False, None, []))
        exact(gate(), False)
        queued = coordq.load()
        exact((len(queued["items"]), queued["items"][0]["args"]["clientRequestId"], queued["items"][0]["args"]["modelSelection"]),
              (1, key, selection))
        exact("List every failure path: missing data, unreadable input, stalled dependency, malformed reply." in queued["items"][0]["args"]["message"], True)
        Path(scratch, "dispatch-receipts.json").write_text(json.dumps({key: "thread-1"}))
        exact((gate(), len(coordq.load()["items"])), (False, 1))
        thread["status"] = "completed"
        exact((gate(), rows(scratch)), (True, ["prereview_queued"]))
        thread["status"] = "failed"
        exact((gate(), gate(), rows(scratch)), (True, True, ["prereview_queued", "prereview_skipped"]))
        with coordq.Lock(True):
            queue = coordq.load()
            queue["prereviewHeads"][key] = {"id": 1, "at": time.time()}
            coordq.save(queue)
        with patch.object(coordq, "call", lambda tool, args, rules=None: (1, "unreadable")):
            exact((gate(dry=True), coordq.load()["prereviewHeads"][key].get("skipped")), (True, None))
            exact((gate(), gate(), rows(scratch).count("prereview_skipped")), (True, True, 2))
        with coordq.Lock(True):
            queue = coordq.load()
            queue["prereviewHeads"][key] = {"id": 1, "at": time.time()}
            coordq.save(queue)
        with patch.object(coordq, "call", lambda tool, args, rules=None: (0, "not json")):
            exact((gate(), gate(), rows(scratch).count("prereview_skipped")), (True, True, 3))
        with coordq.Lock(True):
            queue = coordq.load()
            queue["prereviewHeads"][key] = {"id": 1, "at": time.time() - coordq.PREREVIEW_WAIT_SECONDS - 1}
            coordq.save(queue)
        thread["status"] = "running"
        exact((gate(dry=True), coordq.load()["prereviewHeads"][key].get("skipped")), (True, None))
        exact((gate(), gate(), rows(scratch).count("prereview_skipped")), (True, True, 4))
        with patch.object(coordq, "reviewer_model", lambda models: None):
            fresh = {**loop, "head": "c" * 40}
            exact((coordq.prereview_gate(settings, repo, "31", fresh, "gate:x", False), rows(scratch).count("prereview_skipped")), (True, 5))
        with coordq.Lock(True):
            queue = coordq.load()
            queue["gatedHeads"] = {gate_key: {}}
            queue["prereviewHeads"] = {}
            coordq.save(queue)
        exact((gate(), coordq.load()["prereviewHeads"]), (True, {}))


def overnight_act():
    """`overnight act` runs the lane's check for one pull request once its gate ends.

    It waits for the gate thread, takes the shift lock, and calls the lane's
    `act_on_pr` for that pull request only. STOP and a held lock leave the
    work to the scheduled pass.
    """
    import lane_driver as lane
    runner = load_runner()
    repo = "shyamsivakumar/mac-ops"
    calls = []

    def act(root, stop=False, lock=True):
        calls.clear()
        statuses = iter(["running", "completed"])
        (root / "run").mkdir(exist_ok=True)
        if stop:
            (root / "run" / "STOP").write_text("")
        (root / ".coordinator").mkdir(exist_ok=True)
        (root / ".coordinator" / "tickets.json").write_text(json.dumps({"repos": {repo: {"key": "MO"}}}))
        args = argparse.Namespace(ref=f"{repo}#7", after="thread-1", wait=900, root=str(root))
        with patch.object(runner, "load_policy", return_value=({"repos": [repo]}, "")), \
             patch.object(runner, "cycle_allow", return_value=[repo]), \
             patch.object(runner, "take_shift_lock", return_value=(3, "") if lock else (None, "")), \
             patch.object(runner, "release_shift_lock"), \
             patch.object(runner.time, "sleep"), \
             patch.object(runner.Path, "home", return_value=root), \
             patch.object(lane, "t3", side_effect=lambda tool, a: calls.append(tool) or {"thread": {"status": next(statuses, "completed")}}), \
             patch.object(lane, "load_ledger", return_value={}), \
             patch.object(lane, "save_ledger"), \
             patch.object(lane, "board_snapshot", return_value={}), \
             patch.object(lane, "act_on_pr", side_effect=lambda r, n, ledger: calls.append((r, n)) or "merged"), \
             patch.object(lane, "print", create=True), \
             patch.object(runner, "emit"), \
             patch.object(lane, "LANE_REPOS", [repo]):
            return runner.cmd_act(args)

    with tempfile.TemporaryDirectory() as scratch:
        exact(act(Path(scratch)), 0)
        exact(calls, ["t3_thread_read", "t3_thread_read", (repo, 7)])
    with tempfile.TemporaryDirectory() as scratch:
        exact((act(Path(scratch), stop=True), calls), (0, []))
    with tempfile.TemporaryDirectory() as scratch, patch.object(runner.time, "monotonic", side_effect=[0, 0, 1000, 1000, 1000]):
        exact((act(Path(scratch), lock=False), [c for c in calls if isinstance(c, tuple)]), (0, []))


def gatekeep_round_cap():
    """Gatekeep queues no gate for a pull request at the lane's round cap.

    The lane counts the failed gate reviews of a pull request in its
    ledger. Gatekeep reads that same count, so a pull request that used
    its rounds is skipped instead of gated again: SRW#1338 was gated ten
    times because every new head looked like a fresh candidate.
    """
    coordq = load_coordq()
    repo = "shyamsivakumar/strategy-replay-workbench"
    head = "3b7671c1" + "0" * 32
    pr = {"draft": False, "number": 1338, "head": {"sha": head},
          "body": f"Refs #1338\nBuilder check: PASS {head}\n",
          "changed_files": 1, "base": {"ref": "main"}}
    config = {"repos": {repo: {"key": "SRW", "projectId": "fixture"}}}

    class Run:
        def __init__(self, stdout=""):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = 0

    def run(argv, **kwargs):
        if argv[:3] == ["gh", "api", "user"]:
            return Run("me\n")
        endpoint = argv[-1]
        if endpoint == f"repos/{repo}/pulls?state=open&per_page=100":
            return Run(json.dumps([[pr]]))
        # A pull request at the cap is skipped before any other read, so
        # no other endpoint is asked for.
        raise AssertionError(f"unexpected read for a capped pull request: {endpoint}")

    def events(ledger):
        with tempfile.TemporaryDirectory() as scratch, \
             patch.object(coordq, "DIR", scratch), \
             patch.object(coordq, "LANE_LEDGER", str(Path(scratch) / "lanes-ledger.json")), \
             patch.object(coordq.gh_gateway, "run", run), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            Path(scratch, "lanes-ledger.json").write_text(json.dumps(ledger))
            found = list(coordq.gate_candidates(config, coordq.lane_ledger()))
        return found, errors.getvalue()

    def gatekeep(ledger):
        """One gatekeep run over a scratch queue, and what it queued."""
        with tempfile.TemporaryDirectory() as scratch, \
             patch.object(coordq, "DIR", scratch), \
             patch.object(coordq, "LANE_LEDGER", str(Path(scratch) / "lanes-ledger.json")), \
             patch.object(coordq.gh_gateway, "run", run), \
             patch.object(coordq.gh_gateway, "remaining_or_none", return_value=None), \
             contextlib.redirect_stderr(io.StringIO()) as errors, \
             contextlib.redirect_stdout(io.StringIO()):
            Path(scratch, "lanes-ledger.json").write_text(json.dumps(ledger))
            settings = Path(scratch) / "gatekeep-config.json"
            settings.write_text(json.dumps(config))
            coordq.cmd_gatekeep(argparse.Namespace(config=str(settings), dry_run=False))
            queue = json.loads(Path(scratch, "queue.json").read_text())
        return queue, errors.getvalue()

    # A ticket that cannot be read costs only its pull request: the next
    # pull request is still gated, and an exhausted API budget still stops
    # the pass.
    missing = {"draft": False, "number": 711, "head": {"sha": "d" * 40}, "title": "MO-1131 fix",
               "body": f"Refs #1131\nBuilder check: PASS {'d' * 40}\n", "changed_files": 1,
               "base": {"ref": "main"}}
    second = {"draft": False, "number": 712, "head": {"sha": "e" * 40},
              "body": f"Builder check: PASS {'e' * 40}\n", "changed_files": 1, "base": {"ref": "main"}}

    def unreadable_run(argv, **kwargs):
        if argv[:3] == ["gh", "api", "user"]:
            return Run("me\n")
        endpoint = argv[-1]
        if endpoint == f"repos/{repo}/pulls?state=open&per_page=100":
            return Run(json.dumps([[missing, second]]))
        if endpoint == f"repos/{repo}/issues/1131/comments?per_page=100":
            failed = Run()
            failed.returncode = 1
            failed.stderr = "gh: Not Found (HTTP 404)"
            return failed
        if endpoint in (f"repos/{repo}/commits/{'d' * 40}/statuses?per_page=100",
                        f"repos/{repo}/commits/{'e' * 40}/statuses?per_page=100"):
            return Run(json.dumps([[{"context": "srw/agent-check", "state": "success"}]]))
        if endpoint.endswith("/files?per_page=100"):
            return Run("[[]]")
        raise AssertionError(f"unexpected read: {endpoint}")

    def unreadable_events(run_stub):
        with tempfile.TemporaryDirectory() as scratch, \
             patch.object(coordq, "DIR", scratch), \
             patch.object(coordq.gh_gateway, "run", run_stub), \
             patch.object(coordq, "gate_proof", return_value=("none", "", "path")), \
             patch.object(coordq, "gate_prompt_state", return_value=coordq.prompt_paths.CLEAR), \
             patch.object(coordq, "backstop_model", return_value={"instanceId": "fixture", "model": "m"}), \
             patch.object(coordq, "gate_args", return_value={}), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            return list(coordq.gate_candidates(config, {})), errors.getvalue()

    found, errors = unreadable_events(unreadable_run)
    exact([(event["kind"], event["pr"]) for event in found],
          [("skip", f"{repo}#711"), ("candidate", f"{repo}#712")])
    reason = "Refs #1131 cannot be read (issue #1131 does not exist; a ticket key number used as an issue number?)"
    exact(found[0]["reason"], reason)
    exact(f"skip {repo}#711: {reason}" in errors, True)

    def exhausted_run(argv, **kwargs):
        if argv[-1] == f"repos/{repo}/issues/1131/comments?per_page=100":
            raise coordq.gh_gateway.ApiBudgetExhausted("quota could not be read")
        return unreadable_run(argv, **kwargs)

    try:
        unreadable_events(exhausted_run)
    except coordq.gh_gateway.ApiBudgetExhausted:
        pass
    else:
        raise AssertionError("an exhausted API budget must stop the pass")
    # The SRW#1338 shape: ten failed rounds, a new head, no gate queued.
    found, errors = events({f"rounds:{repo}#1338": {"count": 10, "head": "a" * 40}})
    exact([event["kind"] for event in found], ["skip"])
    exact(found[0]["reason"], "at the gate round cap")
    exact(f"skip {repo}#1338: at the gate round cap, no gate queued" in errors, True)
    # The command that owns the run reads the ledger and passes it in, so
    # the real gatekeep path queues no gate for the capped pull request.
    queue, errors = gatekeep({f"rounds:{repo}#1338": {"count": 10, "head": "a" * 40}})
    exact(queue["items"], [])
    exact(queue["gatekeepSkips"][f"{repo}#1338"]["reason"], "at the gate round cap")
    exact(f"skip {repo}#1338: at the gate round cap, no gate queued" in errors, True)
    # Three failed rounds is the cap itself, and three fix rounds count the
    # same way the lane counts them.
    for ledger in ({f"rounds:{repo}#1338": {"count": 3}},
                   {f"fix:{repo}#1338:{head}": "sent",
                    f"fix:{repo}#1338:{'b' * 40}": "sent",
                    f"fix:{repo}#1338:{'c' * 40}": "sent"}):
        found, _ = events(ledger)
        exact([event["kind"] for event in found], ["skip"])
    # Under the cap the pull request is still gated, and a ledger that
    # cannot be read is no reason to stop the gate.
    for ledger in ({f"rounds:{repo}#1338": {"count": 2}}, {},
                   {"rounds:other/repo#1": {"count": 9}}):
        with tempfile.TemporaryDirectory() as scratch, \
             patch.object(coordq, "LANE_LEDGER", str(Path(scratch) / "lanes-ledger.json")):
            Path(scratch, "lanes-ledger.json").write_text(json.dumps(ledger))
            exact(coordq.gate_rounds_used(repo, 1338, coordq.lane_ledger()), False)
    with tempfile.TemporaryDirectory() as scratch, \
         patch.object(coordq, "LANE_LEDGER", str(Path(scratch) / "missing.json")):
        exact(coordq.lane_ledger(), {})
        exact(coordq.gate_rounds_used(repo, 1338, coordq.lane_ledger()), False)
        Path(scratch, "corrupt.json").write_text("{not json")
        with patch.object(coordq, "LANE_LEDGER", str(Path(scratch) / "corrupt.json")):
            exact(coordq.lane_ledger(), {})


def decisions_board_guard():
    """A test run never writes the board Shyam reads, and settled cards leave it.

    The lane raises one item on the decisions board when a pull request
    uses its review rounds. The board path comes from the environment, so
    a test points it at a scratch file. This eval runs the path that
    raises the item and checks that every write names the scratch file as
    its destination. The board Shyam reads is not compared before and
    after, because the coordinator may publish to it while this runs.

    The same eval replays the settled cards this ticket names: four
    gate-rounds cards whose pull requests are closed, and one close-failed
    card whose ticket is closed. A gate-rounds card for an open pull
    request stays, a prompt-merge card is still withdrawn, a dry run writes
    nothing, and a card whose state cannot be read stays.
    """
    import lane_driver as lane
    targets = []
    real_update = lane.alarms.board_update

    def record(target, *args, **kwargs):
        targets.append(str(target))
        return real_update(target, *args, **kwargs)

    with tempfile.TemporaryDirectory() as scratch:
        board = Path(scratch) / "decisions.json"
        board.write_text(json.dumps({"items": []}))
        with patch.object(lane, "DECISIONS_PATH", str(board)), \
                patch.object(lane, "CFG", {"fixture/repo": {"build": "here"}}), \
                patch.object(lane.alarms, "board_update", record):
            lane.gate_round_decision("fixture/repo", 20, "a" * 40, {})
            lane.gate_round_decision("fixture/repo", 20, "a" * 40, {})
        items = json.loads(board.read_text())["items"]
        exact(targets, [str(board)] * 2)
        exact(len(items), 1)
        exact(items[0]["id"], "lane-gate-rounds-fixture-repo-20")

    repo = "shyamsivakumar/mac-ops"
    settled = [f"lane-gate-rounds-shyamsivakumar-mac-ops-{number}" for number in (602, 623, 625, 627)]
    settled += ["lane-close-failed-MO-661", "prompt-merge-MO-544",
                "recut-MO-868", "proof-MO-882", "herdr-build-MO-890"]
    kept = ["lane-gate-rounds-shyamsivakumar-mac-ops-700", "lane-close-failed-MO-702",
            "recut-MO-700", "proof-MO-901", "herdr-build-MO-700"]
    # The close-failed title is the one `close_failed_item` writes, and it
    # names the ticket the close was for.
    def close_failed_title(pr, ticket):
        return (f"MO-{pr} is merged at head 12345678 but closing MO-{ticket} failed: "
                "check why and close the ticket yourself.")
    cards = [{"id": card} for card in settled + kept]
    cards[settled.index("lane-close-failed-MO-661")]["title"] = close_failed_title(661, 660)
    open_card = cards[len(settled) + 1]
    open_card["title"] = close_failed_title(702, 701)
    snapshot = {"repos": {repo: {"prs": [{"number": 700}]}}}
    closed_prs = {602, 623, 625, 627, 544, 868, 882, 890}
    closed_tickets = {660}

    def read(cmd, timeout=150):
        kind, number = cmd[1], int(cmd[3])
        if kind == "pr":
            return json.dumps({"state": "CLOSED" if number in closed_prs else "OPEN",
                               "mergedAt": None})
        return json.dumps({"state": "CLOSED" if number in closed_tickets else "OPEN"})

    taken = []

    def withdraw(item_id):
        taken.append(item_id)
        return "wrote"

    def reconcile(runner=read, dry=False):
        taken.clear()
        with patch.object(lane, "CFG", {repo: {"key": "MO", "projectId": "fixture"}}), \
                patch.object(lane, "DRY", dry), \
                patch.object(lane, "run", runner), \
                patch.object(lane.alarms, "read_board", return_value=(b"", {"items": cards})), \
                patch.object(lane, "withdraw_decision", withdraw):
            return lane.reconcile_prompt_items(snapshot)

    # The settled cards this ticket names are withdrawn, and the prompt-merge
    # card is still withdrawn. The open pull request and the open ticket keep
    # their cards.
    exact(reconcile(), len(settled))
    exact(sorted(taken), sorted(settled))
    # A dry run writes nothing and reads nothing.
    exact(reconcile(dry=True), 0)
    exact(taken, [])
    # A state that did not come back is not a settled card.
    def broken(cmd, timeout=150):
        raise RuntimeError("gh failed")
    exact(reconcile(runner=broken), 0)
    exact(taken, [])
    # A close-failed card whose title names no ticket stays.
    open_card["title"] = "MO-702 is merged but the close failed."
    exact(reconcile(), len(settled))
    exact("lane-close-failed-MO-702" in taken, False)
    open_card["title"] = close_failed_title(702, 701)
    # A close-failed card whose ticket is still open stays.
    closed_tickets.clear()
    exact(reconcile(), len(settled) - 1)
    exact("lane-close-failed-MO-661" in taken, False)
    closed_tickets.add(660)
    # A card this cleanup does not own is left alone.
    cards.append({"id": "unrelated"})
    exact(reconcile(), len(settled))
    exact("unrelated" in taken, False)
    # A merged-unreviewed card is withdrawn once the ticket it names is closed.
    def unreviewed_title(pr, ticket):
        return (f"MO-{pr} is merged at head 12345678 without a gate PASS the lane can tie to the merge, "
                f"so its ticket stays open (ticket MO-{ticket}): check the merge and close the ticket yourself.")
    cards[:] = [{"id": "lane-merged-unreviewed-MO-663", "title": unreviewed_title(663, 659)},
                {"id": "lane-merged-unreviewed-MO-703", "title": unreviewed_title(703, 701)}]
    closed_tickets.clear()
    closed_tickets.add(659)
    exact(reconcile(), 1)
    exact(taken, ["lane-merged-unreviewed-MO-663"])


def send_integrity():
    import lane_driver as lane
    repo = "shyamsivakumar/mac-ops"
    key = f"fix:{repo}#385:head"
    cases = [(dict(status=status), True) for status in
             ("running", "waiting", "queued", "starting", "preparing", "completed", "interrupted", "failed")]
    cases += [(thread, False) for thread in ({}, dict(status="deleted"),
              dict(status="running", archived=True), dict(status="running", sendable=False),
              dict(status="running", canSend=False))]
    for thread, live in cases:
        for failure in (None, "error", "empty"):
            actions, reads, ledger = [], [], {}
            def read(tool, args):
                exact((tool, args), ("t3_thread_read", {"threadId": "old", "limit": 1}))
                reads.append("read")
                return {"thread": {**fixer_identity(), **thread}}
            def command(cmd, timeout=150):
                exact(reads, ["read"])
                exact(cmd[:2], [lane.COORDQ, "start"])
                payload = json.loads(cmd[2])
                if live:
                    exact(payload, {"threadId": "old", "message": "brief"})
                    exact(cmd[3:], ["--tool", "t3_thread_send", "--priority", "800", "--title", "fix"])
                else:
                    exact(payload, {"projectId": "fixture", "title": "fix", "taskType": "fix", "modelSelection": lane.model_list.first_available("fix")["selection"],
                          "runtimeMode": "full-access", "workspaceStrategy": {"type": "worktree", "baseRef": "origin/builder/fixture", "startFromOrigin": True}, "message": "brief", "clientRequestId": key})
                    exact(cmd[3:], ["--priority", "800"])
                actions.append("send" if live else "fresh")
                if failure == "error":
                    raise subprocess.CalledProcessError(1, cmd)
                return "" if failure == "empty" else "receipt"
            output = io.StringIO()
            with patch.object(lane, "CFG", {repo: {"projectId": "fixture"}}), \
                 patch.object(lane, "DRY", False), patch.object(lane, "t3", read), \
                 patch.object(lane, "read_json", side_effect=pr_reads(lane, dict(number=385, state="OPEN", headRefName="builder/fixture", baseRefName="main"))), \
                 patch.object(lane, "run", command), contextlib.redirect_stdout(output):
                try:
                    result = lane.send("old", "brief", "fix", ledger, key, repo=repo, pr_number=385)
                except (subprocess.CalledProcessError, RuntimeError):
                    exact(failure in ("error", "empty"), True)
                    exact(ledger, {})
                else:
                    exact(failure, None)
                    exact(ledger, {key: "receipt"})
                    exact(result, "receipt" if live else "fresh (old unreachable): receipt")
                    exact(output.getvalue(), "" if live else "SEND REROUTE old: receipt\n")
                exact(actions, ["send" if live else "fresh"])
    with patch.object(lane, "DRY", True), \
         patch.object(lane, "t3", return_value={"thread": {**fixer_identity(), "status": "running"}}), \
         patch.object(lane, "run", side_effect=AssertionError("dry dispatch")):
        ledger = {}
        exact(lane.send("old", "brief", "fix", ledger, key), f"DRY {key}: send existing thread")
        exact(ledger, {})

    snapshot = {"repos": {repo: {"issues": [{"number": 385, "labels": []}], "prs": []}}}
    from unittest.mock import mock_open
    for failure in (False, True):
        ledger, actions = {}, []
        def files(path, *args, **kwargs):
            data = json.dumps({f"ticket:{repo}#385:a1": "old"}) if path == lane.RECEIPTS else "brief"
            return mock_open(read_data=data)()
        def command(cmd, timeout=150):
            exact(json.loads(cmd[2])["projectId"], "fixture")
            exact("t3_thread_send" in cmd, False)
            actions.append("fresh")
            if failure:
                raise subprocess.CalledProcessError(1, cmd)
            return "receipt"
        with patch.object(lane, "SNAPSHOT", snapshot), \
             patch.object(lane, "CFG", {repo: {"projectId": "fixture", "key": "MO"}}), \
             patch.object(lane, "DRY", False), patch("builtins.open", files), \
             patch.object(lane, "t3", return_value={"thread": {"status": "deleted"}}), \
             patch.object(lane, "run", command):
            result = lane.unstick(repo, ledger)
        exact(actions, [])
        exact(f"cont:old" in ledger, True)
        if failure:
            exact("started" in result, False)
        else:
            exact(result, f"continue #385: skip continue:{repo}#385:old: no verified PR branch for relaunch")

    coordq = load_coordq()
    from argparse import Namespace
    old, new = "a" * 40, "b" * 40

    def queued(item_id, title, thread="t1", key=None):
        item = {"id": item_id, "messageTitle": title, "args": {"threadId": thread}}
        if key:
            item["actionKey"] = key
        return item

    started = [{"id": 9, "title": f"SRW#7 check {old}", "target": "t1"}]

    def older_heads(items, keys, title, below=None, reserved=None):
        queue = {"items": list(items), "started": started, "reserved": reserved or {},
                 "actionKeys": {key: {"id": 1, "state": "queued"} for key in keys}}
        dropped = coordq.drop_older_heads(queue, title, below)
        exact(queue["started"], started)
        return dropped, [item["id"] for item in queue["items"]], sorted(queue["actionKeys"])

    items = [queued(1, f"SRW#7 check {old}", key="k1"), queued(2, f"SRW#7 gate findings {old}"),
             queued(3, f"SRW#7 continue {new}", thread="t2"), queued(4, f"SRW#8 check {old}"),
             queued(5, f"SRW#7 check {old}", thread="t2"), queued(6, f"gate:SRW#7:{old}"),
             queued(7, f"SRW#7 check {old}")]
    exact(older_heads(items, ["k1"], f"SRW#7 continue {new}"), (4, [3, 4, 6], []))
    exact(older_heads(items, ["k1"], f"SRW#7 continue {new}", 7), (3, [3, 4, 6, 7], []))
    exact(older_heads(items, [], f"SRW#7 continue {new}", reserved={"2": 1, "7:send": 1}),
          (2, [2, 3, 4, 6, 7], []))
    exact(older_heads(items, [], f"SRW#7 continue {old}")[0], 1)
    for other in ("SRW#7 continue", f"SRW#7 retry {new}", f"SRW#7 continue {new[:39]}", f"gate:SRW#7:{new}", ""):
        exact(older_heads(items, [], other)[0], 0)

    repos = {"repos": {"o/one": {"key": "SRW"}, "o/two": {"key": "MO"}, "o/three": {"key": "MO"}}}

    def read_head(config, run):
        with tempfile.TemporaryDirectory() as scratch:
            file = Path(scratch, "tickets.json")
            file.write_text(config if isinstance(config, str) else json.dumps(config))
            with patch.object(coordq, "TICKETS_CONFIG", str(file)), \
                 patch.object(coordq.gh_gateway, "run", side_effect=run) as gh:
                return coordq.current_head(f"SRW#7 check {old}"), gh.call_args_list

    def answer(stdout, code=0):
        return lambda *args, **kwargs: subprocess.CompletedProcess(args[0], code, stdout, "")

    def raising(error):
        def run(*args, **kwargs):
            raise error
        return run

    failures = (answer("not json"), answer("{}"), answer("", 1), raising(subprocess.TimeoutExpired("gh", 40)),
                raising(OSError("gh missing")), raising(coordq.gh_gateway.ApiBudgetExhausted("budget")))

    head, calls = read_head(repos, answer(json.dumps({"head": {"sha": new}})))
    exact(head, new)
    exact([(c.args, c.kwargs) for c in calls], [((["gh", "api", "repos/o/one/pulls/7"],), {"timeout": 40, "fresh": True})])
    for bad in failures:
        exact(read_head(repos, bad)[0], None)
    exact(read_head("{broken", answer("{}"))[0], None)
    exact(read_head({"repos": {"o/one": {"key": "X"}}}, answer("{}")), (None, []))
    exact(read_head({"repos": {"o/one": {"key": "SRW"}, "o/two": {"key": "SRW"}}}, answer("{}")), (None, []))

    def start(runner, key=None, thread="t1", head=new, queued_items=items):
        args = json.dumps({"threadId": thread, "message": "m"})
        with tempfile.TemporaryDirectory() as scratch, \
             patch.dict(os.environ, {"COORDQ_DIR": scratch, "COORD_JOURNAL_DIR": scratch}), \
             patch.object(coordq, "DIR", scratch), patch.object(coordq, "drain"), \
             patch.object(coordq, "TICKETS_CONFIG", str(Path(scratch, "tickets.json"))), \
             patch.object(coordq.gh_gateway, "run", side_effect=runner) as gh, \
             patch.object(coordq, "flush_provider_blocks"), contextlib.redirect_stdout(io.StringIO()):
            Path(scratch, "tickets.json").write_text(json.dumps(repos))
            coordq.save({"next": 8, "items": [dict(item) for item in queued_items],
                         "actionKeys": {"k1": {"id": 1, "state": "queued"}}})
            try:
                coordq.cmd_start(Namespace(args=args, tool="t3_thread_send", title=f"SRW#7 continue {head}",
                                           priority=800, action_key=key))
            except SystemExit:
                pass
            return [item["id"] for item in coordq.load()["items"]], gh.call_count

    current = answer(json.dumps({"head": {"sha": new}}))
    exact(start(current), ([3, 4, 6, 8], 1))
    exact(start(current, thread="t3"), ([3, 4, 6, 8], 1))
    exact(start(current, head=old), (list(range(1, 9)), 1))
    exact(start(answer(json.dumps({"head": {"sha": old}}))), (list(range(1, 9)), 1))
    exact(start(current, key="k1"), (list(range(1, 8)), 1))
    exact(start(current, queued_items=items[2:4]), ([3, 4, 8], 0))
    for broken in failures:
        exact(start(broken), (list(range(1, 9)), 1))


def build_here():
    import lane_driver as lane
    coordq = load_coordq()
    repo = "shyamsivakumar/mac-ops"
    other = "shyamsivakumar/scrapers"
    rows = [{"number": number, "repository": {"nameWithOwner": name}, "labels": [{"name": "stage:todo"}], "body": ""}
            for number, name in ((1, repo), (2, repo), (3, other))]
    with tempfile.TemporaryDirectory() as scratch:
        with patch.object(coordq, "DIR", scratch):
            picked = coordq.lane_candidates(rows, set(), {}, {repo})
            exact([row["number"] for row in picked], [3])
            exact(Path(scratch, "dispatch.log").read_text().splitlines()[-1].split(" ", 2)[2],
                  f"refill: skipped 2 build-here tickets in {repo}")
        sent = []
        head = "a" * 40
        with scratch_board(scratch) as decisions:
            def send(*args, **kwargs):
                sent.append(args[4])
                return "sent"
            for pr_fields, verdict in (({"mergeable": "CONFLICTING"}, ("none", None, "")),
                                       ({"body": "Refs #10"}, ("none", None, "")),
                                       ({}, ("FAIL", {"threadId": "gate"}, "finding\nVERDICT: FAIL"))):
                pr = {**dict(number=20, state="OPEN", headRefOid=head, mergeable="MERGEABLE",
                             body=f"Refs #10\nBuilder check: PASS {head}"), **pr_fields}
                snapshot = {"repos": {repo: {"prs": [pr], "issues": [dict(number=10, labels=[])]}}}
                with patch.object(lane, "CFG", {repo: dict(key="MO", projectId="fixture", build="here")}), \
                     patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "DRY", False), \
                     patch.object(lane, "builder_thread", return_value=("10", "live-builder")), \
                     patch.object(lane, "gate_verdict", return_value=verdict), \
                     patch.object(lane, "read_json", side_effect=pr_reads(lane, dict(number=20, state="OPEN", headRefName="builder/fixture", baseRefName="main"))), \
                     patch.object(lane, "run", side_effect=AssertionError("live command forbidden")), \
                     patch.object(lane, "t3", return_value={"thread": {"status": "completed"}}), \
                     patch.object(lane, "send", send):
                    exact(lane.act_on_pr(repo, 20, {}), f"#20: {repo} is built in the Herdr session, board card raised")
            exact(sent, [])
            card_id = "herdr-build-MO-20"
            owner_board = Path(lane.alarms.board_for(decisions, card_id))
            exact(bool(lane.alarms.OWNER_IDS.fullmatch(card_id)), True)
            exact(owner_board, decisions.with_name("mac-ops-owner.json"))
            exact(json.loads(decisions.read_text())["items"], [])
            items = json.loads(owner_board.read_text())["items"]
            exact([item["id"] for item in items], [card_id])
            exact(head[:8] in items[0]["title"], True)
            for status, expect_card, pr_body in (("running", False, "Refs #10"), ("waiting", False, "Refs #10"),
                                                 ("completed", False, "Refs #10\nOwner: t1j"), ({}, True, "Refs #10")):
                pr = dict(number=21, state="OPEN", headRefOid=head, mergeable="MERGEABLE", body=pr_body)
                snapshot = {"repos": {repo: {"prs": [pr], "issues": [dict(number=10, labels=[])]}}}
                reply = {"thread": {"status": status}} if status != {} else {}
                ledger = {}
                with tempfile.TemporaryDirectory() as journal_dir, \
                     patch.dict(os.environ, {"COORD_JOURNAL_DIR": journal_dir}), \
                     patch.object(lane, "CFG", {repo: dict(key="MO", projectId="fixture", build="here")}), \
                     patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "DRY", False), \
                     patch.object(lane, "builder_thread", return_value=("10", "live-builder")), \
                     patch.object(lane, "gate_verdict", return_value=("none", None, "")), \
                     patch.object(lane, "read_json", side_effect=pr_reads(lane, dict(number=21, state="OPEN", headRefName="builder/fixture", baseRefName="main"))), \
                     patch.object(lane, "run", side_effect=AssertionError("live command forbidden")), \
                     patch.object(lane, "t3", return_value=reply):
                    first = lane.act_on_pr(repo, 21, ledger)
                    again = lane.act_on_pr(repo, 21, ledger)
                    cards = [item["id"] for board in decisions.parent.glob("*.json")
                             for item in json.loads(board.read_text())["items"] if item["id"] == "herdr-build-MO-21"]
                    rows = [json.loads(line) for line in Path(lane.journal.journal_path(time.time())).read_text().splitlines()
                            if "fix_skipped_owned" in line] if Path(lane.journal.journal_path(time.time())).exists() else []
                    exact(cards == ["herdr-build-MO-21"], expect_card)
                    exact(len(rows), 0 if expect_card else 1)
                    exact(first.startswith("skip #21"), not expect_card)
                    exact(again, first)
            pr = dict(number=22, state="OPEN", headRefOid=head, mergeable="MERGEABLE", body="Refs #10\nOwner: t1j")
            snapshot = {"repos": {repo: {"prs": [pr], "issues": [dict(number=10, labels=[])]}}}
            ledger = {}
            start = 1_800_000_000.0
            for hours, expect_card in ((0, False), (1, False), (7, True)):
                with tempfile.TemporaryDirectory() as journal_dir, \
                     patch.dict(os.environ, {"COORD_JOURNAL_DIR": journal_dir}), \
                     patch.object(lane, "CFG", {repo: dict(key="MO", projectId="fixture", build="here")}), \
                     patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "DRY", False), \
                     patch.object(lane.time, "time", return_value=start + hours * 3600), \
                     patch.object(lane, "builder_thread", return_value=("10", "ended-builder")), \
                     patch.object(lane, "gate_verdict", return_value=("none", None, "")), \
                     patch.object(lane, "read_json", side_effect=pr_reads(lane, dict(number=22, state="OPEN", headRefName="builder/fixture", baseRefName="main"))), \
                     patch.object(lane, "run", side_effect=AssertionError("live command forbidden")), \
                     patch.object(lane, "t3", return_value={"thread": {"status": "completed"}}):
                    result = lane.act_on_pr(repo, 22, ledger)
                    exact(result.startswith("skip #22"), not expect_card)
                    exact("herdr-build-MO-22" in [item["id"] for board in decisions.parent.glob("*.json")
                                                  for item in json.loads(board.read_text())["items"]], expect_card)
                    expired = "owner_grace_expired" in Path(lane.journal.journal_path(start + hours * 3600)).read_text() \
                        if Path(lane.journal.journal_path(start + hours * 3600)).exists() else False
                    exact(expired, expect_card)


def stale_started_refill():
    import lane_driver as lane
    from datetime import datetime, timezone
    repo = "shyamsivakumar/mac-ops"
    started = [{"name": "stage:started"}]
    snapshot = {"repos": {repo: {"issues": [
        {"number": 7, "title": "stale", "labels": started},
        {"number": 8, "title": "has pull request", "labels": started},
        {"number": 9, "title": "live builder", "labels": started},
        {"number": 10, "title": "ready", "labels": [{"name": "stage:todo"}]}],
        "prs": [{"number": 80, "body": "Refs #8"}]}}}
    receipts = json.dumps({f"ticket:{repo}#9:a1": "live"})
    def t3(tool, args):
        if tool == "t3_thread_read":
            return {"thread": {"status": "running"}}
        return {"threads": []}
    actions = []
    ages = {}
    def run_pass(dry):
        with tempfile.TemporaryDirectory() as scratch, \
             patch.dict(os.environ, {"COORD_JOURNAL_DIR": scratch}), \
             patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "t3", t3), \
             patch.object(lane, "CFG", {repo: {"projectId": "fixture", "key": "MO"}}), \
             patch.object(lane, "RECEIPTS", str(Path(scratch, "receipts.json"))), \
             patch.object(lane.time, "time", return_value=now), \
             patch.object(lane, "DRY", dry), \
             patch.object(lane, "run", lambda cmd, timeout=150: actions.append(cmd) or ""):
            Path(lane.RECEIPTS).write_text(receipts)
            Path(scratch, "events-2099-01.jsonl").write_bytes(b"\xff\xfe")
            Path(scratch, "events-2024-12.jsonl").write_text("not json\n")
            for number, ts in ages.items():
                with open(lane.journal.journal_path(ts), "a") as handle:
                    handle.write(json.dumps({"event": "ticket_started", "repo": repo,
                                             "ticket": number, "ts": ts}) + "\n")
            return lane.unstick(repo, {})
    now = datetime(2025, 3, 1, 0, 30, tzinfo=timezone.utc).timestamp()
    exact(run_pass(False), "nothing ready")
    ages[7] = now - 300
    exact(run_pass(False), "nothing ready")
    exact(actions, [])
    ages[7] = now - 7200
    exact(run_pass(True), "DRY release [7]")
    exact(actions, [])
    exact(run_pass(False), "release [7]")
    exact([cmd[2:3] + cmd[3:4] for cmd in actions], [["edit", "7"], ["comment", "7"]])
    exact("stage:todo" in actions[0] and "stage:started" in actions[0], True)
    actions.clear()
    ages[7] = now - 90 * 86400
    exact(run_pass(False), "release [7]")
    exact([cmd[2:4] for cmd in actions], [["edit", "7"], ["comment", "7"]])


def refill_busy():
    coordq = load_coordq()
    repo = "shyamsivakumar/mac-ops"
    started = [649, 633, 614, 611, 610, 607, 605, 591, 543, 530]
    page = [{"number": number, "labels": [{"name": label}], "body": "", "updated_at": "2026-11-19T22:50:00Z"}
            for label, numbers in (("stage:started", started), ("stage:todo", range(673, 682)))
            for number in numbers]
    def candidates(occupied, refs):
        with tempfile.TemporaryDirectory() as scratch:
            config = Path(scratch, "tickets.json")
            config.write_text(json.dumps({"repos": {repo: {}}}))
            with patch.object(coordq, "DIR", scratch), patch.object(coordq, "TICKETS_CONFIG", str(config)), \
                 patch.object(coordq, "live_lane_repositories", return_value=occupied), \
                 patch.object(coordq, "open_pr_refs", return_value=(refs, {})), \
                 patch.object(coordq.gh_gateway, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps([page]))):
                picked = [row["number"] for row in coordq.board_candidates()]
            log = Path(scratch, "dispatch.log")
            lines = [line.split(" ", 2)[2] for line in log.read_text().splitlines()] if log.exists() else []
            return picked, lines
    picked, lines = candidates(set(), {533, 514, 548, 576, 504, 505, 596, 662, 663, 671})
    exact(picked, list(range(673, 682)))
    exact(lines, [f"refill: #{number} is stage:started with no live thread or open PR" for number in started])
    exact(candidates({repo}, set())[0], [])
    exact(candidates(set(), {675})[0], [])
    todo = {"number": 1, "labels": [{"name": "stage:todo"}], "repository": {"nameWithOwner": "o/r"}}
    rows = [{**todo, "number": n, "title": f"SRW-{n} x"} for n in (1, 2, 3)] + [{**todo, "number": 4, "repository": {"nameWithOwner": "o/s"}}]
    picked = lambda *args: [row["number"] for row in coordq.lane_candidates(rows, *args)]
    exact(picked(set(), {}, (), {}, {"o/r": 2}), [1, 4, 2, 3])
    exact(picked({"o/r#1", "o/r#pr9", "o/r#SRW-1"}, {}, (), {"o/r": {9: {1}}}, {"o/r": 2}), [2, 4, 3])
    exact(picked({"o/r#1", "o/r#SRW-2"}, {}, (), {}, {"o/r": 2}), [4])
    exact(picked(set(), {"o/r": {1, 2}}, (), {"o/r": {5: {1, 2}}}, {"o/r": 2}), [3, 4])
    def refill_calls(limits, answer):
        calls = []
        three = coordq.Candidates([{**todo, "number": n, "title": str(n)} for n in (1, 2, 3)], [], (), {}, limits)
        with tempfile.TemporaryDirectory() as scratch, patch.object(coordq, "DIR", scratch), \
             patch.object(coordq, "board_candidates", return_value=three), patch.object(coordq, "used_slots", return_value=0), \
             patch.object(coordq, "cap", return_value=9), patch.object(coordq, "last_refill", return_value=None), \
             patch.object(coordq, "ticket_start", side_effect=lambda *args: calls.append(args) or answer):
            coordq.refill(SimpleNamespace(dry_run=False))
        return [call[1:] for call in calls]
    exact(refill_calls({"o/r": 1}, (1, "receipt comment failed")), [(1, False, False)])
    exact(refill_calls({"o/r": 1}, (0, "started")), [(1, False, False)])
    exact(refill_calls({"o/r": 2}, (0, "started")), [(1, False, False), (2, False, True)])
    exact(len(refill_calls({}, (2, "refused: no"))), 3)
    started = [{**todo, "number": n, "labels": [{"name": "stage:started"}]} for n in (5, 6, 7)]
    exact([row["number"] for row in coordq.stale_started(started, {"o/r#5", "o/r#pr9"}, {}, {"o/r": {9: {7}}})], [6])
    def limit(value):
        with tempfile.TemporaryDirectory() as scratch:
            config = Path(scratch, "tickets.json")
            config.write_text(json.dumps({"repos": {repo: {"lanes": value}}}))
            with patch.object(coordq, "DIR", scratch), patch.object(coordq, "TICKETS_CONFIG", str(config)), \
                 patch.object(coordq, "live_lane_repositories", return_value=set()), \
                 patch.object(coordq, "open_pr_refs", return_value=(set(), {})), \
                 patch.object(coordq.gh_gateway, "run", return_value=SimpleNamespace(returncode=0, stdout="[[]]")):
                return coordq.board_candidates().limits[repo]
    exact([limit(value) for value in (None, 0, -1, True, "2", 2)], [1, 1, 1, 1, 1, 2])
    exact(coordq.candidate_state(todo, {"a"}) == coordq.candidate_state(todo, {"b"}), False)
    exact(coordq.empty_board_reason([], ()), "refill stopped: the board has no open stage:todo ticket")
    exact(coordq.empty_board_reason([todo], ()), "refill stopped: 1 open stage:todo ticket waiting, and their repos are busy")
    exact(coordq.empty_board_reason([todo, {**todo, "number": 2}], ()).split(" ")[2], "2")
    exact(coordq.empty_board_reason([todo], {"o/r"}), coordq.empty_board_reason([], ()))
    ticket = load_ticket()
    scope = lambda *lines: "In:\n" + "\n".join(lines) + "\nOut: y\n"
    def overlap(own, others=(), pulls=(), alongside=True):
        listing = lambda args, **kwargs: [{"number": n, "body": b} for n, b in others] if args[0] == "issue" else \
            [{"number": n, "body": "", "files": [{"path": f} for f in files]} for n, files in pulls]
        with patch.object(ticket, "gh_json", listing):
            return ticket.scope_overlap("o/r", {"number": 1, "body": own}, alongside)
    proof = scope("- `scripts/a_proof.cjs`: x")
    exact(overlap(proof, [(2, proof)]), [(2, "scripts/a_proof.cjs")])
    exact(overlap(proof, [(2, proof)], alongside=False), [])
    exact(overlap(scope("- `a.py`, `b.py`, `c.py`: x"), [(2, scope("- `x.py`, `c.py`: y"))]), [(2, "c.py")])
    exact(overlap(scope("- `./a.py`: x"), [(2, scope("- `a.py`: y"))]), [(2, "a.py")])
    exact(overlap(scope("- `d/`: x"), [(2, scope("- `d/x.py`: y"))]), [(2, "d/x.py")])
    exact(overlap(scope("- `d/x.py`: x"), [(2, scope("- `d/`: y"))]), [(2, "d/")])
    exact(overlap(scope("- `d/x.py`: x"), [], [(9, ["d/x.py", "z.py"])]), [(9, "d/x.py")])
    exact(overlap(scope("- `a.py`: `runDrill()`, `--flag`, `stage:todo`, not `b.py`"), [(2, scope("- `b.py`: x"))]), [])
    exact(overlap(scope("- `a.py`: leaves `b.py` alone"), [(2, scope("- `b.py`: x"))]), [])
    exact(overlap(scope("- `a.py`, `evidence/MO-1/runs.md`: x"), [(2, scope("- `evidence/MO-1/runs.md`, `q.py`: y"))]), [])
    exact(ticket.scope_files(scope("- `a.py`, `b.py`: x", "- `x_proof.py`: y")), ["a.py"])
    exact(ticket.scope_files(scope("- `./a.py`: x")), ["./a.py"])
    try:
        overlap(scope("- `evidence/MO-1/runs.md`: x"))
    except ticket.Refuse as refused:
        exact(str(refused), "--alongside needs a Scope In that names a readable file")
    else:
        raise AssertionError("an evidence-only ticket must refuse")
    try:
        overlap(proof, [(2, "no names here")])
    except ticket.Refuse as refused:
        exact(str(refused), "#2 is started and names no files and has no open pull request")
    else:
        raise AssertionError("a started ticket with no names and no pull request must refuse")


def root_workspace():
    """Pull request work never works in the shared root of a repository.

    The lane sends pull request work to the builder thread of the ticket
    that opened the pull request. A thread that works in the shared root
    of the repository is refused: the work starts a fresh worktree
    instead, so the branch everyone installs from never moves. The lane
    also skips a herdr pull request and a pull request that is merged or
    closed, so neither ever reaches a thread.
    """
    import lane_driver as lane
    repo = "shyamsivakumar/mac-ops"
    root = "/Users/shyamsivakumar/Code/mac-ops"
    worktree = "/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-fixture"
    key = f"check:{repo}#512:head"
    # The root checkout of a repository keeps the common git directory of
    # the repository; a linked worktree keeps its own.
    root_git = ".git\n.git\n"
    worktree_git = ("/Users/shyamsivakumar/Code/mac-ops/.git/worktrees/t3-fixture\n"
                    "/Users/shyamsivakumar/Code/mac-ops/.git\n")
    other_root_git = ("/Users/shyamsivakumar/Code/strategy-replay-workbench/.git\n"
                      "/Users/shyamsivakumar/Code/strategy-replay-workbench/.git\n")

    def send_to(thread, pr=None, listing="abc123\trefs/heads/builder/fixture", git=worktree_git,
                worktree_only=True):
        actions = []
        def read(tool, args):
            return {"thread": {**fixer_identity(), **thread}}
        def command(cmd, timeout=150):
            if cmd[0] == "git":
                if "rev-parse" in cmd:
                    return git
                exact(cmd[1:4], ["-C", root, "ls-remote"])
                exact(cmd[4:], ["--heads", "origin", "builder/fixture"])
                return listing
            payload = json.loads(cmd[2])
            if payload.get("threadId"):
                actions.append("send")
            else:
                actions.append("fresh")
                exact(payload["workspaceStrategy"], {"type": "worktree", "baseRef": "origin/builder/fixture",
                                                     "startFromOrigin": True})
            return "receipt"
        pull = pr or dict(number=512, state="OPEN", headRefName="builder/fixture", baseRefName="main")
        with patch.object(lane, "CFG", {repo: {"projectId": "fixture"}}), \
             patch.object(lane, "DRY", False), patch.object(lane, "t3", read), \
             patch.object(lane, "read_json", side_effect=pr_reads(lane, pull)), \
             patch.object(lane, "run", command), contextlib.redirect_stdout(io.StringIO()):
            result = lane.send("old", "brief", "MO#512 check", {}, key, repo=repo, pr_number=512,
                               worktree_only=worktree_only)
        return result, actions

    # A thread without a worktree works in the shared root.
    result, actions = send_to({"status": "running"})
    exact(result, "fresh (old root workspace): receipt")
    exact(actions, ["fresh"])
    # So does a thread whose worktree is the root checkout of a repository.
    result, actions = send_to({"status": "running", "worktreePath": root}, git=root_git)
    exact(result, "fresh (old root workspace): receipt")
    exact(actions, ["fresh"])
    # And so does a thread whose worktree is the root checkout of another
    # repository.
    result, actions = send_to({"status": "running", "worktreePath": worktree}, git=other_root_git)
    exact(result, "fresh (old root workspace): receipt")
    exact(actions, ["fresh"])
    # A worktree path that cannot be read cannot be shown to be a worktree
    # of its own, so the work does not go there either.
    result, actions = send_to({"status": "running", "worktreePath": worktree}, git="")
    exact(result, "fresh (old root workspace): receipt")
    exact(actions, ["fresh"])
    # A thread with its own worktree takes the work.
    result, actions = send_to({"status": "running", "worktreePath": worktree})
    exact(result, "receipt")
    exact(actions, ["send"])
    # The other lane paths keep their own routing: a thread in a shared
    # checkout still takes their work.
    result, actions = send_to({"status": "running", "worktreePath": root}, git=root_git,
                               worktree_only=False)
    exact(result, "receipt")
    exact(actions, ["send"])
    # A branch that is not on origin has no safe worktree, so no work is
    # dispatched at all.
    result, actions = send_to({"status": "running"}, listing="")
    exact(result, f"skip {key}: branch builder/fixture is not on origin, no safe worktree")
    exact(actions, [])
    # A herdr pull request is skipped, and a merged one is skipped too.
    result, actions = send_to({"status": "running", "worktreePath": worktree},
                               pr=dict(number=512, state="OPEN", headRefName="herdr/board-stuck-lane",
                                       baseRefName="main"))
    exact(result, "skip #512: herdr branch, Shyam merges")
    exact(actions, [])
    result, actions = send_to({"status": "running", "worktreePath": worktree},
                               pr=dict(number=512, state="MERGED", headRefName="builder/fixture",
                                       baseRefName="main"))
    exact(result, "skip #512: PR is merged or closed")
    exact(actions, [])
    # An idle thread on another model gives its worktree to one send of a
    # pass, and only while the worktree is on the head branch of the pull
    # request and not on a herdr branch.
    def reroute(branch, sends=1):
        launches = []
        def command(cmd, timeout=150):
            if cmd[0] == "git":
                if "--abbrev-ref" in cmd:
                    return branch + "\n"
                if "rev-parse" in cmd:
                    return worktree_git
                return "abc123\trefs/heads/builder/fixture"
            launches.append(json.loads(cmd[2])["workspaceStrategy"])
            return "receipt"
        idle = {"providerInstanceId": "fixture-other", "model": "fixture-other", "status": "completed",
                "worktreePath": worktree}
        pull = dict(number=512, state="OPEN", headRefName="builder/fixture", baseRefName="main")
        lane.PASS_WORKTREES.clear()
        with patch.object(lane, "CFG", {repo: {"projectId": "fixture"}}), \
             patch.object(lane, "DRY", False), patch.object(lane, "t3", lambda tool, args: {"thread": idle}), \
             patch.object(lane, "read_json", side_effect=pr_reads(lane, pull)), \
             patch.object(lane, "run", command), contextlib.redirect_stdout(io.StringIO()):
            for number in range(sends):
                lane.send("old", "brief", "MO#512 check", {}, f"{key}{number}", repo=repo, pr_number=512)
        return launches
    own = {"type": "existing_worktree", "worktreePath": worktree}
    fresh = {"type": "worktree", "baseRef": "origin/builder/fixture", "startFromOrigin": True}
    exact(reroute("builder/fixture"), [own])
    exact(reroute("herdr/board-stuck-lane"), [fresh])
    exact(reroute("builder/other"), [fresh])
    exact(reroute("builder/fixture", sends=2), [own, fresh])


def cycle_health():
    """The cycle's health checks over injected inputs.

    The inputs are the data the checks read, handed in instead of read
    from the machine: the eval starts no process, opens no socket and
    touches no board. It proves the four checks of the cycle's health
    boundary and the rule that a read which failed is never a clean
    result."""
    loader = importlib.machinery.SourceFileLoader(
        "fixture_overnight", str(ROOT / "overnight")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    real_decisions_checked = module.read_decisions_checked
    # The tools: a probe that failed and a log with a traceback.
    findings = module.tool_findings(
        [
            {
                "name": "coordq",
                "command": "python3 coordq status",
                "exit": 1,
                "output": "Traceback (most recent call last):",
            },
            {
                "name": "overnight",
                "command": "python3 overnight --help",
                "exit": 0,
                "output": "usage: overnight",
            },
        ],
        [{"path": "/tmp/dispatch.log", "lines": ["a line", "Traceback (most recent call last):"]}],
    )
    exact(len(findings), 2)
    exact([finding["check"] for finding in findings], ["tools", "tools"])
    exact(module.tool_findings([{"name": "coordq", "command": "x", "exit": 0}], []), [])
    # The installed files: in sync is no finding, out of sync is one.
    exact(module.install_findings({"in_sync": True, "differs": []}), [])
    out = module.install_findings(
        {"in_sync": False, "differs": ["/Users/x/.local/bin/coordq"]}
    )
    exact(len(out), 1)
    exact(out[0]["check"], "install")
    # The board's attempts: three starts and no pull request is a finding.
    record = {
        "repo": "o/r",
        "number": 7,
        "key": "R-7",
        "attempts": 3,
        "carried": False,
        "parked": False,
    }
    exact(len(module.attempt_findings([record])), 1)
    exact(module.attempt_findings([{**record, "carried": True}]), [])
    exact(module.attempt_findings([{**record, "parked": True}]), [])
    exact(module.attempt_findings([{**record, "attempts": 2}]), [])
    # A pull request list that was cut off at the limit is not a list
    # with no pull requests: the tickets of that repository are not
    # classified at all, and the check says the list was incomplete.
    module.run = lambda argv, timeout, deadline: json.dumps(
        [
            {
                "number": 7,
                "title": "a ticket",
                "comments": [
                    {"body": "Starting b attempt 1"},
                    {"body": "Starting b attempt 2"},
                    {"body": "Starting b attempt 3"},
                ],
            }
        ]
    )
    module.read_decisions_checked = lambda: (Path("/tmp/decisions.md"), [], "")
    module.read_pull_requests = lambda repo, deadline: ([], True)
    ran, cut = module.check_attempts(
        [{"repo": "o/r", "number": 7, "key": "R-7"}], [("o/r", "")], 0
    )
    exact(len(cut), 1)
    exact(cut[0]["check"], "attempts")
    exact("not classified" in cut[0]["detail"], True)
    exact("cut off" in cut[0]["detail"], True)
    # The same board with a whole pull request list is classified: the
    # ticket has no pull request, so it is a finding.
    module.read_pull_requests = lambda repo, deadline: ([], False)
    ran, whole = module.check_attempts(
        [{"repo": "o/r", "number": 7, "key": "R-7"}], [("o/r", "")], 0
    )
    exact(len(whole), 1)
    exact(whole[0]["check"], "attempts")
    exact("no open pull request" in whole[0]["detail"], True)
    # An issue whose comments were cut off is not an issue with few
    # comments: its starts are not known and it is not classified.
    module.run = lambda argv, timeout, deadline: json.dumps(
        [
            {
                "number": 7,
                "title": "a ticket",
                "comments": [
                    {"body": "Starting b attempt 1"},
                    {"body": "Starting b attempt 2"},
                    {"body": "Starting b attempt 3"},
                ]
                + [{"body": "a comment"} for _ in range(97)],
            }
        ]
    )
    module.read_pull_requests = lambda repo, deadline: ([], False)
    ran, cut_comments = module.check_attempts(
        [{"repo": "o/r", "number": 7, "key": "R-7"}], [("o/r", "")], 0
    )
    exact(len(cut_comments), 1)
    exact(cut_comments[0]["check"], "attempts")
    exact("cut off" in cut_comments[0]["detail"], True)
    exact("not classified" in cut_comments[0]["detail"], True)
    # A decisions log that exists and cannot be read leaves the parked
    # tickets unknown: the check is incomplete and classifies nothing.
    module.read_decisions_checked = lambda: (
        Path("/tmp/decisions.md"),
        [],
        "the log could not be read: boom",
    )
    ran, unreadable = module.check_attempts(
        [{"repo": "o/r", "number": 7, "key": "R-7"}], [("o/r", "")], 0
    )
    exact(len(unreadable), 1)
    exact(unreadable[0]["check"], "attempts")
    exact("incomplete" in unreadable[0]["detail"], True)
    exact(any("no ticket was classified" in line for line in ran), True)
    # A decisions log that does not exist yet is not an error: the
    # coordinator writes it the first time it parks a ticket.
    module.read_decisions_checked = real_decisions_checked
    with tempfile.TemporaryDirectory() as folder:
        module.DECISIONS_FILE = Path(folder) / "decisions.md"
        _path, none_yet, none_error = module.read_decisions_checked()
    exact(none_yet, [])
    exact(none_error, "")
    # The board's blockers: a closed issue is a false blocker, an issue
    # whose state was never read is an incomplete check, not a clean one.
    refusal = {
        "repo": "o/r",
        "number": 8,
        "reason": "refused: text blockers: SRW-9 (#9) is still open",
    }
    closed = module.blocker_findings([refusal], {("o/r", 9): "closed"}, {})
    exact(len(closed), 1)
    exact(closed[0]["check"], "blockers")
    exact(module.blocker_findings([refusal], {("o/r", 9): "open"}, {}), [])
    incomplete = module.blocker_findings(
        [refusal], {}, {
            ("o/r", 9): (
                "the state of o/r#9 could not be read, so the text blocker "
                "check is incomplete for it"
            )
        }
    )
    exact(len(incomplete), 1)
    exact("incomplete" in incomplete[0]["detail"], True)
    # A log that could not be read is not an empty log: the check that
    # needed it is incomplete, and the receipt does not claim the log
    # was read.
    broken = module.log_read_finding(
        "blockers", "/tmp/dispatch.log", "the log could not be read: boom"
    )
    exact(broken["check"], "blockers")
    exact("incomplete" in broken["detail"], True)
    unread_logs = module.tool_findings(
        [], [{"path": "/tmp/dispatch.log", "lines": [], "error": "boom"}]
    )
    exact(len(unread_logs), 1)
    exact(unread_logs[0]["check"], "tools")
    exact("incomplete" in unread_logs[0]["detail"], True)
    with tempfile.TemporaryDirectory() as folder:
        module.QUEUE_DIR = Path(folder)
        ran, failed = module.check_blockers(0)
    exact(len(failed), 1)
    exact(failed[0]["check"], "blockers")
    exact("incomplete" in failed[0]["detail"], True)
    exact(any("could not be read" in line for line in ran), True)
    # A stale board is not a board with no tickets: the attempts check
    # is incomplete and classifies nothing.
    ran, stale = module.check_attempts([], [("o/r", "")], 0, True)
    exact(len(stale), 1)
    exact(stale[0]["check"], "attempts")
    exact("incomplete" in stale[0]["detail"], True)
    exact(any("stale" in line for line in ran), True)
    # The log read is bounded: a huge log costs one fixed read from the
    # end, so a traceback buried far from the end is outside the window
    # and a traceback at the end is inside it.
    import time as clock
    with tempfile.TemporaryDirectory() as folder:
        module.QUEUE_DIR = Path(folder)
        log = Path(folder) / "dispatch.log"
        filler = "a line of the queue log\n" * 60000
        log.write_text("Traceback (most recent call last):\n" + filler)
        lines, error = module.queue_log_tail("dispatch.log", 40, clock.monotonic() + 60)
        exact(error, "")
        exact(any("Traceback" in line for line in lines), False)
        log.write_text(filler + "Traceback (most recent call last):\n")
        lines, error = module.queue_log_tail("dispatch.log", 40, clock.monotonic() + 60)
        exact(error, "")
        exact(any("Traceback" in line for line in lines), True)
        # The window never returns more lines than asked for, and it
        # drops the partial first line of the window.
        exact(len(lines) <= 40, True)
        exact(all(line for line in lines), True)
        # A cycle that is out of time does not read the log at all.
        lines, error = module.queue_log_tail("dispatch.log", 40, clock.monotonic() - 1)
        exact(lines, [])
        exact("ran out of time" in error, True)
        # The bounded window is a fixed budget, far below the log's size.
        exact(module.LOG_TAIL_BYTES <= 1024 * 1024, True)
        exact(log.stat().st_size > module.LOG_TAIL_BYTES, True)


def stall():
    import lane_driver as lane
    import stall as rule

    # The rule: three idle ticks park the item, and a marker that moves
    # starts the count again.
    state = rule.new_state()
    exact(rule.observe(state, "repo#1", "aaa|1"), None)
    exact(rule.observe(state, "repo#1", "aaa|1"), None)
    event = rule.observe(state, "repo#1", "aaa|1")
    exact(event is not None, True)
    exact(event["kind"], "item")
    exact(event["idle"], 3)
    exact(state["items"]["repo#1"]["stalled"], True)
    exact(rule.observe(state, "repo#1", "aaa|1"), None)

    state = rule.new_state()
    exact(rule.observe(state, "repo#1", "aaa|1"), None)
    exact(rule.observe(state, "repo#1", "bbb|1"), None)
    exact(rule.observe(state, "repo#1", "bbb|1"), None)
    exact(rule.observe(state, "repo#1", "bbb|1"), None)
    exact(state["items"]["repo#1"]["stalled"], False)
    event = rule.observe(state, "repo#1", "bbb|1")
    exact(event is not None, True)
    exact(event["kind"], "item")

    # The board is alerted once per episode, and the flag is set only after
    # the alert was delivered: an alert that could not be written asks
    # again on the next tick.
    state = rule.new_state()
    exact(rule.board(state, False, 1), None)
    exact(rule.board(state, False, 1), None)
    event = rule.board(state, False, 1)
    exact(event["kind"], "board")
    exact(event["idle"], 3)
    # The alert was not delivered, so the board asks again.
    exact(rule.board(state, False, 1)["kind"], "board")
    rule.delivered(state)
    exact(rule.board(state, False, 1), None)
    # The board moved, so the episode is over and the flag is gone.
    exact(rule.board(state, True, 1), None)
    exact(rule.board(state, False, 1), None)
    exact(state.get("board_alerted"), None)
    # A board with no item in it is not a stalled board.
    state = rule.new_state()
    exact(rule.board(state, False, 0), None)
    exact(state["board_idle"], 0)
    # The board's first tick is its baseline, and a board that keeps moving
    # never stalls.
    state = rule.new_state()
    exact(rule.board(state, True, 1), None)
    exact(state["board_idle"], 1)
    exact(rule.board(state, True, 1), None)
    exact(state["board_idle"], 0)

    # The driver: the item is worked until it is parked, and a parked item
    # is skipped, so the shift moves on.
    repo = "shyamsivakumar/mac-ops"
    head = "a" * 40
    pull = {"number": 7, "state": "OPEN", "headRefOid": head, "body": "Refs #9",
            "mergeable": "MERGEABLE", "isDraft": False}
    snapshot = {"tickets": [], "repos": {repo: {"prs": [pull], "issues": []}}}
    ledger = {}
    acted = []
    events = []

    def act(repo_name, number, ledger_state):
        acted.append(number)
        return f"#{number} worked"

    with patch.object(lane, "watchdog"), patch.object(lane, "drift_ff"), \
         patch.object(lane, "board_snapshot", return_value=snapshot), \
         patch.object(lane, "LANE_REPOS", [repo]), patch.object(lane, "ORDER", {}), \
         patch.object(lane, "CFG", {repo: {"projectId": "fixture", "key": "MO"}}), \
         patch.object(lane, "busy", return_value=""), patch.object(lane, "t3", return_value={}), \
         patch.object(lane, "stall_receipts", return_value={}), \
         patch.object(lane, "act_on_pr", act), patch.object(lane, "settle_merged_prs"), patch.object(lane, "DRY", False):
        lane.STALL_STATE = {}
        lane.STALL_EVENTS.clear()
        for _ in range(4):
            lane.run_pass(ledger)
            events.append(list(lane.STALL_EVENTS))
            lane.STALL_EVENTS.clear()
    exact(acted, [7, 7, 7, 7])
    # The board asks again on the next tick, because the alert was never
    # delivered: the flag is set only after the alert was written.
    exact([len(found) for found in events], [0, 0, 2, 1])
    exact(events[2][0]["kind"], "item")
    exact(events[2][0]["item"], f"{repo}#9")
    exact(events[2][1]["kind"], "board")
    exact(events[3][0]["kind"], "board")
    exact(lane.STALL_STATE.get("board_alerted"), None)
    exact(lane.STALL_STATE["items"][f"{repo}#9"]["stalled"], True)

    # A pass with live work in the dispatch queue is progress for the board,
    # not for its items: a thread can run for longer than three ticks
    # between commits.
    def idle_board(live):
        found = []
        with patch.object(lane, "watchdog"), patch.object(lane, "drift_ff"), \
             patch.object(lane, "board_snapshot", return_value=snapshot), \
             patch.object(lane, "LANE_REPOS", [repo]), patch.object(lane, "ORDER", {}), \
             patch.object(lane, "CFG", {repo: {"projectId": "fixture", "key": "MO"}}), \
             patch.object(lane, "busy", return_value=live), patch.object(lane, "t3", return_value={}), \
             patch.object(lane, "stall_receipts", return_value={}), \
             patch.object(lane, "act_on_pr", act), patch.object(lane, "settle_merged_prs"), patch.object(lane, "DRY", False):
            lane.STALL_STATE = {}
            lane.STALL_EVENTS.clear()
            for _ in range(4):
                lane.run_pass({})
                found.extend(e["kind"] for e in lane.STALL_EVENTS)
                lane.STALL_EVENTS.clear()
        return found

    exact("board" in idle_board("live: builder thread"), False)
    exact(idle_board("").count("board"), 2)

    acted.clear()
    timeout = subprocess.TimeoutExpired(["t3mcp"], 30)
    with patch.object(lane, "watchdog"), patch.object(lane, "drift_ff"), \
         patch.object(lane, "board_snapshot", return_value=snapshot), \
         patch.object(lane, "LANE_REPOS", [repo]), patch.object(lane, "ORDER", {}), \
         patch.object(lane, "CFG", {repo: {"projectId": "fixture", "key": "MO"}}), \
         patch.object(lane, "busy", side_effect=timeout), patch.object(lane, "t3", return_value={}), \
         patch.object(lane, "stall_receipts", return_value={}), \
         patch.object(lane, "start_next") as start, \
         patch.object(lane, "act_on_pr", act), patch.object(lane, "settle_merged_prs"), patch.object(lane, "DRY", False):
        lane.STALL_STATE = {}
        failed = {}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.suppress(RuntimeError):
            lane.run_pass(failed)
    exact(acted, [])
    exact(start.call_count, 0)
    exact(failed.get("_item_failures"), 1)

    # New work on the board is progress, whether the shift has measured the
    # new item or not.
    state = rule.new_state()
    exact(rule.arrived(state, {"a", "b"}), {"a", "b"})
    exact(rule.arrived(state, {"a", "b"}), set())
    exact(rule.arrived(state, {"b", "c"}), {"c"})
    exact(sorted(state["board"]), ["b", "c"])

    # A board that receives a new ticket every tick is a board that is
    # working, so it does not stall.
    boards = [
        {"tickets": [dict(repo=repo, number=number, key=f"MO-{number}", stage="todo",
                          problems=[])],
         "repos": {repo: {"prs": [], "issues": []}}}
        for number in (1, 2, 3)
    ]
    seen = {"index": 0}

    def board(ledger, force=False):
        index = min(seen["index"], len(boards) - 1)
        seen["index"] += 1
        return boards[index]

    def run(cmd, timeout=150):
        return "started\n"

    lane.STALL_STATE = {}
    lane.STALL_EVENTS.clear()
    with patch.object(lane, "watchdog"), patch.object(lane, "drift_ff"), \
         patch.object(lane, "board_snapshot", side_effect=board), \
         patch.object(lane, "LANE_REPOS", [repo]), patch.object(lane, "ORDER", {}), \
         patch.object(lane, "CFG", {repo: {"projectId": "fixture", "key": "MO"}}), \
         patch.object(lane, "busy", return_value=""), patch.object(lane, "t3", return_value={}), \
         patch.object(lane, "stall_receipts", return_value={}), \
         patch.object(lane, "act_on_pr", act), patch.object(lane, "settle_merged_prs"), patch.object(lane, "run", run), \
         patch.object(lane, "DRY", False):
        for _ in range(3):
            lane.run_pass({})
    exact(lane.STALL_EVENTS, [])
    lane.STALL_EVENTS.clear()

    # A stale board must not report an item as stalled: the shift reads the
    # board again before it decides, and the fresh head is progress.
    stale = {"number": 8, "state": "OPEN", "headRefOid": "a" * 40, "body": "Refs #9",
             "mergeable": "MERGEABLE", "isDraft": False}
    fresh = dict(stale, headRefOid="b" * 40)
    stale_board = {"tickets": [], "repos": {repo: {"prs": [stale], "issues": []}}}
    fresh_board = {"tickets": [], "repos": {repo: {"prs": [fresh], "issues": []}}}
    reads = []

    def snapshot(ledger, force=False):
        reads.append(force)
        return fresh_board if force else stale_board

    lane.STALL_STATE = {}
    with patch.object(lane, "watchdog"), patch.object(lane, "drift_ff"), \
         patch.object(lane, "board_snapshot", side_effect=snapshot), \
         patch.object(lane, "LANE_REPOS", [repo]), patch.object(lane, "ORDER", {}), \
         patch.object(lane, "CFG", {repo: {"projectId": "fixture", "key": "MO"}}), \
         patch.object(lane, "busy", return_value=""), patch.object(lane, "t3", return_value={}), \
         patch.object(lane, "stall_receipts", return_value={}), \
         patch.object(lane, "act_on_pr", act), patch.object(lane, "settle_merged_prs"), patch.object(lane, "DRY", False):
        for _ in range(4):
            lane.run_pass({})
    exact(lane.STALL_STATE["items"][f"{repo}#9"]["stalled"], False)
    exact(True in reads, True)

    # A draft is not work the shift does, so it is not measured.
    draft = {"tickets": [], "repos": {repo: {"prs": [dict(stale, isDraft=True)],
                                              "issues": []}}}
    lane.STALL_STATE = {}
    with patch.object(lane, "watchdog"), patch.object(lane, "drift_ff"), \
         patch.object(lane, "board_snapshot", return_value=draft), \
         patch.object(lane, "LANE_REPOS", [repo]), patch.object(lane, "ORDER", {}), \
         patch.object(lane, "CFG", {repo: {"projectId": "fixture", "key": "MO"}}), \
         patch.object(lane, "busy", return_value=""), patch.object(lane, "t3", return_value={}), \
         patch.object(lane, "stall_receipts", return_value={}), \
         patch.object(lane, "act_on_pr", act), patch.object(lane, "settle_merged_prs"), patch.object(lane, "DRY", False):
        lane.run_pass({})
    exact(lane.STALL_STATE.get("items", {}), {})

    held = {"number": 9, "title": "held", "labels": [{"name": "stage:hold"}]}
    idle = {"number": 10, "title": "idle", "labels": [{"name": "stage:todo"}]}
    idle_pull = dict(stale, number=10, body="Refs #10")

    def three_ticks(prs, issues):
        board = {"tickets": [], "repos": {repo: {"prs": prs, "issues": issues}}}
        lane.STALL_STATE = {}
        lane.STALL_EVENTS.clear()
        with patch.object(lane, "watchdog"), patch.object(lane, "drift_ff"), \
             patch.object(lane, "board_snapshot", return_value=board), \
             patch.object(lane, "LANE_REPOS", [repo]), patch.object(lane, "ORDER", {}), \
             patch.object(lane, "CFG", {repo: {"projectId": "fixture", "key": "MO"}}), \
             patch.object(lane, "busy", return_value=""), patch.object(lane, "t3", return_value={}), \
             patch.object(lane, "stall_receipts", return_value={}), \
             patch.object(lane, "act_on_pr", act), patch.object(lane, "settle_merged_prs"), patch.object(lane, "DRY", False):
            for _ in range(3):
                lane.run_pass({})
        found = list(lane.STALL_EVENTS)
        lane.STALL_EVENTS.clear()
        return found

    exact(three_ticks([stale], [held]), [])
    exact(lane.STALL_STATE.get("items", {}), {})
    exact(lane.board_keys({"tickets": [dict(repo=repo, number=9, stage="todo")],
                           "repos": {repo: {"prs": [], "issues": [held]}}}), set())
    found = three_ticks([stale, idle_pull], [held, idle])
    exact([event["item"] for event in found if event["kind"] == "item"], [f"{repo}#10"])

    # A stalled item is reported, not parked: the shift keeps working it.
    lane.STALL_STATE = {"items": {f"{repo}#9": {"marker": "a" * 40, "idle": 3,
                                                "stalled": True}}}
    orphan = {"tickets": [], "repos": {repo: {"prs": [], "issues": [
        {"number": 9, "title": "bot repair", "labels": []}]}}}
    from unittest.mock import mock_open
    import datetime as dt
    started = {f"ticket:{repo}#9:a1": "old"}
    cooling = {"cont:old": [dt.datetime.now(dt.timezone.utc).isoformat(), "receipt"]}
    with patch.object(lane, "SNAPSHOT", orphan), patch.object(lane, "DRY", True), \
         patch.object(lane, "t3", return_value={}), \
         patch("builtins.open", mock_open(read_data=json.dumps(started))):
        exact(lane.unstick(repo, dict(cooling)), "DRY unstick [9]")

    # A receipt is the proof a builder was started. A fresh ticket with no
    # receipt was never started, so nothing finished and unstick leaves it
    # alone; a started ticket with no pull request is still swept.
    fresh = {"tickets": [], "repos": {repo: {"prs": [], "issues": [
        {"number": 8, "title": "bot repair", "labels": []},
        {"number": 9, "title": "bot repair", "labels": []}]}}}
    with patch.object(lane, "SNAPSHOT", fresh), patch.object(lane, "DRY", True), \
         patch.object(lane, "t3", return_value={}), \
         patch("builtins.open", mock_open(read_data=json.dumps(started))):
        exact(lane.unstick(repo, dict(cooling)), "DRY unstick [9]")
    with patch.object(lane, "SNAPSHOT", fresh), patch.object(lane, "DRY", True), \
         patch.object(lane, "t3", return_value={}), \
         patch("builtins.open", mock_open(read_data="{}")):
        exact(lane.unstick(repo, {}), "nothing ready")

    # The brief the thread receives tells it to re-read the ticket's open
    # pull requests before closing, so a pull request opened after the
    # snapshot is not missed.
    brief = lane.UNSTICK_BRIEF
    exact("re-read its open pull requests" in brief, True)
    exact("leave the issue untouched" in brief, True)
    exact("Refs #<n>" in brief, True)
    exact("{repo}" in brief, True)
    exact("{list}" in brief, True)

    # A matching pull request and an incomplete lookup are terminal: the
    # thread reports the issue and moves on, so the disposition rule cannot
    # send it back to close a ticket that has a pull request.
    exact("Two outcomes end the work on an issue at once" in brief, True)
    exact("The lookup is incomplete (the command fails, or the list reaches the limit)" in brief, True)
    exact("report it and leave the issue alone" in brief, True)

    # Brief text lives in lane_briefs.py, which the prompt hold knows by
    # path, so a change to it is held even though lane_driver.py is code.
    # Replay of #626: its brief change now lands in lane_briefs.py.
    exact(lane.prompt_paths.prompt_scan(["coordinator/bin/lane_briefs.py"]), lane.prompt_paths.HOLD)
    exact(lane.prompt_paths.prompt_scan(["coordinator/overnight/lane_driver.py"]), lane.prompt_paths.LOOP_HOLD)
    exact(lane.prompt_paths.prompt_scan(["README.md"]), lane.prompt_paths.CLEAR)
    exact("re-read its open pull requests" in Path(lane.__file__).read_text(), False)
    exact("last review round" in Path(lane.__file__).read_text(), False)
    exact("skipped: matching PR #<n>" in brief, True)
    exact("skipped: incomplete PR lookup" in brief, True)
    exact("Every confirmed orphan must end closed" in brief, True)
    exact("Every issue must end closed" in brief, False)


def alarm_mute_on_one_board():
    import datetime as dt
    import alarms
    import lane_driver as lane
    import stall as rule

    now = dt.datetime(2026, 11, 17, 12, 0, tzinfo=dt.timezone.utc)
    cause = "gatekeep failing (last exit code 1)"
    key = alarms.key_of("factory-watchdog", cause)

    # The rule: a key with an acknowledgement stays quiet for four hours,
    # and every other key is raised at once.
    state = {}
    exact(alarms.decide(state, "factory-watchdog", cause, now), "raise")
    alarms.raised(state, "factory-watchdog", cause, now)
    exact(alarms.decide(state, "factory-watchdog", cause, now), "raise")

    # A board item that went missing is not an acknowledgement. The board
    # has more than one writer and one of them can lose the item, so an
    # alarm nobody answered is raised again and never silenced.
    exact(alarms.decide(state, "factory-watchdog", cause, now), "raise")

    # The acknowledgement is what quiets the key.
    alarms.acknowledge(state, key, now)
    exact(alarms.decide(state, "factory-watchdog", cause, now), "quiet")
    exact(alarms.muted(state, key, now), True)
    # A different cause is a different key and alarms at once.
    exact(alarms.decide(state, "factory-watchdog", "gatekeep failing (last exit code 2)",
                         now), "raise")
    # The quiet key stays quiet for four hours and then alarms again.
    exact(alarms.decide(state, "factory-watchdog", cause,
                         now + dt.timedelta(hours=3)), "quiet")
    exact(alarms.decide(state, "factory-watchdog", cause,
                         now + dt.timedelta(hours=4, minutes=1)), "raise")

    # The minutes of a quiet log are not part of the cause, so the same
    # quiet log is the same cause. The exit code is part of it.
    exact(alarms.key_of("factory-watchdog", "gatekeep silent 200 min (limit 120)"),
          alarms.key_of("factory-watchdog", "gatekeep silent 261 min (limit 120)"))
    exact(alarms.key_of("factory-watchdog", "gatekeep failing (last exit code 1)") ==
          alarms.key_of("factory-watchdog", "gatekeep failing (last exit code 2)"), False)

    # The idle tick count is not part of a cause: the same stall reported
    # on the fourth tick is the same stall as the one reported on the
    # third, so it does not raise again inside the mute window.
    exact(alarms.key_of("factory-overnight-stall", "no board progress for 3 ticks"),
          alarms.key_of("factory-overnight-stall", "no board progress for 4 ticks"))

    # A tick where the alarm is not true any more does not take the mute
    # with it: the key keeps its acknowledgement, so the same cause stays
    # quiet for the rest of the four hours.
    state = {}
    alarms.raised(state, "factory-watchdog", cause, now)
    alarms.acknowledge(state, key, now)
    alarms.gone(state, "factory-watchdog")
    exact(alarms.decide(state, "factory-watchdog", cause, now), "quiet")
    # And a cause that was never acknowledged alarms again when it is
    # true again.
    state = {}
    alarms.raised(state, "factory-watchdog", cause, now)
    alarms.gone(state, "factory-watchdog")
    exact(alarms.decide(state, "factory-watchdog", cause, now), "raise")

    # The mute state lives in its own file, so a board file that the
    # coordinator rewrites cannot take the mute with it, and the command
    # that records an acknowledgement writes that file.
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        with patch.object(alarms, "MUTE_PATH", mute):
            state = alarms.load_state()
            alarms.raised(state, "factory-watchdog", cause, now)
            exact(alarms.save_state(state), True)
            exact(alarms.load_state()[key]["raised"], alarms.stamp(now))

            class StateClock(dt.datetime):
                @classmethod
                def now(cls, tz=None):
                    return now

            with patch.object(dt, "datetime", StateClock):
                exact(alarms.main(["ack", "factory-watchdog", cause]), 0)
            exact(alarms.muted(alarms.load_state(), key, now), True)
            # The command that cannot write the state says so, so the
            # panel can warn that the alarm will raise again.
            with patch.object(alarms, "write_state", return_value=False), \
                 contextlib.redirect_stderr(io.StringIO()):
                exact(alarms.main(["ack", "factory-watchdog", cause]), 3)
            with contextlib.redirect_stderr(io.StringIO()):
                exact(alarms.main(["ack", "factory-nothing", cause]), 1)

    # The command acknowledges one cause. Another cause of the same alarm
    # was not answered and is not silenced.
    state = {}
    alarms.raised(state, "factory-watchdog", cause, now)
    other = "gatekeep failing (last exit code 2)"
    alarms.raised(state, "factory-watchdog", other, now)
    alarms.acknowledge(state, alarms.key_of("factory-watchdog", other), now)
    exact(alarms.decide(state, "factory-watchdog", other, now), "quiet")
    exact(alarms.decide(state, "factory-watchdog", cause, now), "raise")

    # A tick that read the state before the acknowledgement was recorded
    # does not take that acknowledgement with it when it writes.
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        with patch.object(alarms, "MUTE_PATH", mute):
            stale = alarms.load_state()
            alarms.raised(stale, "factory-watchdog", cause, now)
            alarms.save_state(stale)
            fresh = alarms.load_state()
            alarms.acknowledge(fresh, alarms.key_of("factory-watchdog", cause), now)
            alarms.save_state(fresh)
            # The tick writes its older snapshot.
            alarms.save_state(stale)
            exact(alarms.muted(alarms.load_state(),
                                alarms.key_of("factory-watchdog", cause), now), True)

    # Two writers of the same file at once: the tick writes its older
    # snapshot while the panel records the acknowledgement, and the
    # acknowledgement survives.
    import threading
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        with patch.object(alarms, "MUTE_PATH", mute):
            stale = alarms.load_state()
            alarms.raised(stale, "factory-watchdog", cause, now)
            alarms.save_state(stale)
            written = []

            def panel():
                fresh = alarms.load_state()
                alarms.acknowledge(fresh, alarms.key_of("factory-watchdog", cause), now)
                written.append(alarms.save_state(fresh))

            def tick():
                written.append(alarms.save_state(stale))

            threads = [threading.Thread(target=panel), threading.Thread(target=tick)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            exact(all(written), True)
            exact(alarms.muted(alarms.load_state(),
                                alarms.key_of("factory-watchdog", cause), now), True)

    # The panel is JavaScript, so the contract it holds for the answer is
    # read from its source: the answer carries the cause it was given
    # for, an answer whose alarm changed is dropped before the send, the
    # acknowledgement names that cause, and the panel warns when the
    # command did not record it.
    panel = panel_source()
    exact('shown: a.cause ?? ""' in panel, True)
    # The panel uses the rules in the module the probe runs, so the
    # rules themselves are checked there, not here.
    exact('from "./answers.js"' in panel, True)
    exact("await acknowledgeAlarm(a.id, a.cause)" in panel, True)
    exact("if (r.code !== 0) {" in panel, True)
    exact("`${home()}/.local/bin/alarms.py`" in panel, True)
    exact("const bound = this.replyCauses.get(q)" in panel, True)
    # A restored reply keeps the cause it belongs to, and a restored
    # reply whose cause is unknown is dropped.
    exact('shared("co.replyCauses")' in panel, True)
    exact("bound === undefined" in panel, True)
    send = panel.index("send(cx) {")
    body = panel[send:send + 400]
    exact(body.index("this.dropStaleDrafts()") < body.index("this.message()"), True)

    # A lock that cannot be taken is not a lock: the write fails and the
    # file is left alone, rather than written unlocked.
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        with patch.object(alarms, "MUTE_PATH", mute):
            state = alarms.load_state()
            alarms.raised(state, "factory-watchdog", cause, now)
            with patch.object(alarms.os, "open", side_effect=OSError("read-only")):
                exact(alarms.save_state(state), False)
            exact(alarms.load_state(), {})

    # A lock that cannot be taken fails the command too: the
    # acknowledgement did not land, the command says so, and the alarm is
    # not muted.
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        with patch.object(alarms, "MUTE_PATH", mute):
            state = alarms.load_state()
            alarms.raised(state, "factory-watchdog", cause, now)
            alarms.save_state(state)
            with patch.object(alarms.os, "open", side_effect=OSError("read-only")), \
                 contextlib.redirect_stderr(io.StringIO()):
                exact(alarms.main(["ack", "factory-watchdog", cause]), 3)
            exact(alarms.muted(alarms.load_state(),
                                alarms.key_of("factory-watchdog", cause), now), False)

    # The decision and the publication happen under the lock, so an
    # answer cannot slip between them: while the alarm is published, the
    # lock is held and no other writer can record an acknowledgement.
    import fcntl
    import os
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        with patch.object(alarms, "MUTE_PATH", mute):
            state = alarms.load_state()
            alarms.raised(state, "factory-watchdog", cause, now)
            alarms.save_state(state)
            published = []
            held = []

            def publish(action):
                # Another writer tries the lock while the alarm is
                # published. It cannot have it: the tick holds it.
                other = os.open(str(Path(str(mute) + ".lock")), os.O_RDWR | os.O_CREAT, 0o600)
                try:
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    held.append(False)
                    fcntl.flock(other, fcntl.LOCK_UN)
                except OSError:
                    held.append(True)
                finally:
                    os.close(other)
                published.append(action)
                return None

            action = alarms.decide_and_publish("factory-watchdog", cause, publish)
            exact(action, "raise")
            exact(published, ["raise"])
            # The lock was held for the whole publication.
            exact(held, [True])
            # The key is on the board and in the state, so the answer has
            # something to acknowledge.
            exact(alarms.muted(alarms.load_state(), key, now), False)
            exact("acked" in alarms.load_state()[key], False)

    # A lock that cannot be taken does not hide the alarm: the alarm is
    # published as unchecked and the fault is said out loud, because a
    # storage failure must not hide a real failure from Shyam.
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        with patch.object(alarms, "MUTE_PATH", mute):
            published = []
            with patch.object(alarms, "take_lock", return_value=None):
                action = alarms.decide_and_publish("factory-watchdog", cause,
                                                   lambda a: published.append(a))
            exact(action, "unchecked")
            exact(published, ["unchecked"])

    # A board lock that cannot be taken does not hide the alarm: the
    # board is written without it and the fault is said out loud.
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        with patch.object(alarms, "MUTE_PATH", mute):
            published = []
            with patch.object(alarms, "take_lock", return_value=None):
                action = alarms.decide_and_publish("factory-watchdog", cause,
                                                   lambda a: published.append(a))
            exact(action, "unchecked")
            exact(published, ["unchecked"])
            # The board lock is its own file, so a mute lock that cannot
            # be taken does not leave the board open. A board lock that
            # cannot be taken does not suppress the alarm either: the
            # write falls back to a compare-and-swap, so the alarm is
            # delivered and another publisher's item survives.
            board_file = Path(scratch) / "decisions.json"
            board_file.write_text(json.dumps({"items": [{"id": "unrelated"}]}))
            with patch.object(alarms, "take_lock", side_effect=lambda path=None: None):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    target, action = rule.alert("no board progress for 3 ticks", None, board_file)
                exact(action, "wrote")
            ids = [i["id"] for i in json.loads(board_file.read_text())["items"]]
            exact("factory-overnight-stall" in ids, True)
            exact("unrelated" in ids, True)

    # A board lock that cannot be taken does not suppress an alarm: both
    # publishers still deliver, by compare-and-swap, and neither erases
    # the other's item.
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        board = Path(scratch) / "decisions.json"
        board.write_text(json.dumps({"items": []}))
        with patch.object(alarms, "MUTE_PATH", mute):
            with patch.object(alarms, "take_lock", side_effect=lambda path=None: None):
                result = alarms.board_update(
                    str(board), "factory-watchdog", "raise",
                    {"id": "factory-watchdog", "cause": "gatekeep failing (last exit code 1)"})
                exact(result, "wrote")
                target, action = rule.alert("no board progress for 3 ticks", None, board)
                exact(action, "wrote")
            ids = [i["id"] for i in json.loads(board.read_text())["items"]]
            exact("factory-watchdog" in ids, True)
            exact("factory-overnight-stall" in ids, True)

    # A damaged state file is not an empty state either: the alarm is
    # published as unchecked and the file is kept as it is, so the
    # acknowledgements it still holds are not lost.
    with tempfile.TemporaryDirectory() as scratch:
        damaged = Path(scratch) / "mute-state.json"
        damaged.write_text("{ not json")
        with patch.object(alarms, "MUTE_PATH", str(damaged)):
            published = []
            action = alarms.decide_and_publish("factory-watchdog", cause,
                                               lambda a: published.append(a))
            exact(action, "unchecked")
            exact(published, ["unchecked"])
            exact(damaged.read_text(), "{ not json")
            # The command says the state cannot be read, and it does not
            # write over the damaged file either.
            exact(alarms.main(["status"]), 3)
            exact(alarms.main(["ack", "factory-watchdog", cause]), 3)
            exact(damaged.read_text(), "{ not json")

    # A state file that cannot be read is not an empty state: the alarm
    # is published as unchecked, and the state that could not be read is
    # not written over, so the acknowledgements it holds stay.
    with tempfile.TemporaryDirectory() as scratch:
        unreadable = Path(scratch) / "mute-state.json"
        unreadable.mkdir()
        with patch.object(alarms, "MUTE_PATH", str(unreadable)):
            published = []
            action = alarms.decide_and_publish("factory-watchdog", cause,
                                               lambda a: published.append(a))
            exact(action, "unchecked")
            exact(published, ["unchecked"])
            exact(unreadable.is_dir(), True)

    # The stall's cause names the stalled repos, so two stalls on
    # different repos are different causes.
    stalled = {"items": {"a/one#1": {"stalled": True}, "b/two#2": {"stalled": False}}}
    exact(rule.alarm_cause("no board progress for 3 ticks", stalled),
          "no board progress for 3 ticks | stalled: a/one#1")
    exact(rule.alarm_cause("no board progress for 3 ticks", {"items": {}}),
          "no board progress for 3 ticks | stalled: none")

    # The stall writes the alarm, and the same cause stays quiet once it
    # is acknowledged.
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        with patch.object(alarms, "MUTE_PATH", mute):
            board = Path(scratch) / "decisions.json"
            board.write_text(json.dumps({"items": []}))
            target, action = rule.alert("no board progress for 3 ticks", None, board)
            exact(action, "wrote")
            exact(target, str(board))
            items = json.loads(board.read_text())["items"]
            exact(len(items), 1)
            exact(items[0]["id"], "factory-overnight-stall")
            exact(items[0]["cause"], "no board progress for <ticks>")
            # An alarm nobody answered is raised again: the board item
            # going missing says nothing.
            data = json.loads(board.read_text())
            data["items"] = []
            board.write_text(json.dumps(data))
            target, action = rule.alert("no board progress for 3 ticks", None, board)
            exact(action, "wrote")
            exact(len(json.loads(board.read_text())["items"]), 1)
            # The acknowledgement quiets it. The panel passes the cause
            # the item shows, and only that cause is quiet.
            shown = json.loads(board.read_text())["items"][0]["cause"]
            exact(alarms.main(["ack", "factory-overnight-stall", shown]), 0)
            target, action = rule.alert("no board progress for 3 ticks", None, board)
            exact(action, "quiet")
            exact(json.loads(board.read_text())["items"], [])
            # A different cause is a different alarm and is written at once.
            target, action = rule.alert("the board stopped for another reason", None, board)
            exact(action, "wrote")
            exact(len(json.loads(board.read_text())["items"]), 1)

    # An alarm on the board always has a key: the stall writes no board
    # item is published anyway when its key cannot be written, and the
    # fault is said out loud: a storage failure must not hide a real
    # failure.
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        with patch.object(alarms, "MUTE_PATH", mute):
            board = Path(scratch) / "decisions.json"
            board.write_text(json.dumps({"items": []}))
            buffer = io.StringIO()
            with patch.object(alarms, "write_state", return_value=False), \
                 contextlib.redirect_stdout(buffer):
                target, action = rule.alert("no board progress for 3 ticks", None, board)
            exact(action, "wrote")
            items = json.loads(board.read_text())["items"]
            exact(len(items), 1)
            exact("the alarm key could not be written" in buffer.getvalue(), True)

    # The real path: the shift asks again on every tick of a stall that
    # continues, so the alarm can come back when the four hours are over
    # and the log says one line per tick.
    runner = load_runner()

    # The fixture writes its records under the root it chose, the mute
    # state included: a fixture run never writes a synthetic alarm key
    # into the live state, and never reads a live acknowledgement.
    from argparse import Namespace
    with tempfile.TemporaryDirectory() as scratch:
        fixture = Path(scratch) / "fixture.json"
        fixture.write_text(json.dumps({
            "items": [{"repo": "a/one", "number": 1}],
            "ticks": [{"a/one#1": "same|1"}] * 4,
        }))
        root = Path(scratch) / "root"
        live = str(Path(scratch) / "live-mute-state.json")
        with patch.object(alarms, "MUTE_PATH", live):
            runner.run_stall_fixture(Namespace(root=str(root), fixture=str(fixture)))
            exact(alarms.MUTE_PATH, str(root / "run" / "mute-state.json"))
            exact((root / "run" / "mute-state.json").exists(), True)
            exact(Path(live).exists(), False)

    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        board = Path(scratch) / "decisions.json"
        with patch.object(alarms, "MUTE_PATH", mute), \
             patch.object(rule, "BOARD_FILE", str(board)):
            board.write_text(json.dumps({"items": []}))
            state = rule.new_state()
            state["board_idle"] = 3
            event = {"kind": "board", "idle": 3, "cap": 3}
            written = runner.stall_records(Path(scratch), [event], str(board), state)
            exact(len(written), 1)
            items = [i for i in json.loads(board.read_text())["items"]
                     if i["id"] == "factory-overnight-stall"]
            exact(len(items), 1)
            # The rule stops asking once the alert was delivered, and the
            # shift asks anyway.
            exact(rule.continues(state), True)
            # Shyam answers the alarm: the acknowledgement is recorded,
            # for the cause the panel showed.
            shown = json.loads(board.read_text())["items"][0]["cause"]
            exact(alarms.main(["ack", "factory-overnight-stall", shown]), 0)
            # The next tick has no event, and the alarm stays quiet.
            runner.stall_records(Path(scratch), [], str(board), state)
            exact(json.loads(board.read_text())["items"], [])
            runner.stall_records(Path(scratch), [], str(board), state)
            exact(json.loads(board.read_text())["items"], [])
            # The shift's log says one line per tick.
            log = (Path(scratch) / "run" / "shift-log.md").read_text()
            exact(log.count("stall: no board progress"), 3)

    # The watchdog raises the alarm, and the same cause stays quiet once
    # it is acknowledged. A changed cause alarms at once, and the alarm
    # comes back after four hours.
    with tempfile.TemporaryDirectory() as scratch:
        mute = str(Path(scratch) / "mute-state.json")
        with patch.object(alarms, "MUTE_PATH", mute):
            board = Path(scratch) / "decisions.json"
            board.write_text(json.dumps({"items": []}))
            codes = {"code": 1}

            def state_of(label):
                if label == "dev.coordinator.gatekeep":
                    return {"loaded": True, "runs": 3, "exit_code": codes["code"],
                            "signal": None, "running": False, "pid": 0}
                return {"loaded": True, "runs": 3, "exit_code": 0, "signal": None,
                        "running": False, "pid": 0}

            def pass_once(clock):
                class Clock(dt.datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return clock

                buffer = io.StringIO()
                with patch.object(lane, "DECISIONS_PATH", str(board)), \
                     patch.object(lane, "log_age", return_value=1.0), \
                     patch.object(lane, "launchd_state", side_effect=state_of), \
                     patch.object(dt, "datetime", Clock):
                    with contextlib.redirect_stdout(buffer):
                        lane.watchdog()
                return buffer.getvalue()

            output = pass_once(now)
            items = json.loads(board.read_text())["items"]
            exact(len(items), 1)
            exact(items[0]["id"], "factory-watchdog")
            exact(items[0]["cause"], "gatekeep failing (last exit code 1)")
            exact("WATCHDOG" in output, True)

            # An alarm nobody answered is raised again, even when its
            # board item went missing.
            data = json.loads(board.read_text())
            data["items"] = []
            board.write_text(json.dumps(data))
            output = pass_once(now + dt.timedelta(minutes=3))
            items = json.loads(board.read_text())["items"]
            exact(len(items), 1)
            exact("WATCHDOG quiet" in output, False)

            # The acknowledgement quiets it: the board holds no item and
            # the tick says so. The command runs on the clock the tick
            # runs on.
            class AckClock(dt.datetime):
                @classmethod
                def now(cls, tz=None):
                    return now + dt.timedelta(minutes=6)

            with patch.object(dt, "datetime", AckClock):
                exact(alarms.main(["ack", "factory-watchdog", cause]), 0)
            output = pass_once(now + dt.timedelta(minutes=6))
            items = json.loads(board.read_text())["items"]
            exact(items, [])
            exact("WATCHDOG quiet" in output, True)

            # A changed cause is a different key and alarms at once.
            codes["code"] = 78
            output = pass_once(now + dt.timedelta(minutes=9))
            items = json.loads(board.read_text())["items"]
            exact(len(items), 1)
            exact(items[0]["cause"], "gatekeep failing (last exit code 78)")

            # The same cause comes back after four hours.
            data = json.loads(board.read_text())
            data["items"] = []
            board.write_text(json.dumps(data))
            codes["code"] = 1
            output = pass_once(now + dt.timedelta(hours=4, minutes=10))
            items = json.loads(board.read_text())["items"]
            exact(len(items), 1)
            exact(items[0]["cause"], "gatekeep failing (last exit code 1)")

            # A tick where the job is healthy does not take the mute with
            # it: the same cause stays quiet for the rest of the four
            # hours.
            class LaterClock(dt.datetime):
                @classmethod
                def now(cls, tz=None):
                    return now + dt.timedelta(hours=4, minutes=11)

            with patch.object(dt, "datetime", LaterClock):
                exact(alarms.main(["ack", "factory-watchdog", cause]), 0)
            data = json.loads(board.read_text())
            data["items"] = []
            board.write_text(json.dumps(data))
            codes["code"] = 0
            output = pass_once(now + dt.timedelta(hours=4, minutes=12))
            exact(json.loads(board.read_text())["items"], [])
            codes["code"] = 1
            output = pass_once(now + dt.timedelta(hours=4, minutes=13))
            exact(json.loads(board.read_text())["items"], [])
            exact("WATCHDOG quiet" in output, True)

            # An alarm on the board always has a key: the key is written
            # before the alarm is published. A key that cannot be written
            # is said out loud, and the alarm is published anyway: a
            # storage failure must not hide a real failure.
            codes["code"] = 78
            with patch.object(alarms, "write_state", return_value=False):
                output = pass_once(now + dt.timedelta(hours=4, minutes=14))
            items = json.loads(board.read_text())["items"]
            exact(len(items), 1)
            exact(items[0]["id"], "factory-watchdog")
            exact("the alarm key could not be written" in output, True)

            # A quiet tick writes nothing, so a write that fails cannot
            # turn a muted alarm into a published one.
            codes["code"] = 1
            with patch.object(alarms, "write_state", return_value=False):
                output = pass_once(now + dt.timedelta(minutes=30))
            items = [i for i in json.loads(board.read_text())["items"]
                     if i["id"] == "factory-watchdog"]
            exact(items, [])
            exact("WATCHDOG quiet" in output, True)

            # A new cause raises its own alarm, so the board holds the
            # watchdog's item.
            codes["code"] = 78
            output = pass_once(now + dt.timedelta(minutes=33))
            ids = [i["id"] for i in json.loads(board.read_text())["items"]]
            exact("factory-watchdog" in ids, True)
            # The board is read under the lock, so the two writers do not
            # lose each other's item: the stall writer adds its item and
            # the watchdog's item stays.
            target, action = rule.alert("no board progress for 3 ticks", None, board)
            ids = [i["id"] for i in json.loads(board.read_text())["items"]]
            exact("factory-watchdog" in ids, True)
            exact("factory-overnight-stall" in ids, True)

            # The board lock is held while the board is read, changed
            # and replaced, and it is its own file, so a mute storage
            # that cannot be locked does not leave the board open.
            import fcntl
            import os as _os
            held = []
            real_write_board = alarms.write_board

            def watched_write_board(path, board_state):
                if str(path) == str(board):
                    other = _os.open(str(str(board) + ".lock"),
                                     _os.O_RDWR | _os.O_CREAT, 0o600)
                    try:
                        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        held.append(False)
                        fcntl.flock(other, fcntl.LOCK_UN)
                    except OSError:
                        held.append(True)
                    finally:
                        _os.close(other)
                return real_write_board(path, board_state)

            codes["code"] = 1
            with patch.object(alarms, "write_board", side_effect=watched_write_board):
                output = pass_once(now + dt.timedelta(hours=4, minutes=43))
            exact(held, [True])

            # A board that cannot be written is said out loud: the alarm
            # is nowhere, and the tick says so.
            with patch.object(alarms, "write_board", return_value=False):
                output = pass_once(now + dt.timedelta(hours=4, minutes=40))
            exact("could not be published" in output, True)

            # A board that cannot be read is said out loud too: the alarm
            # is nowhere, and the tick says so.
            board.unlink()
            output = pass_once(now + dt.timedelta(hours=4, minutes=41))
            exact("could not be published" in output, True)
            board.write_text(json.dumps({"items": []}))

            # The healthy branch cleans the board even when the mute
            # state cannot be locked or read: a stale alarm must not
            # stay on the board.
            codes["code"] = 78
            pass_once(now + dt.timedelta(hours=4, minutes=44))
            ids = [i["id"] for i in json.loads(board.read_text())["items"]
                   if i["id"] == "factory-watchdog"]
            exact(ids, ["factory-watchdog"])
            codes["code"] = 0
            real_take_lock = alarms.take_lock

            def mute_lock_only(path=None):
                """Fail the mute lock, and leave the board lock alone."""
                if path is None or str(path) == str(Path(str(mute) + ".lock")):
                    return None
                return real_take_lock(path)

            with patch.object(alarms, "take_lock", side_effect=mute_lock_only):
                output = pass_once(now + dt.timedelta(hours=4, minutes=45))
            ids = [i["id"] for i in json.loads(board.read_text())["items"]
                   if i["id"] == "factory-watchdog"]
            exact(ids, [])




def alarm_mute():
    """The mute rule on one board, then the routing of the owner alarms."""
    import alarms
    import stall as rule
    with patch.object(alarms, "board_for", lambda decisions, alarm_id: Path(decisions)):
        alarm_mute_on_one_board()
    with tempfile.TemporaryDirectory() as scratch, \
            patch.object(alarms, "MUTE_PATH", str(Path(scratch) / "mute-state.json")):
        decisions = Path(scratch) / "decisions.json"
        owner = Path(scratch) / "mac-ops-owner.json"
        stale = {"id": "factory-overnight-stall", "cause": "stale"}
        decisions.write_text(json.dumps({"items": [{"id": "SRW-1"}, stale]}))
        target, action = rule.alert("no board progress for 3 ticks", None, decisions)
        exact(action, "wrote")
        exact([i["id"] for i in json.loads(owner.read_text())["items"]], ["factory-overnight-stall"])
        exact([i["id"] for i in json.loads(decisions.read_text())["items"]], ["SRW-1"])
        exact(alarms.route_update(decisions, "SRW-1", "remove"), "wrote")
        exact(alarms.route_update(decisions, "factory-overnight-stall", "remove"), "wrote")
        exact(json.loads(owner.read_text())["items"], [])
        decisions.write_text(json.dumps({"items": [{"id": "factory-zero-merge"}, {"id": "factory-watchdog"}]}))
        owner.unlink()
        exact(alarms.route_update(decisions, "factory-zero-merge", "remove"), "wrote")
        exact([i["id"] for i in json.loads(decisions.read_text())["items"]], ["factory-watchdog"])
        exact(owner.exists(), False)
        decisions.write_text(json.dumps({"items": [dict(stale, id="factory-zero-merge")]}))
        before = decisions.read_bytes()
        with patch.object(alarms, "take_lock", return_value=None):
            exact(alarms.clear_stale(decisions, "factory-zero-merge"), "failed")
        exact(decisions.read_bytes(), before)
        exact(alarms.board_for(decisions, "prompt-merge-SRW-4"), decisions)
        for alarm in ("lane-close-failed", "lane-gate-split", "merge-pass-stuck", "manual-merge"):
            exact(alarms.board_for(decisions, f"{alarm}-MO-654"), owner)
            for key in ("SRW", "TNR"):
                exact(alarms.board_for(decisions, f"{alarm}-{key}-654"), decisions)
        exact(alarms.board_for(decisions, "lane-gate-rounds-shyamsivakumar-mac-ops-9"), owner)


def router_build():
    """A build or fix launch runs on the router, so a Morph rate limit falls back in-thread.

    The router entry names the route its task type runs, and a payload that
    still names a direct `pi` Morph model is mapped to the router entry
    instead of refused.
    """
    import lane_driver as lane
    queue = load_coordq()
    for task_type, expected in [("standard", "task/standard"), ("rca", "task/rca"),
                                ("risky", "task/risky"), ("design", "task/design"),
                                ("chore", "task/standard"), ("fix", "task/standard")]:
        resolved, refusal = queue.with_model({"taskType": task_type})
        exact(refusal, None)
        exact(resolved["modelSelection"], {"instanceId": "router", "model": expected})
    # A payload that still names a direct `pi` Morph model is mapped, not refused.
    for task_type, model, expected in [("standard", "morph/morph-dsv41flash", "task/standard"),
                                       ("rca", "morph/morph-dsv41flash-1017", "task/rca"),
                                       ("fix", "morph/morph-dsv41flash", "task/standard")]:
        resolved, refusal = queue.with_model({"taskType": task_type,
                                              "modelSelection": {"instanceId": "pi", "model": model}})
        exact(refusal, None)
        exact(resolved["modelSelection"], {"instanceId": "router", "model": expected})
    # A router selection is accepted and resolved for the task type.
    resolved, refusal = queue.with_model({"taskType": "rca",
                                          "modelSelection": {"instanceId": "router", "model": "task/standard"}})
    exact(refusal, None)
    exact(resolved["modelSelection"], {"instanceId": "router", "model": "task/rca"})
    # A route the entry does not configure is refused, not silently defaulted.
    _, refusal = queue.with_model({"taskType": "standard",
                                   "modelSelection": {"instanceId": "router", "model": "task/bogus"}})
    exact(refusal is not None, True)
    # A model of another instance is not mapped to the router.
    _, refusal = queue.with_model({"taskType": "standard",
                                   "modelSelection": {"instanceId": "cursor", "model": "morph/morph-kimik31"}})
    exact(refusal is not None, True)
    # The router entry is blocked only when every Morph identity it covers is.
    router = lane.model_list.router_entry("build")
    exact(lane.model_list.entry_blocked(router, {"pi:morph-dsv41flash"}), False)
    exact(lane.model_list.entry_blocked(router, {"pi:morph-dsv41flash", "pi:morph-dsv41flash-1017"}), True)
    exact(lane.model_list.selection_identities({"instanceId": "router", "model": "task/standard"}),
          {"pi:morph-dsv41flash", "pi:morph-dsv41flash-1017"})
    # The installer still builds the hard route Kimi first.
    exact(lane.model_list.pi_routes("hard"), ["morph/morph-dsv41flash", "morph/morph-dsv41flash-1017"])
    # A review launch still refuses a builder model.
    _, refusal = queue.with_model({"taskType": "review",
                                   "modelSelection": {"instanceId": "pi", "model": "morph/morph-dsv41flash"}})
    exact(refusal is not None, True)


def router_blocked():
    """A router entry with every Morph identity blocked falls to the next entry.

    The shared provider store blocks one identity per Morph model, so the
    router is out only when both are blocked; then the build list continues
    on Cursor and a quick task still ends on Terra.
    """
    import lane_driver as lane
    queue = load_coordq()
    both = {"pi:morph-dsv41flash", "pi:morph-dsv41flash-1017"}
    for list_name, task_type in [("build", "standard"), ("build", "rca"), ("fix", "fix")]:
        exact(lane.model_list.first_available(list_name, None, both, task_type)["id"], "cursor")
    # One blocked Morph model leaves the router in place.
    exact(lane.model_list.first_available("build", None, {"pi:morph-dsv41flash"}, "standard")["id"], "router")
    # A quick task still ends on Terra once Cursor is out too.
    exact(lane.model_list.first_available("build", None, both | {"cursor:default"}, "quick")["id"], "terra")
    # The CLI lookup behind `models.py first build` skips a blocked router too.
    with patch.object(lane.model_list, "blocked_identities", return_value=both):
        exact(lane.model_list.first_other("build")["id"], "cursor")
    # A dead run on a usage limit skips the router entry, so Cursor gets the next attempt.
    thread = {"providerInstanceId": "router", "model": "task/standard"}
    exact(lane.dead_run_model(thread, True), {"instanceId": "cursor", "model": "default"})
    exact(lane.dead_run_model(thread, False), {"instanceId": "router", "model": "task/standard"})
    # The same payload resolves to Cursor from a temp providers-blocked.json.
    with tempfile.TemporaryDirectory() as scratch:
        store = Path(scratch) / lane.model_list.BLOCKED_FILE
        store.write_text(json.dumps({"blocked": {key: {"expires_at": 4102444800} for key in both}}))

        def from_store():
            return {key for key, entry in lane.model_list.read_blocked_file(str(store))["blocked"].items()
                    if lane.model_list.expiry(entry) > time.time()}

        with patch.dict(os.environ, {"COORDQ_DIR": scratch}), \
             patch.object(lane.model_list, "blocked_identities", side_effect=from_store):
            exact(from_store(), both)
            resolved, refusal = queue.with_model({"taskType": "standard"})
    exact(refusal, None)
    exact(resolved["modelSelection"], {"instanceId": "cursor", "model": "default"})


def credit_block():
    """A gate that fails on no credits blocks its provider for every caller.

    The dispatch launch failure and gatekeep's dead-gate retry both read the
    failure. Explicit exhaustion text blocks the provider for an hour and the
    retry goes to the next reviewer. A rate limit or a transport error blocks
    nothing.
    """
    import lane_driver as lane
    coordq = load_coordq()
    model_list = lane.model_list
    review = model_list.entries("review")
    first, second = review[0]["selection"], review[1]["selection"]
    repo = "shyamsivakumar/mac-ops"
    head = "a" * 40
    key = f"gate:{repo}#20:{head}"
    outage = "You have no credits remaining"

    def blocked(scratch):
        file = Path(scratch) / model_list.BLOCKED_FILE
        return model_list.read_blocked_file(str(file))["blocked"] if file.exists() else {}

    def gatekeep(message):
        run = {"runId": "r1", "status": "failed", "error": {"message": message}}
        data = {"thread": {"status": "failed", "latestRunId": "r1", "providerInstanceId": first["instanceId"],
                           "model": first["model"]}, "recentRuns": [run], "items": []}
        args = {"title": "gate", "modelSelection": first}
        event = {"kind": "gate", "pr": f"{repo}#20", "head": head, "key": key, "args": args, "builderModels": []}
        with tempfile.TemporaryDirectory() as scratch, \
             patch.dict(os.environ, {"COORDQ_DIR": scratch}), \
             patch.object(coordq, "DIR", scratch), \
             patch.object(coordq, "LANE_LEDGER", str(Path(scratch) / "lanes-ledger.json")), \
             patch.object(coordq, "gate_candidates", side_effect=lambda *a, **k: iter([event])), \
             patch.object(coordq, "call", return_value=(0, json.dumps(data))), \
             patch.object(coordq.gh_gateway, "remaining_or_none", return_value=None), \
             contextlib.redirect_stdout(io.StringIO()):
            Path(scratch, "queue.json").write_text(json.dumps({"next": 2, "items": [], "gatedHeads": {key: 1}}))
            Path(scratch, "dispatch-receipts.json").write_text(json.dumps({key: "gate"}))
            Path(scratch, "gatekeep-config.json").write_text(json.dumps({"repos": {}}))
            coordq.cmd_gatekeep(argparse.Namespace(config=str(Path(scratch, "gatekeep-config.json")), dry_run=False))
            queue = json.loads(Path(scratch, "queue.json").read_text())
            return queue["items"], blocked(scratch), Path(scratch, "dispatch.log").read_text() if Path(scratch, "dispatch.log").exists() else ""

    items, stored, log = gatekeep(outage)
    identity = model_list.identity(first)
    exact(list(stored), [identity])
    exact(0 < stored[identity]["expires_at"] - time.time() <= 3600, True)
    exact(f"blocked provider {identity} for 1h: no credits remaining" in log, True)
    exact([item["args"]["modelSelection"] for item in items], [second])
    for message in ("429 rate_limit_exceeded", "connect ECONNRESET", "Too many requests"):
        items, stored, _ = gatekeep(message)
        exact(stored, {})

    def dispatch(message):
        item = {"id": 1, "tool": "t3_thread_launch", "title": "gate", "priority": 5000, "attempts": 0,
                "args": {"clientRequestId": key, "taskType": "review", "modelSelection": first}}

        queue_held = threading.Event()
        provider_held = threading.Event()
        reached_queue = []

        def call(tool, args, rules=None):
            if tool == "t3_thread_list":
                return 0, json.dumps({"total": 0, "threads": []})
            queue_held.set()
            return 1, message if args["modelSelection"] == first else "connect ECONNRESET"

        def gatekeeper():
            with model_list.blocked_lock():
                provider_held.set()
                queue_held.wait(10)
                with coordq.Lock(True):
                    reached_queue.append(True)

        with tempfile.TemporaryDirectory() as scratch, \
             patch.dict(os.environ, {"COORDQ_DIR": scratch}), \
             patch.object(coordq, "DIR", scratch), \
             patch.object(coordq, "call", side_effect=call), \
             patch.object(coordq, "read_rules", return_value=""), \
             patch.object(coordq, "safe_refill"):
            Path(scratch, "config.json").write_text(json.dumps({"cap": 3}))
            Path(scratch, "queue.json").write_text(json.dumps({"next": 2, "items": [item], "reserved": {},
                                                               "reservedThreads": {}}))
            gate = threading.Thread(target=gatekeeper, daemon=True)
            gate.start()
            provider_held.wait(10)
            run = threading.Thread(target=coordq.cmd_dispatch, args=(argparse.Namespace(dry_run=False),), daemon=True)
            run.start()
            run.join(10)
            gate.join(10)
            exact((run.is_alive(), gate.is_alive(), reached_queue), (False, False, [True]))
            return blocked(scratch)

    exact(list(dispatch(outage)), [identity])
    exact(dispatch("429 rate_limit_exceeded"), {})


def key_mint():
    """Back-to-back opens against a list that never catches up.

    GitHub's issue list can lag a create by a few seconds, so the list read
    after a create can be missing the issue just made. The key is minted
    from the list and from the keys the repo gave out, so the replay below
    keeps the list stale on purpose: three opens must still give three
    distinct keys, and the record must close the other ways to reuse one.
    """
    ticket = load_ticket()
    from types import SimpleNamespace
    repo = "fixture/repo"
    config = {"repos": {repo: {"key": "MO"}},
              "labels": {"stage": ["backlog"], "priority": [1], "type": ["standard"]},
              "template": ["Goal and why"]}
    ready_body = "## Goal and why\n\nx\n\nProof command: x"
    listed = [{"number": 1, "title": "MO-1 · first"}]
    created = []
    failure = [None]
    record = Path("last-key-fixture_repo-MO.json")

    def gh(args, stdin=None, fresh=False, optional=False):
        if args[:2] == ["issue", "create"]:
            if failure[0]:
                raise ticket.GhError(failure[0], "fixture")
            created.append(args[args.index("--title") + 1])
            return f"https://github.com/{repo}/issues/{len(created) + 1}"
        if args[:1] == ["api"]:
            # The list never catches up: every read is the same page.
            return json.dumps(listed)
        raise AssertionError(f"unexpected gh call: {args}")

    def open_ticket(title, body=ready_body):
        args = SimpleNamespace(repo=repo, title=title, body=body, body_file=None,
                               label="", require_key=False, dry_run=False, repo_dir=None)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            ticket.cmd_open(args)
        return json.loads(output.getvalue())

    def refused(title):
        with contextlib.redirect_stderr(io.StringIO()) as error:
            try:
                open_ticket(title)
            except SystemExit as exit:
                return exit.code, error.getvalue().strip()
        raise AssertionError(f"the open of {title!r} was not refused")

    with tempfile.TemporaryDirectory() as directory, \
         patch.object(ticket, "CACHE_DIR", directory), \
         patch.object(ticket, "load_config", return_value=config), \
         patch.object(ticket, "gh", side_effect=gh), \
         patch.object(ticket, "builder_ids", return_value=[]), \
         patch.object(ticket, "reviewer_ids", return_value=[]):
        exact([open_ticket(f"ticket {n}")["key"] for n in (1, 2, 3)],
              ["MO-2", "MO-3", "MO-4"])
        exact(created, ["MO-2 · ticket 1", "MO-3 · ticket 2", "MO-4 · ticket 3"])
        for bad in ("", "## Goal and why\n\nx"):
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    open_ticket("no proof", bad)
                except SystemExit as exit:
                    exact(exit.code, 2)
                else:
                    raise AssertionError("a body without a proof line was opened")
        # The record sits beside the open lock, so the next open reads it.
        exact(json.loads((Path(directory) / record).read_text()),
              {"number": 4, "unconfirmed": [2, 3, 4], "pending": None})
        # A key an earlier open gave out is refused by hand too, because the
        # list has not shown it yet.
        exact(refused("MO-3 · by hand"),
              (2, "refused: MO-3 was given out by an earlier open and the issue list has not shown it yet"))
        # A listed key past the record still wins: the mint goes one past the
        # larger of the two sources, not one past the record alone.
        listed.insert(0, {"number": 8, "title": "MO-8 · listed"})
        exact(open_ticket("ticket 4")["key"], "MO-9")
        # A failure that establishes rejection frees the key again, so the
        # next open takes the same number instead of leaving a gap.
        failure[0] = "rate_limit"
        exact(refused("ticket 5"), (1, "gh failed (rate_limit): fixture"))
        failure[0] = None
        exact(open_ticket("ticket 5")["key"], "MO-10")
        # A generic error does not establish rejection: `gh` can fail locally
        # after GitHub has made the issue, so the key stays pending and the
        # next open refuses instead of minting it again.
        failure[0] = "error"
        exact(refused("ticket 6"), (1, "gh failed (error): fixture"))
        failure[0] = None
        exact(json.loads((Path(directory) / record).read_text())["pending"], 11)
        exact(refused("ticket 6")[0], 2)
        # The recovery the refusal names: a human checks the repo, then clears
        # `pending`.
        state = json.loads((Path(directory) / record).read_text())
        (Path(directory) / record).write_text(json.dumps({**state, "pending": None}))
        # A new prefix starts at one instead of carrying the old sequence
        # over, and switching back finds the old sequence again.
        config["repos"][repo]["key"] = "NEW"
        exact(open_ticket("ticket 7")["key"], "NEW-1")
        config["repos"][repo]["key"] = "MO"
        exact(open_ticket("ticket 8")["key"], "MO-12")
        # A create whose answer was lost leaves the key pending, and the next
        # open refuses instead of handing the key out again.
        (Path(directory) / record).write_text(json.dumps(
            {"number": 12, "unconfirmed": [12], "pending": 12}))
        code, message = refused("ticket 9")
        exact(code, 2)
        exact(message.startswith("refused: the last open of fixture/repo did not finish, so MO-12 may exist"), True)
        # A record that cannot be read is a refusal, not a reset to zero.
        (Path(directory) / record).write_text("{")
        exact(refused("ticket 10")[0], 2)
        (Path(directory) / record).write_text(json.dumps({"number": "four"}))
        exact(refused("ticket 11")[0], 2)
        # The record is what makes it work: without it the stale list mints
        # the same key again, so the eval would pass on a broken mint.
        (Path(directory) / record).unlink()
        with patch.object(ticket, "read_last_key",
                          return_value={"number": 0, "unconfirmed": [], "pending": None}):
            exact([open_ticket(f"again {n}")["key"] for n in (1, 2, 3)],
                  ["MO-9", "MO-9", "MO-9"])

def close_evidence():
    check = load_ticket().close_check_module()
    head = "a" * 40
    ticket_body = "In: coordinator/bin/close_check.py."

    def proof_item(repo, statuses, pr_body="Refs #7"):
        pull = {"state": "MERGED", "headRefOid": head, "body": pr_body, "mergeCommit": {"oid": "c" * 40},
                "title": "MO-1 · x", "changedFiles": 1}

        def gh_json(args, timeout=60):
            if args[0] == "pr":
                return pull
            if args[0] == "issue":
                return {"body": ticket_body, "title": "MO-1 · x"}
            if args[1].startswith(f"repos/{repo}/pulls/"):
                return [{"filename": "coordinator/bin/close_check.py"}]
            if args[1].startswith(f"repos/{repo}/commits/{head}/statuses"):
                return statuses
            raise AssertionError(f"unexpected gh call: {args}")

        with patch.object(check, "gh_json", gh_json), \
             patch.object(check, "report_state", return_value=("absent", "")):
            items = check.run_check(repo, 7)["items"]
        return {item["item"]: item for item in items}

    srw = check.SRW_REPO
    success = {"context": check.SRW_CHECK_CONTEXT, "state": "success"}
    other = {"context": "other/check", "state": "success"}
    items = proof_item(srw, [other, success])
    exact(items["proof file"]["status"], "pass")
    exact(items["proof file"]["detail"], f"{check.SRW_CHECK_CONTEXT} is success on {head}")
    exact((items["checks"]["status"], items["checks"]["required"]), ("skipped", False))
    for name, statuses in (("failure", [{"context": check.SRW_CHECK_CONTEXT, "state": "failure"}]),
                           ("pending", [{"context": check.SRW_CHECK_CONTEXT, "state": "pending"}]),
                           ("missing", [other]),
                           ("superseded", [{"context": check.SRW_CHECK_CONTEXT, "state": "failure"}, success])):
        exact((name, proof_item(srw, statuses)["proof file"]["status"]), (name, "fail"))
    exact(proof_item(srw, [success, {"context": check.SRW_CHECK_CONTEXT, "state": "failure"}])["proof file"]["status"],
          "pass")
    elsewhere = "shyamsivakumar/fixture"
    exact(proof_item(elsewhere, [], f"Refs #7\nBuilder check: PASS {head}")["proof file"]["status"], "pass")
    exact(proof_item(elsewhere, [], f"Refs #7\nBuilder check: PASS {'b' * 40}")["proof file"]["status"], "fail")
    exact(proof_item(elsewhere, [success], "Refs #7")["proof file"]["status"], "fail")

    coordq = load_coordq()
    recorded = (
        (911, "In: `coordinator/bin/hourly_selftest.py`", ["coordinator/bin/hourly_selftest.py", "coordinator/overnight/selftest.py"], True),
        (917, "In: `scripts/coord_wake_metrics.py` and `evidence/event-inbox-design/tickets/fixtures/`", ["scripts/coord_wake_metrics.py", "coordinator/overnight/selftest.py"], True),
        (928, "In: `runtime/agents/deny-rules.json`, `runtime/agents/deny-merge-guard.py`, `tests/test_install_deny_rules.py`", ["runtime/agents/deny-rules.json", "runtime/pi/AGENTS.md"], True),
        (918, "In: `coordinator/overnight/lane_driver.py`, `coordinator/overnight/selftest.py`", ["coordinator/overnight/lane_driver.py", "coordinator/overnight/selftest.py"], False),
        (923, "In: `coordinator/overnight/overnight`, `coordinator/overnight/selftest.py`", ["coordinator/overnight/overnight", "coordinator/overnight/selftest.py"], False),
        (926, "In: `coordinator/overnight/selftest.py`, an existing module in `tests/`", ["coordinator/overnight/selftest.py", "tests/test_coordq_message_dedupe.py"], False),
        (927, "In: `coordinator/config/AGENT-RULES.md`", ["coordinator/config/AGENT-RULES.md"], False),
    )
    for issue, scope, files, refused in recorded:
        items = [check.item_scope(scope, files + [f"evidence/MO-{issue}/runs.md"], f"evidence/MO-{issue}")]
        exact((issue, bool(coordq.scope_refusal(items))), (issue, refused))
    exact(coordq.scope_refusal([check.item_scope("In: a.py", ["a.py"], "", "502")]), [])

    state = {"scope": recorded[0][1], "runs": 0, "raises": None, "merge": None, "head": "", "removal": "wrote"}
    board = []

    def run_check(repo, pr, issue):
        state["runs"] += 1
        if state["raises"]:
            raise state["raises"]
        files = list(recorded[0][2])
        return {"merge": state["merge"] or state["head"], "files": files,
                "items": [check.item_scope(state["scope"], files, "evidence/MO-911")]}

    def route_update(board_path, card, action, item=None):
        board.append((card, action))
        return state["removal"] if action == "remove" else "wrote"

    def gate(head, dry=False):
        state["head"] = head
        event = {"pr": "r/x#7", "scopeIssue": "911", "head": head}
        return coordq.scope_gate({"proofRequired": True, "key": "MO"}, "r/x", "7", event, f"gate:r/x#7:{head}", dry)

    with tempfile.TemporaryDirectory() as scratch, \
         patch.object(coordq, "DIR", scratch), \
         patch.dict(os.environ, {"COORD_JOURNAL_DIR": scratch}), \
         patch.object(coordq, "gh_json", lambda endpoint: [{"body": state["scope"]}]), \
         patch.object(coordq.close_check, "run_check", run_check), \
         patch.object(coordq.alarms, "route_update", route_update):
        exact((gate("a" * 8), gate("a" * 8), state["runs"], board), (False, False, 1, [("proof-MO-7", "raise")]))
        state["scope"] = recorded[0][1] + ", `coordinator/overnight/selftest.py`"
        state["removal"] = "failed"
        exact((gate("a" * 8), state["runs"], board[-1]), (False, 2, ("proof-MO-7", "remove")))
        exact((gate("a" * 8), gate("a" * 8)), (False, False))
        state["removal"] = "wrote"
        exact((gate("a" * 8), board[-2:]), (True, [("proof-MO-7", "remove")] * 2))
        board.clear()
        exact((gate("a" * 8), board), (True, []))
        for raised in (RuntimeError("gh api failed: HTTP 502"), subprocess.TimeoutExpired("gh", 60), ValueError("bad JSON")):
            state["raises"], state["runs"] = raised, 0
            head = type(raised).__name__[:8].ljust(8, "x")
            exact(([gate(head, True)] + [gate(head) for _ in range(4)], state["runs"]), ([True, False, False, True, True], 3))
        before = coordq.load()
        with patch.object(coordq, "gh_json", side_effect=RuntimeError("HTTP 502")):
            exact((gate("g" * 8, True), coordq.load()), (True, before))
        with patch.object(coordq, "gh_json", side_effect=coordq.gh_gateway.ApiBudgetExhausted("below the floor")):
            try:
                gate("h" * 8)
            except coordq.gh_gateway.ApiBudgetExhausted:
                pass
            else:
                raise AssertionError("the budget stop was swallowed")
        state["raises"], state["merge"] = None, "d" * 8
        wrong = "gate:r/x#7:" + "e" * 8
        exact((gate("e" * 8), wrong in coordq.load().get("scopeHeads", {}), wrong in coordq.load().get("scopeFetch", {})), (False, False, False))
        with coordq.Lock(True):
            queue = coordq.load()
            queue["gatedHeads"] = {"gate:r/x#7:" + "f" * 8: {}}
            coordq.save(queue)
        exact(gate("f" * 8), True)

    mac_ops = "shyamsivakumar/mac-ops"
    sha = "a" * 40
    scope_in = "In: `coordinator/bin/coordq`, `coordinator/overnight/selftest.py`"
    scope_out = "In: `coordinator/bin/coordq`"

    class Reply:
        def __init__(self, stdout=""):
            self.stdout, self.stderr, self.returncode = stdout, "", 0

    def drive(pr_text, scope, receipt=False):
        pr = {"draft": False, "number": 7, "head": {"sha": sha}, "title": "x", "changed_files": 2,
              "body": f"{pr_text}\nBuilder check: PASS {sha}\n", "base": {"ref": "main"}}
        stamp = {"kind": "receipt", "attempt": 1, "requestId": "req-1"}
        comment = {"user": {"login": "me"}, "body": "<!-- coordinator-ticket " + json.dumps(stamp) + " -->"}
        counts, cards, rows = {"checks": 0, "proof": 0}, [], []

        def run(argv, **kwargs):
            if argv[:3] == ["gh", "api", "user"]:
                return Reply("me\n")
            endpoint = argv[-1]
            if endpoint == f"repos/{mac_ops}/pulls?state=open&per_page=100":
                return Reply(json.dumps([[pr]]))
            if endpoint == f"repos/{mac_ops}/issues/951/comments?per_page=100":
                return Reply(json.dumps([[comment] if receipt else []]))
            if endpoint == f"repos/{mac_ops}/issues/951":
                return Reply(json.dumps({"body": scope}))
            if endpoint in (f"repos/{mac_ops}/commits/{sha}/statuses?per_page=100",) or endpoint.endswith("/files?per_page=100"):
                return Reply("[[]]")
            raise AssertionError(f"unexpected read: {endpoint}")

        def checked(repo, number, issue):
            counts["checks"] += 1
            files = ["coordinator/bin/coordq", "coordinator/overnight/selftest.py"]
            return {"merge": sha, "files": files, "items": [check.item_scope(scope, files, "evidence/MO-951")]}

        def no_proof(*args):
            counts["proof"] += 1
            return ""

        with tempfile.TemporaryDirectory() as scratch, contextlib.ExitStack() as stack:
            for patcher in (
                    patch.object(coordq, "DIR", scratch),
                    patch.dict(os.environ, {"COORD_JOURNAL_DIR": scratch}),
                    patch.object(coordq, "LANE_LEDGER", str(Path(scratch) / "lanes-ledger.json")),
                    patch.object(coordq, "load_receipts", lambda: {"req-1": "builder-1"}),
                    patch.object(coordq.gh_gateway, "run", run),
                    patch.object(coordq.gh_gateway, "remaining_or_none", return_value=None),
                    patch.object(coordq, "builder_thread_for_issue", return_value=None),
                    patch.object(coordq, "read_builder_thread", return_value=({"providerInstanceId": "fixture", "model": "m"}, [])),
                    patch.object(coordq, "router_chain", return_value=[]),
                    patch.object(coordq, "gate_proof", return_value=("none", "", "path")),
                    patch.object(coordq, "gate_prompt_state", return_value=coordq.prompt_paths.CLEAR),
                    patch.object(coordq, "backstop_model", return_value={"instanceId": "fixture", "model": "m"}),
                    patch.object(coordq, "gate_args", return_value={"clientRequestId": f"gate:{mac_ops}#7:{sha}", "modelSelection": {"instanceId": "fixture", "model": "m"}, "title": "t", "message": "m"}),
                    patch.object(coordq.model_list, "is_blocked", return_value=False),
                    patch.object(coordq.close_check, "run_check", checked),
                    patch.object(coordq, "proof_gate", no_proof),
                    patch.object(coordq.journal, "emit", lambda name, *rest, **fields: rows.append(name)),
                    patch.object(coordq.alarms, "route_update", lambda board_path, card, action, item=None: cards.append((card, action)) or "wrote"),
                    contextlib.redirect_stderr(io.StringIO()),
                    contextlib.redirect_stdout(io.StringIO())):
                stack.enter_context(patcher)
            settings = Path(scratch) / "gatekeep-config.json"
            settings.write_text(json.dumps({"repos": {mac_ops: {"key": "MO", "projectId": "fixture", "proofRequired": True, "proofOnOpen": True}}}))
            coordq.cmd_gatekeep(argparse.Namespace(config=str(settings), dry_run=False))
            gated = len(coordq.load().get("items", []))
        return gated, cards, rows.count("scope_checked"), counts

    for receipt in (False, True):
        exact(drive("Refs #951", scope_out, receipt), (0, [("proof-MO-7", "raise")], 1, {"checks": 1, "proof": 0}))
        exact(drive("Refs #951", scope_in, receipt), (1, [], 1, {"checks": 1, "proof": 1}))
    exact(drive("no ticket named", scope_out), (1, [], 0, {"checks": 0, "proof": 0}))

    import hashlib
    import proof_run
    real_run = subprocess.run
    real_proof = proof_run.run
    git_spec = importlib.util.spec_from_file_location("real_subprocess", subprocess.__file__)
    real_sub = importlib.util.module_from_spec(git_spec)
    git_spec.loader.exec_module(real_sub)
    scope_text = "In: `coordinator/bin/coordq`, `coordinator/overnight/selftest.py`"

    def proof_body(cmd, scope=scope_text):
        return f"{scope}\nProof command:\n{cmd}\n"

    def sha_of(cmd):
        return hashlib.sha256(cmd.encode()).hexdigest()

    @contextlib.contextmanager
    def arena(*pulls):
        world = {"prs": [{"draft": False, "number": n, "head": {"sha": h}, "title": "x", "changed_files": 2,
                          "user": {"login": "me"}, "body": f"Refs #{n + 944}\nBuilder check: PASS {h}\n",
                          "base": {"ref": "main"}} for n, h in pulls],
                 "issues": {n + 944: {"body": proof_body("true"), "user": {"login": "me"}} for n, _ in pulls},
                 "result": "green", "git": 0, "moved": None, "realgit": False, "pull": 0,
                 "removal": "wrote", "ran": [], "cards": [], "rows": []}

        def run(argv, **kwargs):
            if argv[:3] == ["gh", "api", "user"]:
                return Reply("me\n")
            endpoint = argv[-1]
            if endpoint == f"repos/{mac_ops}/pulls?state=open&per_page=100":
                return Reply(json.dumps([world["prs"]]))
            if endpoint.endswith("/comments?per_page=100") or endpoint.endswith("/files?per_page=100") or "/statuses?" in endpoint:
                return Reply("[[]]")
            return Reply(json.dumps(world["issues"][int(endpoint.rsplit("/", 1)[-1])]))

        def fake_git(argv, **kwargs):
            if argv[0] != "git":
                return real_run(argv, **kwargs)
            if world["git"]:
                raise subprocess.CalledProcessError(1, argv)
            if "fetch" in argv:
                world["pull"] = int(argv[-1].split("/")[2])
            elif argv[-1] == "FETCH_HEAD":
                return Reply(world["moved"] or next(p["head"]["sha"] for p in world["prs"] if p["number"] == world["pull"]))
            elif world["realgit"]:
                return real_sub.run(argv, **kwargs)
            return Reply()

        def proved(mode, repo_dir, head, cmd, signature, record):
            if world["realgit"]:
                return real_proof(mode, repo_dir, head, cmd, signature, record)
            world["ran"].append((head, cmd))
            Path(record).write_text(f"ran {cmd}")
            return {"state": world["result"]}

        def checked(repo, number, issue):
            files = ["coordinator/bin/coordq", "coordinator/overnight/selftest.py"]
            return {"merge": next(p["head"]["sha"] for p in world["prs"] if p["number"] == number),
                    "files": files, "items": [check.item_scope(world["issues"][int(issue)]["body"], files, "evidence/MO-951")]}

        def route_update(board_path, card, action, item=None):
            world["cards"].append((card, action))
            return world["removal"] if action == "remove" else "wrote"

        def opened(issue, cmd, red=True, hashed=True):
            row = {"event": "ticket_opened", "repo": mac_ops, "ticket": issue,
                   "data": {"proof": "red" if red else "prose", **({"proofSha": sha_of(cmd)} if hashed else {})}}
            with open(Path(world["dir"], "events-2026-11.jsonl"), "a") as handle:
                handle.write("not json\n" + json.dumps(row) + "\n")

        def gatekeep(dry=False):
            before = len(world["ran"])
            coordq.cmd_gatekeep(argparse.Namespace(config=world["config"], dry_run=dry))
            return len(coordq.load().get("items", [])), len(world["ran"]) - before

        with tempfile.TemporaryDirectory() as scratch, contextlib.ExitStack() as stack:
            world.update(dir=scratch, opened=opened, gatekeep=gatekeep, config=str(Path(scratch) / "gatekeep-config.json"))
            Path(scratch, "config.json").write_text(json.dumps({"cap": 6, "proofsPerRun": 1}))
            Path(world["config"]).write_text(json.dumps({"repos": {mac_ops: {
                "key": "MO", "projectId": "fixture", "proofRequired": True, "proofOnOpen": True, "checkout": scratch}}}))
            for patcher in (
                    patch.object(coordq, "DIR", scratch),
                    patch.object(coordq, "REPLAY_DIR", str(Path(scratch) / "replay")),
                    patch.dict(os.environ, {"COORD_JOURNAL_DIR": scratch}),
                    patch.object(coordq, "LANE_LEDGER", str(Path(scratch) / "lanes-ledger.json")),
                    patch.object(coordq, "load_receipts", lambda: {}),
                    patch.object(coordq.gh_gateway, "run", run),
                    patch.object(coordq.gh_gateway, "remaining_or_none", return_value=None),
                    patch.object(coordq.subprocess, "run", fake_git),
                    patch.object(proof_run, "run", proved),
                    patch.object(coordq, "builder_thread_for_issue", return_value=None),
                    patch.object(coordq, "read_builder_thread", return_value=({"providerInstanceId": "fixture", "model": "m"}, [])),
                    patch.object(coordq, "router_chain", return_value=[]),
                    patch.object(coordq, "gate_proof", return_value=("none", "", "path")),
                    patch.object(coordq, "gate_prompt_state", return_value=coordq.prompt_paths.CLEAR),
                    patch.object(coordq, "backstop_model", return_value={"instanceId": "fixture", "model": "m"}),
                    patch.object(coordq, "gate_args", lambda *a, **k: {"modelSelection": {"instanceId": "fixture", "model": "m"}, "title": "t", "message": "m"}),
                    patch.object(coordq.model_list, "is_blocked", return_value=False),
                    patch.object(coordq.close_check, "run_check", checked),
                    patch.object(coordq.journal, "emit", lambda name, *rest, **fields: world["rows"].append(name)),
                    patch.object(coordq.alarms, "route_update", route_update),
                    contextlib.redirect_stderr(io.StringIO()),
                    contextlib.redirect_stdout(io.StringIO())):
                stack.enter_context(patcher)
            yield world

    def edit(world, issue=951, cmd="true", scope=scope_text, author=None):
        ticket = world["issues"][issue]
        ticket["body"] = proof_body(cmd, scope)
        ticket["user"] = {"login": author or ticket["user"]["login"]}

    def move(world, head):
        world["prs"][0]["head"]["sha"] = head
        world["prs"][0]["body"] = f"Refs #951\nBuilder check: PASS {head}\n"

    def flags(*groups):
        return sorted(r["carded"] for g in groups for r in coordq.load().get(g, {}).values())

    head_a, head_b, head_c = "a" * 40, "b" * 40, "c" * 40
    narrow = "In: `coordinator/bin/coordq`"
    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        exact((w["gatekeep"](), w["gatekeep"](), w["ran"], w["cards"]), ((1, 1), (1, 0), [(head_a, "true")], []))

    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        w["result"] = "unresolved"
        exact((w["gatekeep"](), w["gatekeep"](), w["cards"]), ((0, 1), (0, 0), [("proof-MO-7", "raise")]))
        move(w, head_b)
        w["result"] = "green"
        exact((w["gatekeep"](), w["cards"][-1], flags("proofHeads")), ((1, 1), ("proof-MO-7", "remove"), [False, False]))

    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        edit(w, scope=narrow)
        exact((w["gatekeep"](), w["cards"]), ((0, 0), [("proof-MO-7", "raise")]))
        edit(w)
        exact((w["gatekeep"](), w["cards"]), ((1, 1), [("proof-MO-7", "raise"), ("proof-MO-7", "remove")]))

    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        w["result"] = "unresolved"
        w["gatekeep"]()
        move(w, head_b)
        edit(w, scope=narrow)
        exact((w["gatekeep"](), w["cards"][-1], flags("scopeHeads", "proofHeads")), ((0, 0), ("proof-MO-7", "raise"), [False, False, True]))
        edit(w)
        exact((w["gatekeep"](), w["cards"][-1], flags("proofHeads")), ((0, 1), ("proof-MO-7", "raise"), [False, True]))

    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        w["result"] = "unresolved"
        w["gatekeep"]()
        w["result"], w["removal"] = "green", "failed"
        move(w, head_b)
        exact((w["gatekeep"](), w["gatekeep"](), w["cards"][-2:], flags("proofHeads")), ((0, 1), (0, 0), [("proof-MO-7", "remove")] * 2, [False, True]))
        w["removal"] = "wrote"
        exact((w["gatekeep"](), w["gatekeep"](), flags("proofHeads")), ((1, 0), (1, 0), [False, False]))

    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        edit(w, author="other")
        exact((w["gatekeep"](), w["gatekeep"](), w["cards"]), ((0, 0), (0, 0), [("proof-MO-7", "raise")]))
        edit(w, author="me")
        exact((w["gatekeep"](), w["cards"][-1]), ((1, 1), ("proof-MO-7", "remove")))

    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        edit(w, cmd="false")
        exact((w["gatekeep"](), w["gatekeep"](), w["cards"]), ((0, 0), (0, 0), [("proof-MO-7", "raise")]))
        edit(w)
        exact((w["gatekeep"](), w["cards"][-1]), ((1, 1), ("proof-MO-7", "remove")))

    with arena((7, head_a)) as w:
        exact((w["gatekeep"](), w["ran"]), ((1, 0), []))
    with arena((7, head_a)) as w:
        w["opened"](951, "true", hashed=False)
        edit(w, cmd="other")
        exact((w["gatekeep"](), w["ran"]), ((1, 1), [(head_a, "other")]))
    with arena((7, head_a)) as w:
        w["opened"](951, "none (prose)", hashed=False)
        edit(w, cmd="none (prose)")
        exact((w["gatekeep"](), w["ran"]), ((1, 0), []))
    with arena((7, head_a)) as w:
        w["opened"](951, "false")
        w["opened"](951, "true")
        exact((w["gatekeep"](), w["ran"]), ((1, 1), [(head_a, "true")]))
    with arena((7, head_a)) as w:
        Path(w["dir"], "events-2026-10.jsonl").mkdir()
        exact(([w["gatekeep"]() for _ in range(3)], w["ran"], w["cards"]), ([(0, 0)] * 3, [], [("proof-MO-7", "raise")]))

    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        w["git"] = 1
        exact(([w["gatekeep"]() for _ in range(3)], w["cards"]), ([(0, 0)] * 3, [("proof-MO-7", "raise")]))
        w["git"] = 0
        with patch.object(coordq, "PROOF_RETRY_SECONDS", -1):
            exact((w["gatekeep"](), w["cards"][-1], w["ran"]), ((1, 1), ("proof-MO-7", "remove"), [(head_a, "true")]))

    with arena((7, head_a), (8, head_b)) as w:
        w["opened"](951, "true")
        w["opened"](952, "true")
        exact((w["gatekeep"](), w["gatekeep"](), [h for h, _ in w["ran"]]), ((1, 1), (2, 1), [head_a, head_b]))

    with arena((7, head_a), (8, head_b), (9, head_c)) as w:
        for issue in (951, 952, 953):
            w["opened"](issue, "true")
        Path(w["dir"], "config.json").write_text(json.dumps({"cap": 6, "proofsPerRun": 2}))
        exact((w["gatekeep"](), w["gatekeep"](), [h for h, _ in w["ran"]]), ((2, 2), (3, 1), [head_a, head_b, head_c]))

    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        w["gatekeep"](True)
        exact((coordq.load().get("proofHeads"), w["cards"], w["ran"], w["rows"]), (None, [], [], []))
        with coordq.Lock(True):
            queue = coordq.load()
            queue["gatedHeads"] = {f"gate:{mac_ops}#7:{head_a}": {}}
            coordq.save(queue)
        exact((w["gatekeep"](), w["ran"]), ((0, 0), []))

    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        w["moved"] = head_b
        exact(([w["gatekeep"]() for _ in range(3)], w["ran"], w["cards"]), ([(0, 0)] * 3, [], [("proof-MO-7", "raise")]))
        exact(coordq.load()["proofHeads"]["gate:" + mac_ops + "#7:" + head_a]["tail"], f"the pull request head moved to {head_b[:8]}")

    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        w["realgit"] = True
        for argv in (["init", "-q"], ["-c", "user.name=x", "-c", "user.email=x@x", "commit", "-q", "--allow-empty", "-m", "x"]):
            real_sub.run(["git", "-C", w["dir"]] + argv, check=True, capture_output=True)
        exact(([w["gatekeep"]() for _ in range(3)], w["cards"]), ([(0, 0)] * 3, [("proof-MO-7", "raise")]))
        exact(coordq.load()["proofHeads"]["gate:" + mac_ops + "#7:" + head_a]["tail"], f"the head {head_a[:8]} is not in the checkout")

    with arena((7, head_a)) as w:
        w["opened"](951, "true")
        w["gatekeep"]()
        key = f"gate:{mac_ops}#7:{head_a}"
        event = {"pr": f"{mac_ops}#7", "head": head_a, "scopeIssue": "951", "login": "me", "prAuthor": "me"}
        gated = coordq.proof_gate({"key": "MO", "proofRequired": True}, mac_ops, "7", event, key, False, set())
        exact((gated, w["ran"], w["cards"]), ("\n\nProof run by Gatekeep on this head (green):\nran true\n", [(head_a, "true")], []))


def provider_until():
    """A provider block ends by a successful probe, never by its time, and an unknown model is dropped."""
    import lane_driver as lane
    model_list = lane.model_list
    loader = importlib.machinery.SourceFileLoader("fixture_models", str(Path(model_list.__file__)))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    real = importlib.util.module_from_spec(spec)
    loader.exec_module(real)
    key = model_list.identity(model_list.entries("review")[0]["selection"])

    def blocked(name, entry):
        with tempfile.TemporaryDirectory() as scratch, \
             patch.dict(os.environ, {"COORDQ_DIR": scratch}), \
             patch.object(model_list, "blocked_identities", real.blocked_identities):
            Path(scratch, model_list.BLOCKED_FILE).write_text(json.dumps({"blocked": {name: entry}}))
            return model_list.blocked_identities()

    exact(key in blocked(key, {"by": "provider_block", "until": "2001-09-08T00:00:00Z"}), True)
    exact(key in blocked(key, {"by": "provider_block", "until": "2001-09-10T00:00:00Z"}), True)
    exact(key in blocked(key, {"by": "manual"}), True)
    exact("gone:retired-model" in blocked("gone:retired-model", {"expires_at": 4102444800}), False)

    coordq = load_coordq()

    def probe(entry, launch, run=None, runs=1, hang=False):
        calls = []
        clock = [1000.0]
        timeouts = []

        def t3(tool, args, timeout=coordq.T3MCP_TIMEOUT):
            calls.append((tool, args.get("action") or args.get("title")))
            if hang and tool != "t3_thread_launch":
                timeouts.append(timeout)
                clock[0] += timeout
                return 1, "t3 call timed out"
            if tool == "t3_thread_launch":
                return launch
            if tool == "t3_thread_read":
                return 0, json.dumps({"thread": {"status": run[0], "latestRunId": "r1"},
                                      "recentRuns": [{"runId": "r1", "status": run[0]}],
                                      "items": [{"type": "assistant_message", "text": run[1]}]})
            return 0, "{}"

        with tempfile.TemporaryDirectory() as scratch, \
             patch.dict(os.environ, {"COORDQ_DIR": scratch}), \
             patch.object(model_list, "blocked_identities", real.blocked_identities), \
             patch.object(model_list, "stale_blocks", real.stale_blocks), \
             patch.object(model_list, "unblock", real.unblock), \
             patch.object(model_list, "probe_started", real.probe_started), \
             patch.object(coordq.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)), \
             patch.object(coordq.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(coordq, "t3_call", side_effect=t3):
            Path(scratch, model_list.BLOCKED_FILE).write_text(json.dumps({"blocked": {key: entry}}))
            for _ in range(runs):
                coordq.probe_one_block()
            stored = model_list.read_blocked_file(str(Path(scratch, model_list.BLOCKED_FILE)))["blocked"]
            probe.elapsed = clock[0] - 1000.0
            probe.timeouts = timeouts
            return [name for name, _ in calls], stored.get(key, {}).get("blocked_at"), [label for name, label in calls if name != "t3_thread_read"]

    lapsed = {"by": "provider_block", "until": "2001-09-08T00:00:00Z"}
    started = (0, json.dumps({"thread": {"threadId": "probe-1"}}))
    archived = ["t3_thread_launch", "t3_thread_read", "t3_thread_organize"]
    names, at, labels = probe(lapsed, started, ("completed", "ok"))
    exact((names, at, labels), (archived, None, [f"probe {key}", "archive"]))
    names, at, _ = probe({"by": "manual"}, started, ("completed", "Ok."))
    exact((names, at), ([], None))
    names, at, _ = probe(lapsed, started, ("failed", "no credits remaining"))
    exact((names, at > time.time() - 60), (archived, True))
    names, at, _ = probe(lapsed, started, ("completed", "no"))
    exact((names, at > time.time() - 60), (archived, True))
    names, at, _ = probe(lapsed, started, ("running", ""))
    exact((names.count("t3_thread_read"), names[-1], at > time.time() - 60), (17, "t3_thread_organize", True))
    names, at, _ = probe(lapsed, started, hang=True)
    exact((names[-1], probe.elapsed <= 90, max(probe.timeouts) <= 60, at > time.time() - 60), ("t3_thread_organize", True, True, True))
    names, at, _ = probe(lapsed, (1, "launch refused"))
    exact((names, at > time.time() - 60), (["t3_thread_launch"], True))
    names, at, _ = probe(lapsed, (1, "launch refused"), runs=2)
    exact(names, ["t3_thread_launch"])
    fresh = time.time()
    exact(probe({**lapsed, "blocked_at": fresh}, started, ("completed", "ok"))[:2], ([], fresh))


def journal_migration():
    """A second writer's file exists before first-use migration runs.

    The destination month file already holds a new row when the old folder
    is migrated, so migration must merge the old rows in rather than skip
    the file, and a second run must not duplicate anything.
    """
    import journal
    with tempfile.TemporaryDirectory() as root:
        old, new = Path(root, "old"), Path(root, "new")
        old.mkdir()
        new.mkdir()
        (old / "events-2026-11.jsonl").write_text('{"a":1}\n{"b":2}\n')
        (old / "events-backfill.jsonl").write_text('{"z":0}\n')
        (new / "events-2026-11.jsonl").write_text('{"b":2}\n{"c":3}\n')
        journal._migrate_legacy(str(new), str(old))
        journal._migrate_legacy(str(new), str(old))
        exact((new / "events-2026-11.jsonl").read_text().splitlines(), ['{"a":1}', '{"b":2}', '{"c":3}'])
        exact((new / "events-backfill.jsonl").read_text().splitlines(), ['{"z":0}'])
        exact((new / ".migrated").exists(), True)


def stop_rules():
    import tick_health as health

    def hold(ts=0, head="a" * 40, reason="loop code hold", event="merge_held", pr=7):
        return {"ts": ts, "event": event, "repo": "o/r", "pr": pr, "head": head, "data": {"reason": reason}}

    def verdict(ts, pr=9, result="FAIL"):
        return {"ts": ts, "event": "gate_verdict", "repo": "o/r", "pr": pr, "head": "b" * 40, "data": {"verdict": result}}

    def acted(ts):
        return {"ts": ts, "event": "launched", "repo": "o/r", "pr": None, "data": {"via_tick": True}}

    hour = 3600
    held = health.held_alarm
    exact("o/r#7" in held([hold()], now=7 * hour, hours=6), True)
    exact("prompt hold" in held([hold(reason="prompt hold")], now=7 * hour, hours=6), True)
    exact(held([hold()], now=5 * hour, hours=6), "")
    exact(held([hold(reason="manual repo")], now=70 * hour, hours=6), "")
    for event in ("merged", "merged_outside_lane"):
        exact(held([hold(), hold(9, event=event)], now=7 * hour, hours=6), "")
    exact(held([hold(), hold(9, head="c" * 40, event="gate_queued")], now=7 * hour, hours=6), "")
    exact("o/r#7" in held([hold(), hold(9, pr=8, event="merged")], now=7 * hour, hours=6), True)
    exact(held([hold()], now=8 * 24 * hour, hours=6), "")
    for bad in (None, "", float("nan"), -1, 0, "x"):
        exact("o/r#7" in held([hold()], now=7 * hour, hours=bad), True)
        exact(held([hold()], now=3 * hour, hours=bad), "")
    exact(held(["x", None, {"ts": "1", "pr": 7}, {"ts": 1, "repo": "o/r", "pr": [1]}, hold()], now=7 * hour, hours=6).count("ALARM"), 1)

    ticks = [100 * hour + n * 1800 for n in range(8)]
    now = ticks[-1] + 60
    idle = health.idle_alarm
    waiting = [verdict(50 * hour)]
    exact("o/r#9" in idle(waiting, ticks, now=now, count=8), True)
    exact(idle([], ticks, now=now, count=8), "")
    exact(idle([verdict(50 * hour, result="PASS")], ticks, now=now, count=8), "")
    exact(idle(waiting + [acted(ticks[3])], ticks, now=now, count=8), "")
    exact(idle(waiting + [acted(ticks[0] - 300)], ticks, now=now, count=8), "")
    exact(idle(waiting + [acted(now + 5)], ticks, now=now, count=8), "")
    exact(idle(waiting + [acted(ticks[0] - 700)], ticks, now=now, count=8) != "", True)
    exact(idle(waiting + [hold(60 * hour, pr=9)], ticks, now=now, count=8), "")
    exact(idle(waiting, ticks[1:], now=now, count=8), "")
    exact(idle([verdict(now - 8 * 24 * hour)], ticks, now=now, count=8), "")
    for bad in (None, "", float("nan"), -1, 2.5):
        exact(idle(waiting, ticks, now=now, count=bad) != "", True)
        exact(idle(waiting, ticks[1:], now=now, count=bad), "")

    exact("o/r#7" in held([hold()], now=7 * hour, hours=6, state=lambda *a: "live"), True)
    exact(held([hold()], now=7 * hour, hours=6, state=lambda *a: "stale"), "")
    exact("o/r#7" in held([hold()], now=7 * hour, hours=6, state=lambda *a: "unknown"), True)
    exact("not read" in held([hold()], now=7 * hour, hours=6, state=lambda *a: "unknown"), True)
    exact("not read" in held([hold()], now=7 * hour, hours=6, state=lambda *a: "live"), False)
    asked = []
    held([hold(), hold(pr=8, ts=0), hold(9 * hour, pr=9), hold(ts=0, pr=10, reason="manual repo")], now=7 * hour, hours=6,
         state=lambda *a: asked.append(a) or "live")
    exact(sorted(asked), [("o/r", 7, "a" * 40), ("o/r", 8, "a" * 40)])
    two = [verdict(50 * hour), verdict(50 * hour, pr=10)]
    stale_nine = lambda repo, pr, head: "stale" if pr == 9 else "live"
    got = idle(two, ticks, now=now, count=8, state=stale_nine)
    exact(("o/r#10" in got, "o/r#9" in got), (True, False))
    exact(idle(two, ticks, now=now, count=8, state=lambda *a: "stale"), "")
    exact("o/r#9 (state not read)" in idle(waiting, ticks, now=now, count=8, state=lambda *a: "unknown"), True)
    exact(idle([{**verdict(50 * hour), "head": None}], ticks, now=now, count=8, state=lambda *a: "live") != "", True)
    headless = verdict(50 * hour)
    del headless["head"]
    seen = []
    idle([headless], ticks, now=now, count=8, state=lambda *a: seen.append(a) or "live")
    exact(seen, [("o/r", 9, None)])
    exact(idle(waiting, ticks, now=now, count=8, state=lambda *a: "stale"), "")

    import gh_gateway

    def pull(state="open", sha="a" * 40):
        return json.dumps({"state": state, "head": {"sha": sha}})

    def reading(*results):
        calls = []

        def fake(argv, timeout=60, **kwargs):
            calls.append((argv, timeout, kwargs))
            result = results[min(len(calls), len(results)) - 1]
            if isinstance(result, BaseException):
                raise result
            return subprocess.CompletedProcess(argv, *result)
        return fake, calls

    def ask(result, repo="o/r", pr=7, head="a" * 40):
        fake, calls = reading(result)
        with patch.object(gh_gateway, "run", fake), patch.object(gh_gateway, "floor", return_value=500):
            return health.pr_state_reader()(repo, pr, head), calls

    exact(ask((0, pull()))[0], "live")
    exact(ask((0, pull(sha="A" * 40)))[0], "live")
    exact(ask((0, pull(sha="b" * 40)))[0], "stale")
    exact(ask((0, pull("closed")))[0], "stale")
    exact(ask((0, pull()), head=None)[0], "live")
    for bad in ((0, "not json"), (0, "[]"), (0, "{}"), (0, json.dumps({"state": "open"})),
                (0, json.dumps({"state": "open", "head": {"sha": ""}})), (0, json.dumps({"state": "draft", "head": {"sha": "a"}})),
                (1, "", "gh: Not Found (HTTP 404)"), (0, None), gh_gateway.ApiBudgetExhausted("low"),
                subprocess.TimeoutExpired("gh", 10), FileNotFoundError("gh"), KeyError("repos"), ValueError("config")):
        exact(ask(bad)[0], "unknown")
    answer, calls = ask((0, pull()))
    exact((calls[0][0], calls[0][1], calls[0][2]["limit"]), (["gh", "api", "repos/o/r/pulls/7"], 10, 500))
    for repo in ("../x/y", "a/b/../c", "a b/c", "o/r;rm", "o/..", "./r", "o/r\n", "", None, 7):
        answer, calls = ask((0, pull()), repo=repo)
        exact((answer, calls), ("unknown", []))
    exact(ask((0, pull()), pr=True)[1], [])
    fake, calls = reading((0, pull()))
    with patch.object(gh_gateway, "run", fake):
        state = health.pr_state_reader()
        exact([state("o/r", 7, "a" * 40), state("o/r", 7, "b" * 40), state("o/r", 7, "a" * 40)], ["live", "stale", "live"])
        exact(len(calls), 1)
        got = [state("o/r", number, "a" * 40) for number in range(100, 112)]
        exact((got.count("live"), got.count("unknown"), len(calls)), (9, 3, 10))
    fake, calls = reading((0, pull()))
    clock = iter([0.0, 5.0, 12.0, 31.0, 31.0])
    with patch.object(gh_gateway, "run", fake), patch.object(health.time, "monotonic", lambda: next(clock)):
        state = health.pr_state_reader()
        exact([state("o/r", number, "a" * 40) for number in (1, 2, 3)], ["live", "live", "unknown"])
        exact([call[1] for call in calls], [10, 10])

    log = ("2026-03-08 12:00 EDT | tick | exit=0 reply=NOOP\nsecond line\n"
           "2026-03-08 12:30 EDT | tick | exit=1 reply=(empty)\n"
           "2026-03-08 13:00 EDT | tick | tick killed after 600s\n"
           "2025-03-08 12:00 EST | tick | exit=0 reply=x\n"
           "2026-11-01 01:30 EDT | tick | exit=0 reply=a\n2026-11-01 01:30 EST | tick | exit=0 reply=b\n")
    with patch.dict(os.environ, {"TZ": "America/New_York"}):
        time.tzset()
        got = health.finished_ticks(log)
    time.tzset()
    exact((len(got), got[0] - got[1] > 300 * 86400, got[3] - got[2]), (4, True, 3600.0))

    with tempfile.TemporaryDirectory() as root:
        journal_dir = Path(root, "journal")
        journal_dir.mkdir()
        import journal
        (journal_dir / Path(journal.journal_path(time.time())).name).write_text(
            "not json\n" + json.dumps(hold(time.time() - 7 * hour)) + "\n{\"pr\":3,\n")
        env = {"HOME": root, "COORD_JOURNAL_DIR": str(journal_dir)}
        with patch.dict(os.environ, env), patch.object(health, "journal_rows", side_effect=AssertionError("read while off")):
            for switch in ("", "off", "ON", "1"):
                with patch.dict(os.environ, {"COORD_STOP_RULES": switch}):
                    exact(health.stop_rules_alarm(), "")
            os.environ.pop("COORD_STOP_RULES", None)
            exact(health.stop_rules_alarm(), "")
        with patch.dict(os.environ, {**env, "COORD_STOP_RULES": "on"}):
            with patch.object(health, "pr_state_reader", return_value=lambda *a: "unknown"):
                exact("o/r#7 held" in health.stop_rules_alarm(), True)
            with patch.object(health, "pr_state_reader", return_value=lambda *a: "stale"):
                exact(health.stop_rules_alarm(), "")


def builder_receipt():
    coordq = load_coordq()
    repo = "shyamsivakumar/strategy-replay-workbench"
    with tempfile.TemporaryDirectory() as scratch, patch.object(coordq, "DIR", scratch):
        Path(scratch, "dispatch-receipts.json").write_text(json.dumps({f"ticket:{repo}#7:a2": "older"}))
        with patch.object(coordq, "builder_thread_for_issue", return_value="shift-thread") as lookup:
            exact(coordq.record_builder(repo, 1580), "shift-thread")
            exact(coordq.record_builder(repo, 1580), "shift-thread")
            exact(coordq.record_builder(repo, 7), "older")
            exact(lookup.call_count, 1)
        receipts = json.loads(Path(scratch, "dispatch-receipts.json").read_text())
        exact(receipts[f"ticket:{repo}#1580:a1"], "shift-thread")
        with patch.object(coordq, "builder_thread_for_issue", return_value=None):
            exact(coordq.record_builder(repo, 99), None)
        exact(sorted(json.loads(Path(scratch, "dispatch-receipts.json").read_text())),
              [f"ticket:{repo}#1580:a1", f"ticket:{repo}#7:a2"])


def closed_ticket_merge():
    import lane_driver as lane
    repo, head, key = "shyamsivakumar/mac-ops", "a" * 40, "FIX"
    row, merges, items = dict(number=20, state="OPEN", headRefName="builder/fixture", baseRefName="main"), [], []

    def merge(repo_, number, head_, pr, issue, gate, ledger):
        merges.append(issue)

    def decision(item):
        items.append(item["id"])

    def act(reason, verdict=("PASS", {"threadId": "gate"}, "VERDICT: PASS"), unreadable=False, ledger=None, dry=False):
        pr = dict(number=20, state="OPEN", headRefOid=head, labels=[], mergeable="MERGEABLE", body=f"Refs #10\nBuilder check: PASS {head}")
        snapshot = {"repos": {repo: {"prs": [pr], "issues": []}}}

        def read_json(command, **_):
            if command[:3] != ["gh", "issue", "view"]:
                return pr_reads(lane, row)(command)
            if unreadable:
                raise RuntimeError("snapshot read failed")
            return {"state": "CLOSED", "stateReason": reason}

        with patch.object(lane, "CFG", {repo: dict(key=key, projectId="fixture")}), \
             patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "DRY", dry), \
             patch.object(lane, "builder_thread", return_value=("10", "live-builder")), \
             patch.object(lane, "gate_verdict", return_value=verdict), patch.object(lane, "read_json", read_json), \
             patch.object(lane, "run", side_effect=AssertionError("unexpected command")), \
             patch.object(lane, "merge_passed_pr", merge), patch.object(lane, "publish_decision", decision):
            return lane.act_on_pr(repo, 20, {} if ledger is None else ledger)

    act("completed")
    exact((merges, items), ([""], []))
    merges.clear()
    ledger = {}
    result = act("not_planned", ledger=ledger)
    exact((merges, items), ([], [f"closed-not-planned-{key}-20"]))
    exact(result, "#20: ticket #10 closed as not planned, no merge, decisions item raised")
    exact(ledger, {f"closed-not-planned:{repo}#20:{head}": "item raised"})
    act("not_planned", ledger=ledger)
    exact(items, [f"closed-not-planned-{key}-20"])
    act("completed", verdict=("absent", None, ""))
    exact(merges, [])
    items.clear()
    result = act("not_planned", unreadable=True)
    exact(result, "skip #20: ticket #10 is not in the open snapshot and its state could not be read")
    exact((merges, items), ([], []))
    act("not_planned", ledger={}, dry=True)
    exact((merges, items), ([], []))


def replay_cases():
    import inbox as store
    import inbox_replay as replay

    def row(ts, event, pr=None, **data):
        return {
            "ts": ts,
            "event": event,
            "actor": "x",
            "repo": "o/r",
            "pr": pr,
            "head": "a" * 40,
            "ticket": None,
            "data": data,
        }

    def write(directory, name, *rows, tail=""):
        with open(os.path.join(directory, name), "a") as fh:
            fh.writelines(json.dumps(r, default=str) + "\n" for r in rows)
            fh.write(tail)

    def alarms():
        return [
            r[0]
            for r in store.connect().execute(
                "SELECT dedupe_key FROM inbox WHERE kind='alarm' ORDER BY id"
            )
        ]

    def fresh():
        return {
            "COORD_JOURNAL_DIR": tempfile.mkdtemp(prefix="selftest-replay-j-"),
            "COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-replay-i-"),
        }

    with patch.dict(os.environ, fresh()):
        jdir = os.environ["COORD_JOURNAL_DIR"]
        write(
            jdir,
            "events-2026-10.jsonl",
            row(100, "gate_verdict", 1),
            row(5000, "gate_verdict", 2),
        )
        write(
            jdir,
            "events-2026-11.jsonl",
            row(6000, "alarm_raised", 0, alarm="a-1"),
            tail='not json\n[1]\n{"ts":1',
        )
        try:
            replay.replay()
        except RuntimeError:
            pass
        else:
            raise AssertionError("replay ran before activation")
        replay.activate(now=1000.0)
        replay.activate(now=9999.0)
        exact(replay.replay(), {"enqueued": 2, "seen_only": 1, "skipped": 2})
        exact(replay.replay(), {"enqueued": 0, "seen_only": 0, "skipped": 0})
        write(jdir, "events-2026-10.jsonl", row(7000, "gate_verdict", 3))
        exact(replay.replay()["enqueued"], 1)
        with open(os.path.join(jdir, "events-2026-11.jsonl"), "a") as fh:
            fh.write(',"event":"gate_verdict"}\n')
        exact(replay.replay(), {"enqueued": 0, "seen_only": 1, "skipped": 0})
        exact(store.counts()["pending"], 3)
        write(jdir, "events-backfill.jsonl", row(8000, "gate_verdict", 9))
        bad = [{"ts": "x", "event": "merged"}, {"ts": None, "event": "merged"}, {"ts": True, "event": "merged"}, {"ts": 9e9, "event": ["a"]}, {"ts": 9e9, "event": "alarm_raised", "data": [1]}, {"ts": 9e9, "event": "merged", "repo": ["r"]}, {"ts": 9e9, "event": "merged", "pr": {"n": 1}}, {"ts": 9e9, "event": "merged", "head": 1.5}, {"ts": 9e9, "event": "merged", "pr": 99999999999999999999}, {"ts": 9e9, "event": "merged", "repo": "\ud800"}, {"ts": 9e9, "event": "alarm_raised", "data": {"alarm": "\ud800"}}, {"ts": 10**400, "event": "merged"}, [1], 7]
        write(jdir, "events-2026-11.jsonl", *bad, row(9100, "alarm_raised", 0, alarm=["a", {"b": 1}]), row(9101, "alarm_withdrawn", 0, alarm={"k": 1}), row(9200, "gate_verdict", 4))
        with open(os.path.join(jdir, "events-2026-11.jsonl"), "a") as fh:
            fh.write('{"ts":9300,"event":"gate_verdict","pr":5,"note":"a\rb"}\r\n')
        exact(replay.replay(), {"enqueued": 2, "seen_only": 0, "skipped": 16})
    with patch.dict(os.environ, {"COORD_JOURNAL_DIR": os.path.join(tempfile.mkdtemp(prefix="selftest-replay-j-"), "missing"), "COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-replay-i-")}):
        replay.activate(now=1.0)
        exact(replay.replay(), {"enqueued": 0, "seen_only": 0, "skipped": 0})
    for steps in (("hook", "replay"), ("replay", "hook")):
        with patch.dict(os.environ, fresh()):
            rows = [
                row(2000 + n, event, 0, alarm="x-1", at=Path("/p"))
                for n, event in enumerate(
                    ("alarm_raised", "alarm_withdrawn", "alarm_raised")
                )
            ]
            write(os.environ["COORD_JOURNAL_DIR"], "events-2026-11.jsonl", *rows)
            replay.activate(now=1000.0)
            for step in steps:
                if step == "replay":
                    replay.replay()
                else:
                    for r in rows:
                        store.record_journal(r, wait=2)
            exact(alarms(), ["alarm:x-1:0", "alarm:x-1:1"])
            replay.replay()
            exact(alarms(), ["alarm:x-1:0", "alarm:x-1:1"])


def disagreement_cases():
    source = ROOT.parent / "evals" / "hillclimb"
    if not source.is_dir():
        return
    spec = importlib.util.spec_from_file_location("burst_disagreements", source / "burst.py")
    sys.path.insert(0, str(source))
    burst = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(burst)

    def v(ts, head, verdict, pr=1, **data):
        return {"ts": ts, "event": "gate_verdict", "repo": "o/r", "pr": pr, "head": head * 40, "data": {"verdict": verdict, **data}}

    def pair(rows):
        return [(r["round1_verdict"], r["round3_verdict"]) for r in burst.disagreements(rows)]

    exact(pair([v(1, "a", "FAIL", **{"class": "logic"}), v(2, "b", "FAIL"), v(3, "c", "PASS")]), [("FAIL", "PASS")])
    exact(pair([v(1, "a", "PASS"), v(2, "b", "PASS"), v(3, "c", "FAIL")]), [("PASS", "FAIL")])
    exact(pair([v(1, "a", "FAIL"), v(2, "b", "PASS"), v(3, "c", "FAIL")]), [])
    exact(pair([v(1, "a", "FAIL"), v(2, "a", "PASS")]), [])
    exact(pair([v(3, "c", "PASS"), v(1, "a", "FAIL"), v(2, "b", "FAIL")]), [("FAIL", "PASS")])
    exact(pair([v(1, "a", "FAIL"), v(2, "a", "PASS"), v(3, "b", "PASS"), v(4, "c", "PASS")]), [])
    exact(pair([v(1, "a", "FAIL"), v(2, "a", "PASS"), v(3, "b", "FAIL"), v(4, "c", "FAIL"), v(5, "a", "FAIL")]), [])
    exact(pair([v(1, "a", "FAIL"), v(2, "b", "FAIL"), v(3, "c", "SPLIT"), v(4, "c", "PASS")]), [("FAIL", "PASS")])
    exact(pair([v(1, "a", "FAIL"), v(2, "b", "FAIL"), v(3, "c", "SPLIT")]), [])
    exact(pair([v(1, "a", "FAIL"), v(2, "b", "FAIL"), v(3, "c", "FAIL"), v(4, "d", "PASS")]), [])
    exact(pair([v(1, "a", "FAIL", pr=1), v(2, "b", "FAIL", pr=2), v(3, "c", "PASS", pr=1), v(4, "d", "PASS", pr=1)]), [("FAIL", "PASS")])
    junk = [None, 7, {}, {"event": "gate_verdict"}, dict(v(9, "z", "PASS"), pr=None), dict(v(9, "z", "PASS"), ts="x"), dict(v(9, "z", "PASS"), ts=float("nan")), dict(v(9, "z", "PASS"), head=""), dict(v(9, "z", "PASS"), data=[1]), dict(v(9, "z", "PASS"), pr=True)]
    exact(pair(junk + [v(1, "a", "FAIL"), v(2, "b", "FAIL"), v(3, "c", "PASS")]), [("FAIL", "PASS")])
    record = burst.disagreements([v(1, "a", "FAIL", **{"class": "logic"}), v(2, "b", "FAIL"), v(3, "c", "PASS")])[0]
    exact((record["round1_class"], record["round1_ts"], record["round3_ts"], record["round1_head"], record["round3_head"]), ("logic", 1, 3, "a" * 40, "c" * 40))

    work = Path(tempfile.mkdtemp(prefix="selftest-disagree-"))
    log = work / "gate_disagreements.jsonl"
    rows = [v(1, "a", "FAIL"), v(2, "b", "FAIL"), v(3, "c", "PASS")]
    exact(len(burst.log_disagreements(rows, log)), 1)
    first = log.read_bytes()
    exact(burst.log_disagreements(rows, log), [])
    exact(log.read_bytes(), first)
    log.write_bytes(b"not json\n[1]\n" + first + b'{"repo":"o/r","pr":2,"round3_he')
    exact(len(burst.log_disagreements(rows + [v(4, "d", "PASS", pr=2), v(5, "e", "PASS", pr=2), v(6, "f", "FAIL", pr=2)], log)), 1)
    lines = log.read_bytes().split(b"\n")
    exact([json.loads(x)["pr"] for x in lines if x.startswith(b'{"pr"') or x.startswith(b'{"round')], [1, 2])
    exact(log.read_bytes().endswith(b"\n"), True)

    jdir = work / "journal"
    jdir.mkdir()
    (jdir / "events-2026-10.jsonl").write_text(json.dumps(v(1, "a", "FAIL")) + "\nnot json\n")
    (jdir / "events-2026-11.jsonl").write_text(json.dumps(v(2, "b", "FAIL")) + "\n")
    (jdir / "events-backfill.jsonl").write_text(json.dumps(v(3, "c", "PASS")) + "\n")
    with patch.dict(os.environ, {"COORD_JOURNAL_DIR": str(jdir)}):
        exact(pair(burst.journal_rows()), [("FAIL", "PASS")])
    with patch.dict(os.environ, {"COORD_JOURNAL_DIR": str(work / "missing")}):
        exact(burst.journal_rows(), [])

    copy = work / "hillclimb"
    copy.mkdir()
    sentinels = {"labels.jsonl": b'{"id":"x"}\n', "split.json": b"{}", "score.lock": b"lock", "burst_queue.jsonl": b'{"id":"q"}\n'}
    for name in ("burst.py", "build_labels.py"):
        (copy / name).write_bytes((source / name).read_bytes())
    for name, body in sentinels.items():
        (copy / name).write_bytes(body)
    for _ in range(2):
        with patch.dict(os.environ, {"COORD_JOURNAL_DIR": str(jdir)}), patch.object(sys, "argv", [str(copy / "burst.py"), "--log-disagreements"]), \
                contextlib.redirect_stdout(io.StringIO()):
            try:
                runpy.run_path(str(copy / "burst.py"), run_name="__main__")
            except SystemExit as done:
                exact(done.code, 0)
    exact({n: (copy / n).read_bytes() for n in sentinels}, sentinels)
    exact(len((copy / "gate_disagreements.jsonl").read_text().splitlines()), 1)


def timer_cases():
    import inbox as store

    with patch.dict(os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-timers-")}):
        def fired():
            return [r[0] for r in store.connect().execute("SELECT dedupe_key FROM inbox ORDER BY id")]

        store.add_timer("t1", due_ts=100.0, period=50.0)
        exact([store.enqueue_due_timers(now=120.0), store.enqueue_due_timers(now=121.0)], [1, 0])
        exact(store.enqueue_due_timers(now=1000.0), 1)
        exact(fired(), ["timer_due:t1:100.0", "timer_due:t1:150.0"])
        store.cancel_timer("t1")
        store.add_timer("once", due_ts=2000.0)
        exact([store.enqueue_due_timers(now=2001.0), store.enqueue_due_timers(now=9000.0)], [1, 0])
        for bad in (0, -5):
            try:
                store.add_timer("bad", due_ts=1.0, period=bad)
            except ValueError:
                continue
            raise AssertionError("period %r accepted" % bad)
        for bad in ([1], "x"):
            try:
                store.add_timer("p", due_ts=1.0, payload=bad)
            except TypeError:
                continue
            raise AssertionError("payload %r accepted" % (bad,))
        store.add_timer("named", due_ts=2500.0, payload={"timer": "other", "k": 1})
        store.enqueue_due_timers(now=2501.0)
        exact(json.loads(store.connect().execute("SELECT payload FROM inbox ORDER BY id DESC").fetchone()[0]), {"timer": "named", "k": 1})
        store.set_last_run(now=10000.0)
        store.ensure_fallback(now=10000.0)
        exact(store.enqueue_due_timers(now=14000.0), 0)
        store.set_last_run(now=17000.0)
        exact([store.enqueue_due_timers(now=17300.0), store.enqueue_due_timers(now=24300.0)], [0, 1])
        exact(fired()[-1].startswith("timer_due:fallback:"), True)
        store.set_last_run(now=712790.0)
        store.enqueue_due_timers(now=719900.0)
        exact([store.enqueue_due_timers(now=719990.0), store.enqueue_due_timers(now=719990.0 + 7199), store.enqueue_due_timers(now=719990.0 + 7200)], [1, 0, 1])


def inbox_poll_cases():
    import inbox as store
    import inbox_poll as poll

    def scratch():
        return patch.dict(os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-poll-")})

    def pr(number, **extra):
        base = dict(number=number, headRefOid="a" * 40, isDraft=False,
                    createdAt="2026-11-22T17:18:16Z", labels=[], reviews=[])
        return dict(base, **extra)

    def payloads(kind):
        with store.txn() as conn:
            return [json.loads(r[0]) for r in conn.execute(
                "SELECT payload FROM inbox WHERE kind=? ORDER BY id", (kind,))]

    prs = [pr(1), pr(2, labels=None, reviews=None)]
    with scratch():
        exact([poll.poll_prs(["o/r"], lambda repo: prs, now=10.0),
               poll.poll_prs(["o/r"], lambda repo: prs, now=11.0)], [2, 0])
    prs = [pr(1), pr(2)]
    with scratch():
        poll.poll_prs(["o/r"], lambda repo: prs, now=10.0)
        prs[1]["headRefOid"] = "b" * 40
        prs[0]["labels"] = [{"name": "merge:human-ok"}, {"name": "merge:human-ok"}]
        exact(poll.poll_prs(["o/r"], lambda repo: prs, now=11.0), 2)
        exact(payloads("human_signal"), [{"verified": False, "label": "merge:human-ok"}])
    prs = [pr(1, reviews=[{"id": "R1", "author": None, "state": "APPROVED",
                           "submittedAt": "2026-11-22T17:18:16Z"},
                          {"id": "R2", "state": "PENDING"}])]
    with scratch():
        exact(poll.poll_prs(["o/r"], lambda repo: prs, now=10.0), 3)
        exact(payloads("pr_review"), [{"review": "R1", "state": "APPROVED"}])
        exact(payloads("human_signal"), [{"verified": False, "review": "R1"}])
    prs = [pr(1, labels=[{"name": "bug"}])]
    with scratch():
        exact(poll.poll_prs(["o/r"], lambda repo: prs, now=10.0), 1)
        exact(payloads("human_signal"), [])
    prs = [pr(1), {"headRefOid": "a" * 40, "createdAt": "2026-11-22T17:18:16Z"}]

    def fetch(repo):
        if repo == "bad/x":
            raise RuntimeError("unreadable")
        return prs

    with scratch():
        exact(poll.poll_prs(["bad/x", "o/r"], fetch, now=10.0), 1)
    prs = [pr(1)]
    with scratch():
        with store.txn() as conn:
            conn.execute("INSERT INTO meta (k, v) VALUES (?,?)",
                         ("activated_at", str(poll._epoch("2026-11-23T00:00:00Z"))))
        exact(poll.poll_prs(["o/r"], lambda repo: prs, now=10.0), 0)
        prs[0]["headRefOid"] = "b" * 40
        exact(poll.poll_prs(["o/r"], lambda repo: prs, now=11.0), 1)
        exact([r[0] for r in store.connect().execute("SELECT kind FROM inbox")], ["pr_new_head"])
    tried = []

    def raising(repo):
        tried.append(repo)
        raise RuntimeError("never")

    with patch.dict(os.environ, {"COORD_INBOX_REPOS": ""}):
        exact(poll.poll_prs(poll.configured_repos(), raising, now=1.0), 0)
    exact(tried, [])
    big = [pr(2 ** 70), pr(True), pr({}), pr(3, headRefOid={}), pr(4, reviews=[{"id": {}, "state": "APPROVED", "submittedAt": "x"}]), pr(5)]
    for bad in (None, {"a": 1}, "x"):
        with scratch():
            exact(poll.poll_prs(["bad/x", "o/r"], lambda repo, bad=bad: bad if repo == "bad/x" else big, now=1.0), 2)
    body = "SECRET-REVIEW-BODY"
    leaky = [pr(1, reviews=[{"id": "R1", "state": "APPROVED", "submittedAt": "nope", "body": body}]), pr(None, body=body)]
    with scratch(), contextlib.redirect_stderr(io.StringIO()) as err:
        poll.poll_prs(["o/r"], lambda repo: leaky, now=1.0)
    exact((body in err.getvalue(), "o/r#1" in err.getvalue()), (False, True))
    calls = []

    def gh(argv, **kw):
        calls.append((argv, kw["limit"]))
        return subprocess.CompletedProcess(argv, *answers.pop(0))

    answers = [(0, "[]", ""), (1, "", "boom"), (0, "not json", "")]
    with patch.object(poll.gh_gateway, "run", gh):
        exact(poll.fetch("o/r"), [])
        for error in (RuntimeError, ValueError):
            try:
                poll.fetch("o/r")
            except error:
                continue
            raise AssertionError("fetch accepted a bad answer")
    exact(calls[0][0], ["gh", "pr", "list", "-R", "o/r", "--state", "open", "--limit", "100",
                        "--json", "number,headRefOid,isDraft,createdAt,labels,reviews"])
    sha = "c" * 40
    status = {"sha": sha, "statuses": [{"context": "srw/agent-check", "state": "pending"},
                                       {"context": "ci/other", "state": "failure"}]}

    def tiers():
        with store.txn() as conn:
            return [r[0] for r in conn.execute("SELECT tier FROM inbox WHERE kind='ci_main' ORDER BY id")]

    with scratch():
        exact(poll.poll_ci(["o/r"], lambda repo: status, now=1.0), 0)
        status["statuses"][0]["state"] = "success"
        exact(poll.poll_ci(["o/r"], lambda repo: status, now=2.0), 1)
        exact(poll.poll_ci(["o/r"], lambda repo: status, now=3.0), 0)
        status["statuses"][0]["state"] = "failure"
        exact(poll.poll_ci(["o/r"], lambda repo: status, now=4.0), 1)
        exact(tiers(), ["batch", "wake"])
        status["statuses"][0]["state"] = "error"
        exact(poll.poll_ci(["o/r"], lambda repo: status, now=5.0), 1)
        exact(tiers(), ["batch", "wake", "wake"])
    good = {"sha": sha, "statuses": [{"context": "srw/agent-check", "state": "failure"}]}
    good_list = [{"context": "srw/agent-check", "state": "failure"}]
    replies = {"bad/x": RuntimeError("unreadable"), "n/a": None, "s/x": {"sha": 7, "statuses": []}, "u/x": {"sha": "\ud800", "statuses": good_list},
               "h/x": {"sha": "ABC", "statuses": good_list},
               "l/x": {"sha": sha, "statuses": "x"}, "w/x": {"sha": sha, "statuses": [
                   None, {"context": {}, "state": "failure"}, {"context": "srw/agent-check", "state": []}]},
               "o/r": good}

    def fetch_ci(repo):
        if isinstance(replies[repo], Exception):
            raise replies[repo]
        return replies[repo]

    with scratch(), contextlib.redirect_stderr(io.StringIO()) as err:
        exact(poll.poll_ci(list(replies), fetch_ci, now=1.0), 1)
    exact(("bad/x: fetch failed: RuntimeError" in err.getvalue(), "unreadable" in err.getvalue()), (True, False))
    more = dict(good, total_count=31)
    with scratch(), contextlib.redirect_stderr(io.StringIO()) as err:
        exact(poll.poll_ci(["o/r"], lambda repo: more, now=1.0), 1)
    exact(err.getvalue(), "o/r: 31 statuses, 1 returned; the rest are not polled\n")
    with scratch(), patch.dict(os.environ, {"COORD_INBOX_CI_CONTEXTS": " a/b, ,c/d "}):
        exact(sorted(poll.ci_contexts()), ["a/b", "c/d"])
    exact(sorted(poll.ci_contexts()), ["srw/agent-check"])
    with patch.dict(os.environ, {"COORD_INBOX_REPOS": ""}):
        exact(poll.poll_ci(poll.configured_repos(), raising, now=1.0), 0)
    exact(tried, [])
    calls.clear()
    answers = [(0, json.dumps(dict(good, extra="x")), ""), (1, "", "boom")]
    with patch.object(poll.gh_gateway, "run", gh):
        exact(poll.fetch_status("o/r"), dict(good, total_count=None))
        try:
            poll.fetch_status("o/r")
        except RuntimeError:
            pass
        else:
            raise AssertionError("fetch_status accepted a failed read")
    exact(calls[0][0], ["gh", "api", "repos/o/r/commits/HEAD/status?per_page=100"])


def outbox_cases():
    import inbox as store
    import inbox_outbox as out

    def statuses():
        with store.txn() as conn:
            return [
                tuple(r)
                for r in conn.execute("SELECT status, attempts FROM outbox ORDER BY id")
            ]

    with patch.dict(
        os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-outbox-")}
    ):
        for value, expected in ((None, True), ("", True), ("1", True), ("0", False)):
            with patch.dict(
                os.environ, {} if value is None else {"COORD_INBOX_SHADOW": value}
            ):
                exact(out.shadow_on(), expected)
        for kind, reason in (("bogus", None), ("none", None), ("none", "  ")):
            try:
                out.add("v", 0, kind, None, "", reason=reason, now=1.0)
            except ValueError:
                continue
            raise AssertionError(kind)
        out.add("s", 0, "hc_send", "t56", "hi", now=1.0)
        calls = []
        exact(out.drain(calls.append, now=2.0), {"would_send": 1})
        exact((calls, statuses()), ([], [("pending", 0)]))
        exact(out.drain(calls.append, now=3.0, shadow=False), {"sent": 1, "errors": 0})
        exact(out.drain(calls.append, now=4.0, shadow=False), {"sent": 0, "errors": 0})
        exact((len(calls), statuses()), (1, [("sent", 1)]))

    def late(kind, expected):
        with patch.dict(
            os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-outbox-")}
        ):
            calls = []
            out.add("l", 0, kind, "t56", "x", now=1.0)

            def sender(row):
                calls.append(row["attempts"])
                if len(calls) == 1:
                    out.reap(now=2000.0)
                    out.drain(sender, now=2001.0, shadow=False)

            exact(out.drain(sender, now=2.0, shadow=False)["sent"], 0)
            exact((calls, statuses()), expected)

    with patch.dict(os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-outbox-")}):
        for index in range(3):
            out.add("c", index, "hc_send", "t56", str(index), now=1.0)
        seen = []

        def crashing(row):
            seen.append(row["body"])
            raise KeyboardInterrupt

        try:
            out.drain(crashing, now=2.0, shadow=False)
        except KeyboardInterrupt:
            pass
        exact((seen, statuses()), (["0"], [("sending", 1), ("pending", 0), ("pending", 0)]))
        exact(out.drain(lambda row: seen.append(row["body"]), now=3.0, shadow=False), {"sent": 2, "errors": 0})
        exact((seen, out.reap(now=900.0)), (["0", "1", "2"], {"unknown": 1}))
    late("hc_send", ([1], [("unknown", 1)]))
    late("coordq_send", ([1, 2], [("sent", 2)]))
    with patch.dict(
        os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-outbox-")}
    ):
        out.add("q", 0, "coordq_send", "x", "y", now=1.0)
        for round_no in range(3):
            exact(
                out.drain(lambda row: 1 / 0, now=10.0 * round_no, shadow=False)[
                    "errors"
                ],
                1,
            )
            exact(
                out.reap(now=10.0 * round_no + 700.0),
                {"unknown": 0, "requeued": 1}
                if round_no < 2
                else {"unknown": 0, "failed": 1},
            )
        exact(statuses(), [("failed", 3)])
    notice_cases(store, out)


def notice_cases(store, out):
    def rows():
        with store.txn() as conn:
            return [tuple(r) for r in conn.execute("SELECT status, reason FROM outbox ORDER BY id")]

    def merged(repo, pr, ts):
        store.enqueue("pr_merged", "m:%s#%s:%s" % (repo, pr, ts), source="journal", ts=ts, repo=repo, pr=pr)
        with store.txn() as conn:
            conn.execute("UPDATE inbox SET status='done' WHERE kind='pr_merged'")

    with patch.dict(os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-notice-")}):
        head = "a" * 40
        exact(out.request_notice("run1", 0, "o/r", 7, head, "merge PR 7", now=10.0), True)
        exact(out.request_notice("run2", 0, "o/r", 7, head, "merge PR 7", now=11.0), False)
        exact(out.add("run1", 0, "hc_send", "t56", "x", now=12.0), True)
        try:
            store.enqueue("approval_answer", "approve:1", source="human", ts=1.0)
        except ValueError:
            pass
        else:
            raise AssertionError("approval kind")
        store.enqueue("human_signal", "forged", source="human", ts=13.0, payload="approve 1")
        merged("o/x", 7, 20.0)
        merged("o/r", 8, 20.0)
        merged("o/r", 7, 5.0)
        with store.txn() as conn:
            grants = [n for (n,) in conn.execute("SELECT name FROM sqlite_master") if "grant" in n.lower()]
        exact((grants, out.close_requests(now=21.0), len(rows())), ([], 0, 2))
        merged("o/r", 7, 15.0)

        def closes_midflight(row):
            exact(out.close_requests(now=22.0), 1)

        exact(out.drain(closes_midflight, now=16.0, shadow=False, limit=1), {"sent": 1, "errors": 0})
        exact(rows(), [("sent", "closed"), ("pending", None)])
        out.request_notice("run3", 0, "o/r", 9, head, "merge PR 9", now=100.0)
        out.request_notice("run3", 1, "o/r", 10, head, "merge PR 10", now=100.0)
        exact(out.reissue_due(now=100.0 + 86400), 0)
        exact([out.reissue_due(now=100.0 + 86401), out.reissue_due(now=100.0 + 90000)], [2, 0])
        merged("o/r", 9, 100.0)
        exact(out.close_requests(now=200000.0), 2)
        exact(out.reissue_due(now=900000.0), 0)
        exact(out.close_requests(now=900001.0), 0)
        exact(out.drain(lambda row: None, now=900002.0, shadow=False), {"sent": 3, "errors": 0})
        exact([r[1] for r in rows()], ["closed", None, "closed", None, "closed", None])
    with patch.dict(os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-notice-")}):
        out.add("k", 0, "none", None, "", reason="closed", now=1.0)
        out.add("k", 1, "hc_send", "t56", "x", reason="closed", now=1.0)
        out.add("k", 2, "request_notice", "t56", "plain text", now=1.0)
        try:
            out.add("notice-x", 0, "hc_send", "t56", "x", now=1.0)
        except ValueError:
            pass
        else:
            raise AssertionError("notice run_id")
        out.request_notice("k", 3, "o/r", 5, "c" * 40, "merge PR 5", now=1.0)
        merged("o/r", 5, 2.0)
        exact((out.close_requests(now=3.0), out.reissue_due(now=90000.0), out.close_requests(now=90001.0)), (1, 0, 0))
        exact(out.drain(lambda row: None, now=90002.0, shadow=False), {"sent": 3, "errors": 0})


def liveness_cases():
    import fcntl
    import signal
    import threading
    import inbox as store
    import inbox_worker as w

    def probe(**k):
        return w.liveness(**{**dict(now=1000.0, lock_held=True, heartbeat=900.0, last_pass_end=0.0, expect_passes=False), **k})

    exact([probe(heartbeat=800.0), bool(probe(heartbeat=700.0)), probe(heartbeat=None) is not None], [None, True, True])
    exact([probe(lock_held=False, last_pass_end=600.0), bool(probe(lock_held=False, last_pass_end=600.0, expect_passes=True)),
           probe(lock_held=False, heartbeat=None, last_pass_end=None, expect_passes=True)], [None, True, None])

    root = tempfile.mkdtemp(prefix="selftest-liveness-")
    missing = os.path.join(root, "never-made")
    with patch.dict(os.environ, {"COORD_INBOX_DIR": missing, "COORD_JOURNAL_DIR": tempfile.mkdtemp(prefix="selftest-liveness-j-")}):
        exact((w.watch(now=1000.0), os.path.exists(missing)), (None, False))
        os.makedirs(missing)
        exact((w.watch(now=1000.0), os.listdir(missing)), (None, []))
        lock = open(os.path.join(missing, w.LOCK), "w")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stale = w.watch(now=1000.0)
        exact(bool(stale), True)
        w._write(os.path.join(missing, w.HEARTBEAT), 900.0)
        exact(w.watch(now=1000.0), None)
        w._write(os.path.join(missing, w.HEARTBEAT), 700.0)
        exact((w.watch(now=1000.0), w.watch(now=1100.0)), (stale, stale))
        with open(os.path.join(missing, w.HEARTBEAT), "w") as handle:
            handle.write("garbage")
        exact(w.watch(now=1000.0), stale)
        lock.close()
        exact(w.watch(now=1000.0), None)

    beatdir = tempfile.mkdtemp(prefix="selftest-liveness-beat-")
    with patch.dict(os.environ, {"COORD_INBOX_DIR": beatdir}):
        failures = []

        def hammer():
            for n in range(150):
                try:
                    w.heartbeat(now=float(n))
                except Exception as exc:
                    failures.append(exc)

        threads = [threading.Thread(target=hammer) for _ in range(2)]
        began = time.monotonic()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        exact((failures, [n for n in os.listdir(beatdir) if n.endswith(".tmp")], time.monotonic() - began < 1), ([], [], True))
        calls = []

        def flaky(*, now):
            calls.append(now)
            if len(calls) == 1:
                raise OSError("disk")

        stop = threading.Event()
        ticks = iter(range(10))
        with patch.object(w, "heartbeat", flaky), contextlib.redirect_stderr(io.StringIO()):
            thread = threading.Thread(target=w._beat, args=(stop, 0.02, lambda: next(ticks)), daemon=True)
            thread.start()
            time.sleep(0.2)
            stop.set()
            thread.join(1)
        exact(len(calls) > 1, True)

    seen_alarm = []
    old = signal.signal(signal.SIGALRM, lambda signum, frame: seen_alarm.append(signum))
    try:
        w._on_alarm(signal.SIGALRM, None)
        signal.raise_signal(signal.SIGALRM)
        exact(seen_alarm, [signal.SIGALRM])
    finally:
        signal.signal(signal.SIGALRM, old)

    import lane_driver as lane
    unreadable = os.path.join(tempfile.mkdtemp(prefix="selftest-liveness-"), w.LOCK)
    real_open = open

    def denied(path, *args, **kwargs):
        if str(path) == unreadable:
            raise PermissionError(13, "denied")
        return real_open(path, *args, **kwargs)

    with patch.dict(os.environ, {"COORD_INBOX_DIR": os.path.dirname(unreadable)}), patch("builtins.open", denied):
        exact(lane.inbox_liveness(), "inbox liveness check failed (PermissionError)")

    def seed():
        store.enqueue("round_cap", "round_cap:o/r#1:x", source="journal", ts=0.0, repo="o/r", pr=1)

    def state():
        return [tuple(r) for r in store.connect().execute("SELECT status, attempts FROM inbox")]

    with patch.dict(os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-liveness-"),
                                 "COORD_JOURNAL_DIR": tempfile.mkdtemp(prefix="selftest-liveness-j-")}):
        seed()
        before = (signal.getsignal(signal.SIGALRM), signal.getitimer(signal.ITIMER_REAL))
        exact(w.shadow_pass(now=100.0, runner=lambda lines: time.sleep(1.5), alarm_seconds=0.3, beat_seconds=0.05, clock=lambda: 555.0), {"batches": 0, "lines": 0})
        exact((signal.getsignal(signal.SIGALRM), signal.getitimer(signal.ITIMER_REAL)), before)
        probe_lock = open(os.path.join(os.environ["COORD_INBOX_DIR"], w.LOCK), "w")
        fcntl.flock(probe_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        probe_lock.close()
        exact(state(), [("pending", 1)])
        exact(w._stamp(w.PASS_END), 555.0)

    with patch.dict(os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-liveness-"),
                                 "COORD_JOURNAL_DIR": tempfile.mkdtemp(prefix="selftest-liveness-j-")}):
        seed()
        seen = []

        def runner(lines):
            time.sleep(0.3)
            seen.append(w._stamp(w.HEARTBEAT))
            return "NOTHING: x"

        probing = open(os.path.join(os.environ["COORD_INBOX_DIR"], w.LOCK), "w")
        fcntl.flock(probing, fcntl.LOCK_SH | fcntl.LOCK_NB)
        threading.Timer(0.1, probing.close).start()
        exact(w.shadow_pass(now=100.0, runner=runner, retry_delay=0.4, beat_seconds=0.05, clock=lambda: 555.0)["batches"], 1)
        exact(seen, [555.0])

    with patch.dict(os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-liveness-"),
                                 "COORD_JOURNAL_DIR": tempfile.mkdtemp(prefix="selftest-liveness-j-")}):
        seed()

        def interrupted(conn, rows, now):
            raise w.PassTimeout()

        with patch.object(store, "_ack", interrupted):
            exact(w.shadow_pass(now=100.0, runner=lambda lines: "NOTHING: x")["batches"], 0)
        exact((state(), store.connect().execute("SELECT COUNT(*) FROM outbox").fetchone()[0]), ([("pending", 1)], 0))


def inbox():
    import functools
    import inbox as store
    import sqlite3

    with patch.dict(os.environ, {"COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-inbox-")}):
        dead, base = 4194303, dict(source="journal", ts=1.0)
        key = "pr_merged:a#1:"
        exact((store.enqueue("pr_merged", key, **base), store.enqueue("pr_merged", key, **base)), (True, False))
        conn = store.connect()
        exact(conn.execute("SELECT tier FROM inbox").fetchone()[0], "batch")
        exact(conn.execute("PRAGMA user_version").fetchone()[0], 1)
        store.enqueue("alarm", "alarm:x:1", payload={"n": 1}, **base)
        exact(conn.execute("SELECT tier FROM inbox WHERE kind='alarm'").fetchone()[0], "wake")
        try:
            store.enqueue("bogus", "bogus:1", **base)
        except ValueError:
            pass
        else:
            raise AssertionError("an unknown kind was stored")
        exact(conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0], 2)
        for number in range(8):
            store.enqueue("pr_opened", f"pr_opened:a#{number}", **base)
        exact(store.counts()["pending"], 10)
        script = ("import json,sys;sys.path.insert(0,sys.argv[1]);import inbox;"
                  "open(sys.argv[3],'w').write(json.dumps([r['id'] for r in inbox.claim('coordinator',worker=sys.argv[2],now=50.0,limit=6)]))")
        outputs = [os.path.join(os.environ["COORD_INBOX_DIR"], name + ".json") for name in ("w1", "w2")]
        children = [os.spawnv(os.P_NOWAIT, sys.executable, [sys.executable, "-c", script, str(ROOT.parent / "bin"), f"w{n + 1}", outputs[n]])
                    for n in range(2)]
        for child in children:
            exact(os.waitpid(child, 0)[1], 0)
        picked = [row_id for out in outputs for row_id in json.load(open(out))]
        exact((len(picked), len(set(picked))), (10, 10))
        exact(store.reap(now=100.0), 0)
        exact(store.reap(now=1000.0), 10)
        first = store.claim("coordinator", worker="w1", now=1100.0, lease=10, limit=1, pid=dead)
        exact((len(first), first[0]["attempts"]), (1, 2))
        exact(store.reap(now=1105.0), 0)
        exact(store.reap(now=1111.0), 1)
        store.claim("coordinator", worker="w1", now=1200.0, lease=10, limit=1, pid=dead)
        exact(store.reap(now=1220.0), 1)
        exact(store.counts()["failed"], 1)
        conn.execute("DELETE FROM inbox")
        store.enqueue("recut", "recut:1", **base)
        stale = store.claim("coordinator", worker="a", now=0.0, lease=10, pid=dead)
        exact(store.reap(now=20.0), 1)
        live = store.claim("coordinator", worker="b", now=30.0, lease=10, pid=os.getpid())
        exact((store.ack(stale, now=31.0), store.release(stale, count_attempt=True)), (0, 0))
        exact(conn.execute("SELECT status, claimed_by FROM inbox").fetchone()[:], ("claimed", "b"))
        exact(store.reap(now=1000.0), 0)
        exact(store.release(live, count_attempt=False), 1)
        exact(conn.execute("SELECT attempts FROM inbox").fetchone()[0], 1)
        again = store.claim("coordinator", worker="c", now=2000.0, lease=10, pid=os.getpid())
        exact((store.ack(live, now=2001.0), store.release(live, count_attempt=False)), (0, 0))
        exact(conn.execute("SELECT status, claimed_by FROM inbox").fetchone()[:], ("claimed", "c"))
        exact(store.ack(again, now=2002.0), 1)
        with patch.object(os, "kill", side_effect=PermissionError):
            store.enqueue("recut", "recut:2", **base)
            store.claim("coordinator", worker="d", now=3000.0, lease=10, pid=1)
            exact(store.reap(now=3020.0), 0)
        exact(store.reap(now=3000.0 + 3611.0), 1)
        future = tempfile.mkdtemp(prefix="selftest-inbox-v2-")
        raw = sqlite3.connect(os.path.join(future, "inbox.db"))
        raw.execute("PRAGMA user_version=2")
        raw.close()
        with patch.dict(os.environ, {"COORD_INBOX_DIR": future}):
            try:
                store.connect()
            except RuntimeError:
                pass
            else:
                raise AssertionError("a newer schema was opened")
            raw = sqlite3.connect(os.path.join(future, "inbox.db"))
            exact(raw.execute("PRAGMA user_version").fetchone()[0], 2)
            raw.close()
        holder = sqlite3.connect(os.path.join(os.environ["COORD_INBOX_DIR"], "inbox.db"), isolation_level=None)
        holder.execute("BEGIN IMMEDIATE")
        quick = functools.partial(sqlite3.connect, timeout=0.1)
        with patch.object(store.sqlite3, "connect", quick):
            try:
                store.enqueue("recut", "recut:locked", **base)
            except sqlite3.OperationalError as error:
                exact("locked" in str(error), True)
            else:
                raise AssertionError("a locked begin did not raise")
        holder.close()
        import journal
        clean = tempfile.mkdtemp(prefix="selftest-hook-off-")
        env = {"COORD_JOURNAL_DIR": clean, "COORD_INBOX_DIR": clean}
        with patch.dict(os.environ, env), patch.dict(sys.modules):
            os.environ.pop("COORD_INBOX_HOOK", None)
            sys.modules.pop("inbox")
            journal.emit("gate_verdict", "lane", repo="o/r", pr=7, head="a" * 40)
            exact(("inbox" in sys.modules, sorted(os.listdir(clean))[0].startswith("events-"), len(os.listdir(clean))), (False, True, 1))

        def run_hook(inbox_dir, emits, wait=None):
            journal_dir = tempfile.mkdtemp(prefix="selftest-hook-journal-")
            env = {"COORD_JOURNAL_DIR": journal_dir, "COORD_INBOX_DIR": inbox_dir, "COORD_INBOX_HOOK": "on"}
            err = io.StringIO()
            with patch.dict(os.environ, env), patch.object(journal, "INBOX_WAIT", wait or journal.INBOX_WAIT), contextlib.redirect_stderr(err):
                for args in emits:
                    journal.emit(*args[:2], **args[2])
            lines = sum(len(open(os.path.join(journal_dir, f)).readlines()) for f in os.listdir(journal_dir))
            return lines, err.getvalue()

        pr = dict(repo="o/r", pr=7, head="a" * 40)
        fresh = tempfile.mkdtemp(prefix="selftest-hook-inbox-")
        emits = [("gate_verdict", "lane", pr), ("gate_verdict", "lane", pr), ("alarm_raised", "alarms", dict(alarm="x-1")),
                 ("alarm_withdrawn", "alarms", dict(alarm="x-1")), ("alarm_raised", "alarms", dict(alarm="x-1")),
                 ("alarm_raised", "alarms", dict(alarm="x-1")), ("gate_started", "lane", pr)]
        exact(run_hook(fresh, emits), (7, ""))
        with patch.dict(os.environ, {"COORD_INBOX_DIR": fresh}):
            rows = [r[0] for r in store.connect().execute("SELECT dedupe_key FROM inbox ORDER BY id")]
        exact(rows, ["gate_verdict:o/r#7:" + "a" * 40, "alarm:x-1:0", "alarm:x-1:1"])
        blocked = tempfile.mkdtemp(prefix="selftest-hook-blocked-")
        open(os.path.join(blocked, "file"), "w").close()
        lines, err = run_hook(os.path.join(blocked, "file", "sub"), emits[:1])
        exact((lines, err.count("\n"), "not queued" in err), (1, 1, True))
        held = tempfile.mkdtemp(prefix="selftest-hook-held-")
        with patch.dict(os.environ, {"COORD_INBOX_DIR": held}):
            store.counts()
        lock = sqlite3.connect(os.path.join(held, "inbox.db"), isolation_level=None)
        lock.execute("BEGIN IMMEDIATE")
        began = time.monotonic()
        lines, err = run_hook(held, emits[:1], wait=0.3)
        lock.close()
        exact((lines, err.count("\n"), time.monotonic() - began < 2), (1, 1, True))
    replay_cases()
    disagreement_cases()
    outbox_cases()
    timer_cases()
    inbox_poll_cases()
    worker_cases()
    liveness_cases()
    main_cases()


def main_cases():
    import plistlib
    import inbox_poll
    import inbox_worker as w

    inbox_dir = tempfile.mkdtemp(prefix="selftest-main-")
    env = {"COORD_JOURNAL_DIR": tempfile.mkdtemp(prefix="selftest-main-journal-"),
           "COORD_INBOX_DIR": inbox_dir, "COORD_INBOX_SHADOW": "1"}
    with patch.dict(os.environ, env):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            exact((w.main([]), out.getvalue()), (0, ""))
        exact(os.path.exists(os.path.join(inbox_dir, "inbox.db")), True)
        with patch.object(w, "shadow_pass", return_value={"batches": 1, "lines": 3}), contextlib.redirect_stdout(io.StringIO()) as out:
            exact((w.main([]), out.getvalue()), (0, "inbox shadow pass: batches=1 lines=3\n"))
        with patch.object(w, "shadow_pass", side_effect=RuntimeError("secret payload")), contextlib.redirect_stderr(io.StringIO()) as err:
            exact((w.main([]), err.getvalue()), (1, "inbox shadow pass failed: RuntimeError\n"))
    with patch.dict(os.environ, {**env, "COORD_INBOX_POLL_EVERY": "300", "COORD_INBOX_REPOS": "o/r"}):
        exact((w.poll_due(now=1000.0), w.poll_due(now=1100.0), w.poll_due(now=1300.0)), (True, False, True))
        calls = []

        def failing(repo):
            calls.append(repo)
            raise RuntimeError("gh")

        def exhausted(repo):
            calls.append(repo)
            raise inbox_poll.gh_gateway.ApiBudgetExhausted("floor")

        with patch.object(inbox_poll, "fetch", failing), patch.object(inbox_poll, "fetch_status", failing), contextlib.redirect_stderr(io.StringIO()):
            exact((w.shadow_pass(now=2000.0)["batches"], w.shadow_pass(now=2100.0)["batches"], calls), (0, 0, ["o/r", "o/r"]))
        calls.clear()
        with patch.object(inbox_poll, "fetch", exhausted), contextlib.redirect_stderr(io.StringIO()) as err:
            exact((w.shadow_pass(now=3000.0)["batches"], calls, err.getvalue().count("\n")), (0, ["o/r"], 1))
    off = os.path.join(tempfile.mkdtemp(prefix="selftest-main-off-"), "x")
    with patch.dict(os.environ, {**env, "COORD_INBOX_DIR": off, "COORD_INBOX_SHADOW": "0"}), contextlib.redirect_stderr(io.StringIO()):
        exact((w.main([]), os.path.exists(off)), (2, False))
    plist = ROOT.parent / "launchd/dev.coordinator.inbox.plist"
    if plist.is_file():
        job = plistlib.loads(plist.read_bytes())
        settings = job["EnvironmentVariables"]
        exact((sorted(settings), settings["COORD_INBOX_SHADOW"], settings["COORD_INBOX_POLL_EVERY"], "KeepAlive" in job),
              (["COORD_INBOX_POLL_EVERY", "COORD_INBOX_REPOS", "COORD_INBOX_SHADOW", "HOME", "PATH"], "1", "300", False))
        with patch.dict(os.environ, {"COORD_INBOX_REPOS": settings["COORD_INBOX_REPOS"]}):
            exact(inbox_poll.configured_repos(), ["shyamsivakumar/mac-ops", "shyamsivakumar/strategy-replay-workbench"])
        exact((job["StartInterval"], job["RunAtLoad"], job["ProgramArguments"][1].endswith("/.local/bin/inbox_worker.py")), (60, True, True))


def worker_cases():
    import fcntl
    import glob
    import inbox as store
    import inbox_outbox as out
    import inbox_worker as w

    def seed(wake=1, **extra):
        for n in range(1, 6):
            for head in "ab":
                store.enqueue("pr_new_head", f"pr_new_head:o/r#{n}:{head}", source="journal", ts=0.0, repo="o/r", pr=n)
        for n in range(1, wake + 1):
            store.enqueue("round_cap", f"round_cap:o/r#{n}:x", source="journal", ts=0.0, repo="o/r", pr=n, **extra)

    def rows():
        return [tuple(r) for r in store.connect().execute("SELECT status, attempts FROM inbox ORDER BY id")]

    def outbox():
        return [tuple(r) for r in store.connect().execute("SELECT kind, target, body, reason FROM outbox ORDER BY id")]

    journal_dir = tempfile.mkdtemp(prefix="selftest-worker-journal-")
    with patch.dict(os.environ, {"COORD_JOURNAL_DIR": journal_dir, "COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-worker-")}):
        seed(2)
        exact(w.shadow_pass(now=100.0), {"batches": 1, "lines": 7})
        exact((set(rows()), outbox()), ({("done", 1)}, [("none", None, "", "shadow")]))
        exact(w.shadow_pass(now=101.0)["batches"], 0)
        exact("inbox_would_wake" in "".join(open(f).read() for f in glob.glob(journal_dir + "/events-*.jsonl")), True)

    with patch.dict(os.environ, {"COORD_JOURNAL_DIR": journal_dir, "COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-worker-")}):
        seed(1)
        exact(w.shadow_pass(now=100.0, runner=lambda lines: "no decision here")["batches"], 0)
        exact((set(rows()), outbox()), ({("pending", 1)}, []))
        exact(w.shadow_pass(now=200.0)["batches"], 0)

        def unavailable(lines):
            raise w.ModelUnavailable

        def broken(lines):
            raise RuntimeError("runner")

        w.shadow_pass(now=2000.0, runner=unavailable)
        exact(set(rows()), {("pending", 1)})
        w.shadow_pass(now=4000.0, runner=broken)
        exact((set(rows()), outbox()), ({("pending", 2)}, []))

    with patch.dict(os.environ, {"COORD_JOURNAL_DIR": journal_dir, "COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-worker-")}):
        seed(1)
        first = store.claim("coordinator", worker="a", now=0.0)
        store.release(first, count_attempt=True)
        store.claim("coordinator", worker="b", now=1.0)
        exact((w.finish(first, "NOTHING: late", now=2.0), outbox()), (0, []))

    with patch.dict(os.environ, {"COORD_JOURNAL_DIR": journal_dir, "COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-worker-")}):
        seed(1)
        store.enqueue("round_cap", "other", source="journal", ts=0.0, session="other")
        with open(os.path.join(os.environ["COORD_INBOX_DIR"], "inbox.worker.lock"), "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            exact(w.shadow_pass(now=100.0)["batches"], 0)
        exact(set(r[0] for r in rows()), {"pending"})
        with patch("inbox_poll.fetch", side_effect=AssertionError("polled")):
            exact(w.shadow_pass(now=100.0)["batches"], 1)
        exact([r[0] for r in store.connect().execute("SELECT status FROM inbox WHERE session='other'")], ["pending"])

    with patch.dict(os.environ, {"COORD_JOURNAL_DIR": journal_dir, "COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-worker-")}):
        seed(0)
        for n, payload in enumerate(({"t": "\ud800"}, {"t": "x" * 2_000_000}, [1, 2], "str")):
            store.enqueue("alarm", f"alarm:{n}:0", source="journal", ts=0.0, payload=payload)
        store.connect().execute("INSERT INTO inbox (ts, source, kind, dedupe_key, session, payload, tier) VALUES (0, 'j', 'alarm', 'corrupt', 'coordinator', '{not json', 'wake')")
        reply = "SEND t56;rm: \ud800 $(id)\nNOTHING: r"
        exact(w.shadow_pass(now=100.0, runner=lambda lines: reply)["batches"], 1)
        exact([r[:2] for r in outbox()], [("hc_send", "t56;rm"), ("none", None)])
        exact(out.drain(None, now=100.0, shadow=True), {"would_send": 1})

    with patch.dict(os.environ, {"COORD_JOURNAL_DIR": journal_dir, "COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-worker-")}):
        seed(1)
        for n, bad in enumerate(("SEND t56 text\nNOTHING: ok", "NOTHING:\nNOTHING: ok", None, b"NOTHING: x", {"a": 1})):
            exact(w.shadow_pass(now=100.0 + 10000 * n, runner=lambda lines, bad=bad: bad)["batches"], 0)
            exact((set(rows()), outbox()), ({("pending", 1)}, []))
            store.connect().execute("UPDATE inbox SET attempts=0")
        claimed = store.claim("coordinator", worker="y", now=0.0)
        real, calls = out._insert, []

        def second_fails(*args):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("second insert")
            return real(*args)

        with patch.object(out, "_insert", second_fails):
            try:
                w.finish(claimed, "NOTHING: a\nNOTHING: b", now=5.0)
            except RuntimeError:
                pass
            else:
                raise AssertionError("second insert error swallowed")
        exact((set(r[0] for r in rows()), outbox()), ({"claimed"}, []))
        errors = []

        def other():
            try:
                with store.txn(time.monotonic() + 0.3):
                    pass
            except Exception as exc:
                errors.append(type(exc).__name__)

        with store.txn():
            thread = threading.Thread(target=other)
            thread.start()
            thread.join()
        exact(len(errors), 1)

    with patch.dict(os.environ, {"COORD_JOURNAL_DIR": journal_dir, "COORD_INBOX_DIR": tempfile.mkdtemp(prefix="selftest-worker-"),
                                 "COORD_INBOX_DEBOUNCE": "soon", "COORD_INBOX_MIN_GAP": "nan"}):
        seed(1)
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            exact(w.shadow_pass(now=100.0)["batches"], 1)
        exact(("COORD_INBOX_DEBOUNCE='soon'" in buffer.getvalue(), "COORD_INBOX_MIN_GAP='nan'" in buffer.getvalue()), (True, True))


def held_merge():
    coordq = load_coordq()
    held, other, keys = "a" * 40, "b" * 40, {"R": "o/r", "RX": "o/rx"}

    def hold(pr, head, reason="loop code hold", repo="o/r"):
        return {"event": "merge_held", "repo": repo, "pr": pr, "head": head, "data": {"reason": reason}}

    rows = [hold(7, held), hold(9, held, "manual repo"), hold(5, other, "prompt hold"), hold(5, held)]
    ask = lambda key="", title="", rows=rows: coordq.held_merge(key, title, rows, keys)
    exact(bool(ask(f"merge:o/r#7:{held}")), True)
    exact(bool(ask(f"MERGE:O/R#7:{held.upper()}")), True)
    exact(bool(ask(title="R-7 merge " + held[:8])), True)
    exact(bool(ask(title="r-7 MERGE " + held[:4].upper())), True)
    exact(bool(ask(title="R-7 merge " + other[:8])), True)
    exact(bool(ask(title="R-5 merge " + other[:8])), True)
    exact(bool(ask(f"merge:o/r#5:{other}")), True)
    newer = "c" * 40
    exact(bool(ask(f"merge:o/r#7:{newer}", "R-7 merge " + newer[:8])), True)
    exact(bool(ask(f"merge:o/r#8:{newer}", "R-7 merge " + held[:8])), True)
    exact(bool(ask(f"merge:o/r#7:{newer}", "R-8 merge " + newer[:8])), False)
    exact(bool(ask(title="R#7 merge on PASS " + held[:8])), True)
    exact(bool(ask(title="R#8 merge on PASS " + held[:8])), False)
    exact(bool(ask(title="R-7 merge on PASS " + held[:8])), True)
    exact(bool(ask(f"merge:o/r#5:{'c' * 40}")), False)
    exact(bool(ask(title="R-5 merge " + "c" * 8)), True)
    exact(bool(ask(f"merge:o/r#8:{held}")), False)
    exact(bool(ask(f"merge:o/rx#7:{held}")), False)
    exact(bool(ask(title="RX-7 merge " + held[:8])), False)
    exact(bool(ask(title="R-9 merge " + held[:8])), False)
    exact(bool(ask(title="R-7 continue")), False)
    exact(bool(ask(title="R-7 merge abc")), False)
    exact(bool(ask(title="ZZ-7 merge " + held[:8])), False)
    exact(bool(ask(f"fix:o/r#7:{held}", "o/r#7 gate findings")), False)
    exact(bool(ask(f"merge:o/r#7:{held}", rows=[hold(7, None), {"event": "merge_held", "repo": "o/r", "pr": 7}])), False)
    exact(bool(ask(f"merge:o/r#7:{held}", rows=[hold(7, held), hold(7, other, "manual repo")])), True)
    exact(bool(ask(title="R-7 merge " + "c" * 8, rows=[hold(7, held), hold(7, other, "manual repo")])), False)

    gate = lambda thread, receipts, rows=rows: coordq.held_gate_thread(thread, receipts, rows)
    exact(bool(gate("t1", {f"gate:o/r#7:{held}": "t1"})), True)
    exact(bool(gate("t1", {f"GATE:O/R#7:{held.upper()}:astra2": "t1"})), True)
    exact(bool(gate("t1", {f"gate:o/r#7:{held}:gate:main:lane": "t1"})), True)
    exact(bool(gate("t1", {f"gate:o/r#7:{other}": "t1", f"gate:o/r#7:{held}:swap": "t1"})), True)
    exact(bool(gate("t1", {f"gate:o/r#7:{other}": "t1"})), False)
    exact(bool(gate("t2", {f"gate:o/r#7:{held}": "t1"})), False)
    exact(bool(gate("t1", {f"gate:o/r#9:{held}": "t1"})), False)
    exact(bool(gate("t1", {f"gate:o/r#5:{held}": "t1"})), True)
    exact(bool(gate("t1", {"base:t1": "main", "brief:t1": "lane-merges", f"merge-pass:o/r#7:{held}": "t1"})), False)
    exact(bool(gate("t1", {f"gate:o/r#7:{held}": "t1"}, rows=[hold(7, held, "manual repo")])), False)
    for bad in (None, 7, "", ["t1"]):
        exact(gate(bad, {f"gate:o/r#7:{held}": "t1"}), None)
    for bad in (None, [], "x", {f"gate:o/r#7:{held}": ["t1"], 5: "t1", f"gate:o/r#7:{held[:9]}": "t1"}):
        exact(gate("t1", bad), None)
    exact(coordq.held_gate_thread("t1", {f"gate:o/r#7:{held}": "t1"}, [None, "x", {"event": "merge_held"}, hold(7, held)]) is not None, True)
    command = lambda text, rows=rows: coordq.held_command(text, rows)
    for text in ("gh pr merge 7 -R o/r", "gh pr merge -R o/r 7 --squash", "gh pr merge 7 --repo=o/r", "gh pr merge 7 --repo o/R",
                 "gh pr merge https://github.com/o/r/pull/7 --squash", "run `gh pr merge 7 -R o/r --squash`.",
                 "first\n```\ngh pr merge -R o/r --squash 7\n```", f"gh pr merge 7 -R o/r --match-head-commit {held}",
                 "x && gh pr merge 007 -R o/r", "gh pr merge '#7' -R 'o/r'"):
        exact(bool(command(text)), True)
    for text in ("gh pr view 7 -R o/r", "gh pr merge 7", "gh pr merge 8 -R o/r", "gh pr merge 7 -R o/rx", "gh pr merge --squash -R o/r",
                 f"gh pr merge 7 -R o/r --match-head-commit {other}", "gh pr merge 9 -R o/r", "merge 7 -R o/r",
                 "gh pr merge https://github.com/o/r/pull/8", None, 7, ["gh pr merge 7 -R o/r"]):
        exact(bool(command(text)), False)
    exact(bool(command("gh pr merge 5 -R o/r", rows=[hold(5, other, "prompt hold")])), True)
    exact(bool(command("gh pr merge 5 -R o/r", rows=[hold(5, other, "prompt hold"), hold(5, held, "manual repo")])), False)
    exact(bool(command("gh pr merge 7 -R o/r", rows=[None, "x", {"event": "merge_held", "repo": "o/r", "pr": 7, "head": held}])), False)
    gate_policy = importlib.import_module("gate_policy")
    sentence = gate_policy.NO_LATER_MERGE
    exact("gh pr merge" in sentence, False)
    brief = lambda repo, **kw: gate_policy.build_gate_brief({"key": "MO"}, repo, 7, 8, held, False, **kw)
    for text in (brief("shyamsivakumar/mac-ops"), brief("shyamsivakumar/mac-ops", prompt=True),
                 brief("shyamsivakumar/mac-ops", ascend_override=False, prompt=True)):
        exact(sentence in text and "gh pr merge" not in text, True)
    exact(sentence in gate_policy.manual_gate_ending(), True)
    exact(sentence in brief("shyamsivakumar/mac-ops", ascend_override=True), False)

    scratch = tempfile.mkdtemp(prefix="selftest-held-merge-")
    with patch.dict(os.environ, {"COORD_JOURNAL_DIR": scratch}):
        now = time.time()
        last_month = now - time.gmtime(now).tm_mday * 86400
        lines = ["not json", "[1]", json.dumps(hold(7, held)), '{"event":"merge_held","data":[1]}']
        with open(coordq.journal.journal_path(last_month), "w") as handle:
            handle.write("\n".join(lines) + "\n")
        exact([r["pr"] for r in coordq.journal_rows()], [7])
        queue_dir = tempfile.mkdtemp(prefix="selftest-held-queue-")
        args = lambda title, key="": argparse.Namespace(
            args=json.dumps({"threadId": "gate", "message": "merge"}), title=title, priority=900,
            tool="t3_thread_send", action_key=key)
        with patch.object(coordq, "DIR", queue_dir), patch.object(coordq, "ticket_keys", lambda: keys), \
             patch.object(coordq, "journal_rows", lambda: rows), patch.object(coordq, "drain", side_effect=AssertionError("drain")), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            for title, key in [("R-7 merge " + held[:8], ""), ("", f"merge:o/r#7:{held}")]:
                try:
                    coordq.cmd_start(args(title, key))
                except SystemExit:
                    pass
                else:
                    raise AssertionError("a held merge was queued")
        exact(err.getvalue().count("o/r#7 is held for Shyam (loop code hold)"), 2)
        exact(os.listdir(queue_dir), [])
        refused = [json.loads(line) for line in open(coordq.journal.journal_path(now)) if '"refused"' in line]
        exact(len(refused), 2)
        receipts = {f"gate:o/r#7:{held}:astra2": "gate", f"gate:o/r#7:{other}": "other"}
        send = lambda thread, message: argparse.Namespace(
            args=json.dumps({"threadId": thread, "message": message}), title="", priority=900,
            tool="t3_thread_send", action_key="")
        with patch.object(coordq, "DIR", queue_dir), patch.object(coordq, "journal_rows", lambda: rows), \
             patch.object(coordq, "load_receipts", lambda: receipts), patch.object(coordq, "drain", side_effect=AssertionError("drain")), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            for thread, message in [("gate", "Finish this gate and run the merge approval step"), ("gate", None), ("other", "gh pr merge 7 -R o/r"),
                                    ("builder", "gh pr merge 7 -R o/r --squash")]:
                try:
                    coordq.cmd_start(send(thread, message))
                except SystemExit:
                    pass
                else:
                    raise AssertionError("a held send was queued")
        exact(err.getvalue().count("o/r#7 is held for Shyam (loop code hold)"), 4)
        exact(os.listdir(queue_dir), [])


EVALS = {"send-integrity": send_integrity, "root-workspace": root_workspace, "worktree-base-ref": worktree_base_ref, "consolidation-guard": consolidation_guard, "script-results": script_results,"start-routing": start_routing, "dead-run-recovery": dead_run_recovery, "gate-pipeline": gate_pipeline, "merged-restart": merged_restart, "merge-pass": merge_pass, "gate-round-cap": gate_round_cap, "decisions-board-guard": decisions_board_guard, "no-parking": no_parking, "turncap": turncap, "watchdog": watchdog, "zero-merge": zero_merge, "board-integrity": board_integrity, "api-budget": api_budget, "ff-drift": ff_drift, "cycle-health": cycle_health, "stall": stall, "alarm-mute": alarm_mute, "router-build": router_build, "router-blocked": router_blocked, "key-mint": key_mint, "credit-block": credit_block, "provider-until": provider_until, "refill-busy": refill_busy, "stale-started-refill": stale_started_refill, "close-evidence": close_evidence, "build-here": build_here, "journal-migration": journal_migration, "builder-receipt": builder_receipt, "closed-ticket-merge": closed_ticket_merge, "inbox": inbox, "held-merge": held_merge, "stop-rules": stop_rules}


def main():
    os.environ["COORD_JOURNAL_DIR"] = tempfile.mkdtemp(prefix="selftest-journal-")
    failed = False
    try:
        exact(["unexpected"], ["expected"])
    except AssertionError:
        pass
    else:
        print("FAIL negative-control: equality accepted wrong actions")
        return 1
    with patch.object(subprocess, "run", side_effect=AssertionError("live subprocess forbidden")), \
         patch.object(subprocess, "Popen", side_effect=AssertionError("live process forbidden")), \
         fixture_models():
        for name, evaluate in EVALS.items():
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    evaluate()
                    if name == "merge-pass":
                        import lane_driver
                        with patch.object(lane_driver, "merge_pass"):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted a pass that merges nothing")
                    if name == "send-integrity":
                        import lane_driver
                        with patch.object(lane_driver, "send", return_value="started"):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted unchecked send")
                    if name == "root-workspace":
                        import lane_driver
                        with patch.object(lane_driver, "root_workspace", return_value=False):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted pull request work in the shared root")
                    if name == "consolidation-guard":
                        import lane_driver
                        with patch.object(lane_driver, "park", return_value="unguarded"):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted missing re-cut dispatch")
                    if name == "script-results":
                        import script_results as results
                        with patch.object(results, "reconcile", return_value=[]):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted missing deadline routing")
                    if name == "ff-drift":
                        import lane_driver
                        with patch.object(lane_driver, "drift_ff"):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted missing fast-forward chore")
                    if name == "api-budget":
                        import lane_driver
                        with patch.object(lane_driver, "BOARD_REFRESH_PASSES", 1):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted excessive board reads")
                    if name == "board-integrity":
                        import board_integrity as audit
                        with patch.object(audit, "defects", return_value=[]):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted missing board defects")
                    if name == "stall":
                        import stall as rule
                        with patch.object(rule, "observe", return_value=None):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted a missing stall")
                    if name == "zero-merge":
                        import lane_driver
                        with patch.object(lane_driver, "zero_merge"):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted missing zero-merge action")
                    if name == "watchdog":
                        import lane_driver
                        with patch.object(lane_driver, "watchdog"):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted missing watchdog action")
                    if name == "turncap":
                        try:
                            turncap(early_interrupt=True)
                        except AssertionError:
                            pass
                        else:
                            raise AssertionError("negative control accepted extra interrupt")
                    if name == "no-parking":
                        import lane_driver
                        for status in ("completed", "failed"):
                            no_parking(status)
                        with patch.object(lane_driver, "send", return_value="dropped"):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted a dropped fix send")
                    if name == "start-routing":
                        import lane_driver
                        with patch.object(lane_driver, "NEVER_START", set()):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control failed to detect forbidden start")
            except Exception as exc:
                failed = True
                print(f"FAIL {name}: {exc}")
            else:
                print(f"PASS {name}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
