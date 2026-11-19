import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
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
    for kind, label, expected in [("standard", None, "morph/morph-dsv41flash"), ("risky", None, "morph/morph-kimik31"),
                                  ("chore", "kimi", "morph/morph-kimik31"), ("chore", None, "morph/morph-dsv41flash")]:
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
                                       print_brief=False, dry_run=False))
        exact(len(commands), 1)
    morph = {"pi:morph-dsv41flash", "pi:morph-kimik31"}
    for kind, walk in [("standard", ["cursor", "terra"]), ("risky", ["cursor", "sol"])]:
        blocked = set(morph)
        for expected_id in walk:
            exact(lane.model_list.first_available("build", None, blocked, kind)["id"], expected_id)
            blocked.add(lane.model_list.identity(lane.model_list.first_available("build", None, blocked, kind)["selection"]))
    exact(lane.model_list.first_available("fix")["selection"]["model"], "morph/morph-dsv41flash")
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
    # The reviewer chain is one list now (#552): the first entry is the gate's
    # reviewer, the last is the fallback when its quota is exhausted.
    full = f"PROVIDES: PASS {head}\nCHECK: PASS {head}\nVERDICT: PASS"
    chain = [entry["selection"]["instanceId"] for entry in lane.model_list.entries("review")]
    cases = [
        ("checked-head", repo, "absent", "", {}, [chain[0]], None),
        ("pass", repo, "PASS", full, {}, ["merge", "provides", "ff"], "coordinator/bin/ticket"),
        ("prompt-pass", repo, "PASS", f"CHECK: PASS {head}\nVERDICT: PASS", {}, ["decisions"],
         "coordinator/config/AGENT-RULES.md"),
        ("fail", repo, "FAIL", "finding\nVERDICT: FAIL", {}, ["builder"], "coordinator/bin/ticket"),
        ("no-verdict", repo, "none", "interrupted", {}, [chain[0]], None),
        ("second-no-verdict", repo, "none", "interrupted",
         {f"gate:{repo}#20:{head}": "first", f"regate:{repo}#20:{head}:main": "retry"}, [], None),
        ("quota", repo, "none", "Astra quota exhausted",
         {f"gate:{repo}#20:{head}": "first", f"regate:{repo}#20:{head}:main": "retry"},
         [chain[chain.index(chain[0]) + 1]], None),
        ("manual", "digitized/Concerning", "PASS", full, {}, [], None),
        ("ascend", "ascend/fixture", "absent", "", {}, [], None),
        ("stray-pass-ignored", repo, "absent", "", {}, [chain[0]], None),
        ("earlier-fail-later-pass", repo, "PASS", full, {}, ["decisions"], None),
        ("retry-replaced-pass", repo, "PASS", full, {}, ["merge", "provides", "ff"], None),
        ("merge-timeout-but-merged", repo, "PASS", full, {}, ["merge", "provides", "ff"], None),
        ("older-running-newer-pass", repo, "PASS", full, {}, [], None),
        ("older-pass-newer-pass", repo, "PASS", full, {}, ["merge", "provides", "ff"], None),
        ("pass-without-provides", repo, "none", f"CHECK: PASS {head}\nVERDICT: PASS", {}, [chain[0]], None),
        ("pass-check-wrong-head", repo, "none", f"PROVIDES: PASS {head}\nCHECK: PASS {'b' * 40}\nVERDICT: PASS", {}, [chain[0]], None),
        ("no-receipts-file", repo, "absent", "", {}, [chain[0]], None),
        ("retargeted-after-pass", repo, "PASS", full, {}, [chain[0]], None),
        ("trailing-space-pass", repo, "PASS", full.replace(f"PROVIDES: PASS {head}", f"PROVIDES: PASS {head}  "), {}, ["merge", "provides", "ff"], None),
        ("indented-verdict", repo, "none", full.replace("\nVERDICT", "\n  VERDICT"), {}, [chain[0]], None),
        ("older-pass-not-superseded", repo, "PASS", full, {}, ["merge", "provides", "ff"], None),
        ("older-fail-superseded", repo, "FAIL", "finding\nVERDICT: FAIL", {}, [], None),
    ]
    gate_key = f"gate:{repo}#20:{head}"
    extra = {"stray-pass-ignored": {"stray": "VERDICT: PASS"},
             "earlier-fail-later-pass": {gate_key + ":old:retry": "old"},
             "retry-replaced-pass": {gate_key + ":old:retry": "old"},
             "older-running-newer-pass": {gate_key + ":old:retry": "old"},
             "older-pass-newer-pass": {gate_key + ":old:retry": "old"}}
    replies = {"stray": full, "old": "dead\nVERDICT: FAIL"}
    replies_by_case = {"retry-replaced-pass": {"old": "interrupted"}, "older-pass-newer-pass": {"old": full}}
    live_by_case = {"older-running-newer-pass": {"old"}}
    for name, target, verdict, reply, ledger, expected, changed in cases:
        actions = []
        receipts = {} if verdict == "absent" else {f"gate:{target}#20:{head}": "gate", "base:gate": "main"}
        receipts.update(extra.get(name, {}))
        receipts.update({f"base:{v}": "main" for k, v in extra.get(name, {}).items() if k.startswith("gate:")})
        thread_replies = {**replies, **replies_by_case.get(name, {}), "gate": reply}
        pr = dict(number=20, state="OPEN", headRefOid=head, changedFiles=1,
                  body=f"Refs #10\nBuilder check: PASS {head}", mergeable="MERGEABLE")
        newer = [dict(number=21, state="OPEN", body="Refs #10")] if name.startswith("older-") and "superseded" in name else []
        snapshot = {"repos": {target: {"prs": [pr, *newer], "issues": [dict(number=10, labels=[])]}}}

        def command(cmd, timeout=150, target=target, changed=changed, actions=actions,
                    head=head, reply=reply, verdict=verdict, name=name):
            if cmd == ["gh", "pr", "view", "20", "-R", target, "--json", "state,mergedAt"]:
                return json.dumps({"state": "OPEN", "mergedAt": None})
            if cmd == ["gh", "pr", "view", "20", "-R", target, "--json", "baseRefName,headRefOid"]:
                # The pre-merge guard: the base and head the review was taken
                # against, read in one call immediately before the merge.
                return json.dumps({"baseRefName": "main", "headRefOid": head})
            if cmd == ["gh", "pr", "view", "20", "-R", target, "--json", "baseRefName"]:
                # The post-merge guard: a merged pull request cannot be
                # retargeted, so this base is the one the merge landed on.
                return json.dumps({"baseRefName": "main"})
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
                 patch.object(lane, "read_json", return_value=dict(number=20, state="OPEN", headRefName="builder/fixture",
                                                baseRefName="other" if name == "retargeted-after-pass" else "main")), \
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


