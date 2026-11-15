import contextlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def load_ticket():
    path = ROOT / "ticket" if (ROOT / "ticket").is_file() else ROOT.parent / "bin" / "ticket"
    loader = importlib.machinery.SourceFileLoader("fixture_ticket", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def exact(actual, expected):
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def start_routing():
    import lane_driver as lane
    ticket = load_ticket()
    repos = ["shyamsivakumar/mac-ops", "shyamsivakumar/strategy-replay-workbench",
             "shyamsivakumar/fantasy-football-toolkit", "shyamsivakumar/catalouge",
             "digitized/Concerning", "fixture/sixth"]
    board = json.loads(json.dumps([
        dict(repo=repo, number=n, key=f"F-{n}", stage=stage, problems=problems,
             priority=2, title="bot", builderAlias="implementation", body="fixture", url="fixture")
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
    cfg = {"repos": {repo: {"projectId": repo} for repo in repos},
           "models": {"implementation": {"selection": {"model": "fixture-implementation"}}}}
    with patch.object(ticket, "default_branch", return_value="main"), \
         patch.object(ticket, "brief_reviewer", return_value="astra"):
        for item in board:
            if item["number"] != 3:
                continue
            _, _, payload = ticket.build_start(cfg, item, 1, {})
            exact(payload["workspaceStrategy"], {"type": "worktree", "baseRef": "origin/main", "startFromOrigin": True})
            exact(payload["modelSelection"], {"model": "fixture-implementation"})
    cfg["types"] = {"feature": "implementation", "chore": "maintenance", "review": "gate"}
    cfg["models"].update({"maintenance": {"selection": {"model": "fixture-maintenance"}, "vendor": "builder"},
                          "gate": {"selection": {"model": "fixture-review"}, "vendor": "reviewer"}})
    cfg["models"]["implementation"]["vendor"] = "builder"
    for kind, expected in [("feature", "fixture-implementation"), ("chore", "fixture-maintenance")]:
        item = dict(board[3], type=kind, builder=None, reviewer=None)
        item["builderAlias"], item["reviewerAlias"] = ticket.resolve_models(cfg, item)
        commands = []
        def launch(command, timeout):
            payload = json.loads(command[2])
            exact(payload["modelSelection"], {"model": expected})
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
         patch.object(lane, "t3", return_value={"threads": [{"title": "bot"}]}), \
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


def gate_pipeline():
    import lane_driver as lane
    repo = "shyamsivakumar/mac-ops"
    head = "a" * 40
    failures = []
    cases = [
        ("checked-head", repo, "absent", "", {}, ["astra"]),
        ("pass", repo, "PASS", "VERDICT: PASS", {}, ["merge", "provides", "ff"]),
        ("fail", repo, "FAIL", "finding\nVERDICT: FAIL", {}, ["builder"]),
        ("no-verdict", repo, "none", "interrupted", {}, ["astra"]),
        ("second-no-verdict", repo, "none", "interrupted",
         {f"gate:{repo}#20:{head}": "first", f"regate:{repo}#20:{head}": "retry"}, []),
        ("quota", repo, "none", "Astra quota exhausted",
         {f"gate:{repo}#20:{head}": "first", f"regate:{repo}#20:{head}": "retry"}, ["opus"]),
        ("manual", "digitized/Concerning", "PASS", "VERDICT: PASS", {}, []),
        ("ascend", "ascend/fixture", "absent", "", {}, []),
    ]
    for name, target, verdict, reply, ledger, expected in cases:
        actions = []
        pr = dict(number=20, state="OPEN", headRefOid=head,
                  body=f"Refs #10\nBuilder check: PASS {head}", mergeable="MERGEABLE")
        snapshot = {"repos": {target: {"prs": [pr], "issues": [dict(number=10, labels=[])]}}}

        def command(cmd, timeout=150):
            if cmd[:2] == ["ticket", "gate"]:
                return f"Gate exact head {head}"
            if cmd[:2] == ["ticket", "close"]:
                actions.append("provides")
                return "closed"
            if cmd[:3] == ["gh", "pr", "merge"]:
                exact(cmd[cmd.index("--match-head-commit") + 1], head)
                actions.append("merge")
                return "merged"
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
                    model = payload["modelSelection"]["model"]
                    actions.append("astra" if model == "gpt-6-astra" else "opus" if "opus" in model else model)
                return "fixture-receipt"
            raise AssertionError(f"unexpected command: {cmd}")

        def threads(tool, args):
            if tool == "t3_thread_list":
                exact(head[:8] in args["titleContains"], True)
                return {"threads": [] if verdict == "absent" else [
                    dict(threadId="gate", status="completed", updatedAt="fixture")]}
            if tool == "t3_thread_read":
                if args["threadId"] == "live-builder":
                    return {"thread": {"status": "running", "sendable": True}}
                return {"items": [{"type": "assistant_message", "text": reply}]}
            raise AssertionError(f"unexpected T3 tool: {tool}")

        try:
            with patch.object(lane, "CFG", {target: dict(key="FIX", projectId="fixture")}), \
                 patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "DRY", False), \
                 patch.object(lane, "builder_thread", return_value=("10", "live-builder")), \
                 patch.object(lane, "run", command), patch.object(lane, "t3", threads), \
                 patch("builtins.open", side_effect=AssertionError("live filesystem forbidden")):
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


def no_parking():
    import lane_driver as lane
    repo = "shyamsivakumar/mac-ops"
    head = "a" * 40
    ledger = {f"fix:{repo}#20:old1": "sent", f"fix:{repo}#20:old2": "sent"}
    snapshot = {"repos": {repo: {"prs": [dict(number=20, state="OPEN", headRefOid=head,
        body=f"Builder check: PASS {head}", mergeable="MERGEABLE")],
        "issues": [dict(number=10, labels=[])]}}}
    actions = []

    def command(cmd, timeout=150):
        exact(cmd[0:2], [lane.COORDQ, "start"])
        exact(cmd[3:5], ["--tool", "t3_thread_send"])
        payload = json.loads(cmd[2])
        exact(payload["threadId"], "builder")
        actions.append("continue" if payload["message"].startswith("Continue") else "fix")
        return "sent"

    with patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "DRY", False), \
         patch.object(lane, "CFG", {repo: {"key": "MO"}}), \
         patch.object(lane, "builder_thread", return_value=("10", "builder")), \
         patch.object(lane, "gate_verdict", return_value=("FAIL", None, "findings")), \
         patch.object(lane, "run", command), \
         patch.object(lane, "t3", return_value={"thread": {"status": "interrupted"}}), \
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
        exact(sorted(ledger), sorted([f"fix:{repo}#20:{h}" for h in ["old1", "old2", head, "b" * 40]] +
                                    [f"continue:{repo}#20:{h}" for h in [head, "b" * 40]]))
    try:
        exact(actions + ["park"], ["fix", "continue", "fix", "continue"])
    except AssertionError:
        pass
    else:
        raise AssertionError("negative control accepted parking")


EVALS = {"start-routing": start_routing, "gate-pipeline": gate_pipeline, "no-parking": no_parking}


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
         patch.object(subprocess, "Popen", side_effect=AssertionError("live process forbidden")):
        for name, evaluate in EVALS.items():
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    evaluate()
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
