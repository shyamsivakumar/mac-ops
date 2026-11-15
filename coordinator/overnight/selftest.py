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
    fixture = json.loads((ROOT / "start-routing.json").read_text())
    repos, board = fixture["repos"], fixture["issues"]
    actions = []

    def run(cmd, timeout=150):
        if cmd[:2] != ["ticket", "start"]:
            raise AssertionError(f"unexpected subprocess: {cmd}")
        actions.append(cmd)
        return "ready" if cmd[-1] == "--dry-run" else "launched"

    with patch.object(lane, "run", run), patch.object(lane, "DRY", False):
        for repo in repos:
            lane.start_next(repo, board, {})
    exact(actions, fixture["expectedActions"])
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


EVALS = {"start-routing": start_routing}


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