def merged_restart():
    import lane_driver as lane
    head = "a" * 40
    merged = [dict(number=20, headRefOid=head, body="Refs #10", mergedAt="2999-01-01T00:00:00Z", baseRefName="main"),
              dict(number=21, headRefOid="b" * 40, body="Refs #10", mergedAt="2000-01-01T00:00:00Z", baseRefName="main")]
    for repo, key, receipts, reply, expected, board in [
        ("shyamsivakumar/mac-ops", "MO", {f"gate:shyamsivakumar/mac-ops#20:{head}": "gate", "base:gate": "main"},
         f"PROVIDES: PASS {head}\nCHECK: PASS {head}\nVERDICT: PASS",
         ["provides", "ff"], None),
        ("shyamsivakumar/mac-ops", "MO", {f"gate:shyamsivakumar/mac-ops#20:{head}": "gate", "base:gate": "main"},
         f"PROVIDES: PASS {head}\nCHECK: PASS {head}\nVERDICT: PASS", ["provides"], "close-failed"),
        ("shyamsivakumar/mac-ops", "MO", {}, "", [], "owner"),
        ("shyamsivakumar/strategy-replay-workbench", "SRW", {}, "", [], "decisions"),
    ]:
        actions = []

        def command(cmd, timeout=150, actions=actions, board=board):
            if cmd[:3] == ["gh", "pr", "list"]:
                return json.dumps(merged)
            if cmd[:2] == ["ticket", "close"]:
                exact(cmd[3:5], ["--pr", "20"])
                actions.append("provides")
                if board == "close-failed":
                    raise subprocess.CalledProcessError(1, cmd)
                return "closed"
            if cmd[0] == "git" and "worktree" in cmd:
                return "worktree /fixture/main\0HEAD fixture\0branch refs/heads/main\0\0"
            if cmd[0] == "git" and "symbolic-ref" in cmd:
                return "refs/heads/main"
            if cmd[0] == "git" and "--ff-only" in cmd:
                actions.append("ff")
                return "updated"
            raise AssertionError(f"unexpected command: {cmd}")

        def threads(tool, args, reply=reply):
            return {"thread": {"status": "completed"}, "items": [{"type": "assistant_message", "text": reply}]}

        ledger = {}
        with tempfile.TemporaryDirectory() as scratch, scratch_board(scratch) as decisions, \
             patch.dict(os.environ, {"COORDINATOR_OWNER_BOARD": str(Path(scratch) / "owner.json")}), \
             patch.object(lane, "RECEIPTS", str(Path(scratch) / "receipts.json")), \
             patch.object(lane, "CFG", {repo: dict(key=key, projectId="fixture")}), \
             patch.object(lane, "SNAPSHOT", {"repos": {repo: {"issues": [dict(number=10, labels=[])]}}}), \
             patch.object(lane, "DRY", False), \
             patch.object(lane, "run", command), patch.object(lane, "t3", threads):
            Path(scratch, "receipts.json").write_text(json.dumps(receipts))
            for _ in range(2):
                lane.settle_merged_prs(repo, ledger)
                exact(actions, expected)
            item_id = f"lane-merged-unreviewed-{key}-20"
            owner_path = Path(scratch, "owner.json")
            owner = [i["id"] for i in json.loads(owner_path.read_text())["items"]] if owner_path.exists() else []
            exact(owner, [item_id] if board == "owner" else
                  ["lane-close-failed-MO-20"] if board == "close-failed" else [])
            exact([i["id"] for i in json.loads(decisions.read_text())["items"]],
                  [item_id] if board == "decisions" else [])


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

        def read(cmd):
            gh_calls.append(cmd)
            return dict(number=20, state="OPEN", headRefName="builder/x", baseRefName=live_base, headRefOid=head,
                        body="Refs #10", changedFiles=1)

        def threads(tool, args):
            return {"thread": {"status": "completed" if finished else "running"},
                    "items": [{"type": "assistant_message", "text": replies[args["threadId"]]}]}

        ledger = {} if ledger is None else ledger
        output = io.StringIO()
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
    merged = dict(state="MERGED", headRefOid=head, body="Refs #10", mergeCommit={"oid": "b" * 40})
    cases = [(merged, proof, True), (dict(merged, state="OPEN"), proof, False),
             (dict(merged, headRefOid="c" * 40), proof, False),
             (dict(merged, body="Refs #11"), proof, False),
             (dict(merged, mergeCommit=None), proof, False),
             (merged, proof.replace("PROVIDES: PASS", "PROVIDES: FAIL"), False),
             (merged, proof.replace("CHECK: PASS", "CHECK: FAIL"), False),
             (merged, proof.replace("VERDICT: PASS", "VERDICT: FAIL"), False)]
    bare = f"CHECK: PASS {head}\nVERDICT: PASS"
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
        if cmd == ["gh", "pr", "view", "20", "-R", repo, "--json", "state,mergedAt"]:
            return json.dumps({"state": "OPEN", "mergedAt": None})
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
         patch.object(lane, "read_json", return_value=dict(number=20, state="OPEN", headRefName="builder/fixture", baseRefName="main")), \
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
            exact([c.args[0] for c in logs().write.call_args_list], [] if seconds <= 2400 else [
                "- cap mis-sized 2026-11-15T00:40Z | t3 | ticket:fixture/repo#2:a1 | paused-run | 10.0 min\n"] * 2)
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
        exact(json.loads(decisions.read_text()), {"items": [{"id": "unrelated"}]})
        with patch.object(adapter, "hourly", return_value="PASS"):
            outcome[0] = SimpleNamespace(returncode=1, stdout="FAIL watchdog\n")
            now[0] += 3600
            try:
                exact(run(), "FAIL")
            except AssertionError:
                pass
            else:
                raise AssertionError("negative control accepted unconditional PASS")
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

    with patch("builtins.open", side_effect=opened),          patch.object(time, "time", return_value=now),          patch.object(os.path, "getmtime", side_effect=lambda path: mtimes[path]),          patch.object(lane.json, "dump", side_effect=saved),          patch.object(os, "replace") as replace,          patch.object(lane.subprocess, "run", side_effect=fake_run),          patch.object(alarms, "MUTE_PATH", mute),          patch.object(alarms, "read_board", side_effect=read_board),          patch.object(alarms, "write_board", side_effect=write_board):
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


def api_budget():
    from live_smoke import fixture as live_fixture
    live_fixture()
    import datetime as dt
    import lane_driver as lane
    from unittest.mock import mock_open
    repo = "fixture/repo"
    ledger = {}
    commands = []
    def read(command):
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
    with tempfile.TemporaryDirectory() as scratch, scratch_board(scratch) as decisions:
        board = decisions.with_name("mac-ops-owner.json")

        def command(cmd, timeout=150):
            if cmd[:3] == ["gh", "pr", "view"]:
                return json.dumps({"state": "OPEN", "mergedAt": None})
            if cmd[:2] == ["gh", "api"]:
                # The prompt classification this branch adds reads the pinned
                # trees; every head here is code-only against its base.
                endpoint = cmd[-1]
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

        def act(number, head, ledger, verdict=("FAIL", {"threadId": "gate"}, "finding\nVERDICT: FAIL")):
            """Run the lane over one pull request at one head."""
            current[0] = head
            pr = dict(number=number, state="OPEN", headRefOid=head,
                      body=f"Refs #10\nBuilder check: PASS {head}", mergeable="MERGEABLE")
            snapshot = {"repos": {repo: {"prs": [pr], "issues": [dict(number=10, labels=[])]}}}
            with patch.object(lane, "CFG", {repo: dict(key="FIX", projectId="fixture")}), \
                 patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "DRY", False), \
                 patch.object(lane, "builder_thread", return_value=("10", "live-builder")), \
                 patch.object(lane, "gate_verdict", return_value=verdict), \
                 patch.object(lane, "read_json", return_value=dict(number=number, state="OPEN", headRefName="builder/fixture", baseRefName="main")), \
                 patch.object(lane, "run", command), patch.object(lane, "t3", threads), \
                 patch.object(lane, "send", send):
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
        exact(len(items[0]["options"]), 2)
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

        check_pass = f"CHECK: PASS {heads[2]}"
        none_line = f"finding\n{check_pass}\n{lane.OPEN_FINDINGS_NONE}\nVERDICT: FAIL"
        merged, briefs = [], []

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
        # (f) the brief asks for the line from round 3 on, not at round 1.
        def brief_for(ledger):
            with patch.object(lane, "start", lambda args, prio, led, lkey: briefs.append(args["message"]) or "started"):
                act(36, heads[3], ledger, verdict=("absent", None, ""))
            return briefs[-1]
        two_rounds = {f"fix:{repo}#36:{heads[0]}": "sent", f"fix:{repo}#36:{heads[1]}": "sent"}
        exact(lane.OPEN_FINDINGS_NONE in brief_for(two_rounds), True)
        exact(lane.OPEN_FINDINGS_NONE in brief_for({}), False)


def decisions_board_guard():
    """A test run never writes the board Shyam reads.

    The lane raises one item on the decisions board when a pull request
    uses its review rounds. The board path comes from the environment, so
    a test points it at a scratch file. This eval runs the path that
    raises the item and checks that every write names the scratch file as
    its destination. The board Shyam reads is not compared before and
    after, because the coordinator may publish to it while this runs.
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
                patch.object(lane.alarms, "board_update", record):
            lane.gate_round_decision("fixture/repo", 20, "a" * 40, {})
            lane.gate_round_decision("fixture/repo", 20, "a" * 40, {})
        items = json.loads(board.read_text())["items"]
        exact(targets, [str(board)] * 2)
        exact(len(items), 1)
        exact(items[0]["id"], "lane-gate-rounds-fixture-repo-20")


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
                 patch.object(lane, "read_json", return_value=dict(number=385, state="OPEN", headRefName="builder/fixture", baseRefName="main")), \
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
             patch.object(lane, "read_json", return_value=pull), \
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
    with patch.object(lane, "SNAPSHOT", orphan), patch.object(lane, "DRY", True), \
         patch.object(lane, "t3", return_value={}), \
         patch("builtins.open", mock_open(read_data="{}")):
        exact(lane.unstick(repo, {}), "DRY unstick [9]")


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


EVALS = {"send-integrity": send_integrity, "root-workspace": root_workspace, "worktree-base-ref": worktree_base_ref, "consolidation-guard": consolidation_guard, "script-results": script_results,"start-routing": start_routing, "dead-run-recovery": dead_run_recovery, "gate-pipeline": gate_pipeline, "merged-restart": merged_restart, "merge-pass": merge_pass, "gate-round-cap": gate_round_cap, "decisions-board-guard": decisions_board_guard, "no-parking": no_parking, "turncap": turncap, "watchdog": watchdog, "zero-merge": zero_merge, "board-integrity": board_integrity, "api-budget": api_budget, "ff-drift": ff_drift, "cycle-health": cycle_health, "stall": stall, "alarm-mute": alarm_mute}


def main():
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
