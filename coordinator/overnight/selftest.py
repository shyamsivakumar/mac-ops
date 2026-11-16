import contextlib
import importlib.machinery
import importlib.util
import io
import json
import re
from pathlib import Path
import subprocess
import tempfile
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
    completion_boundary()
    main_update_boundary()


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
    for pull, reply, allowed in cases:
        actions = []
        args = Namespace(ref="shyamsivakumar/mac-ops#10", pr=20, head=head, gate_thread="gate")
        def close(cmd):
            exact(cmd[:3], ["issue", "close", "10"])
            actions.append("close")
            return "closed"
        with patch.object(ticket, "gh_json", return_value=pull), \
             patch.object(ticket, "t3_call", return_value={"items": [dict(type="assistant_message", text=reply)]}), \
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
         patch.object(lane, "t3", return_value={"thread": {"status": status}}), \
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


def watchdog():
    hourly_selftest_fixture()
    import lane_driver as lane
    import os
    import time
    from unittest.mock import mock_open

    limits = {"tick": 65, "gatekeep": 120, "dispatch": 10, "lanes": 10}
    exact({name: minutes for name, (_, minutes) in lane.WATCH.items()}, limits)
    now = 1000000
    other = {"id": "unrelated", "title": "preserve"}
    state = {"items": [other]}
    mtimes = {path: now for path, _ in lane.WATCH.values()}
    decisions = "/Users/shyamsivakumar/Code/coordinator/decisions.json"

    def opened(path, mode="r"):
        exact(str(path), decisions + (".tmp" if mode == "w" else ""))
        if mode == "r":
            return io.StringIO(json.dumps(state))
        return mock_open()()

    def saved(value, handle, **kwargs):
        state.clear()
        state.update(json.loads(json.dumps(value)))

    with patch("builtins.open", side_effect=opened),          patch.object(time, "time", return_value=now),          patch.object(os.path, "getmtime", side_effect=lambda path: mtimes[path]),          patch.object(lane.json, "dump", side_effect=saved),          patch.object(os, "replace") as replace:
        for name, minutes in limits.items():
            path = lane.WATCH[name][0]
            mtimes[path] = now - minutes * 60
            lane.watchdog()
            exact(state["items"], [other])
            mtimes[path] -= 60
            expected = [other, {"id": "factory-watchdog", "group": "Coordinator",
                "kind": "action",
                "title": f"Factory job silent: {name} silent {minutes + 1} min (limit {minutes})",
                "why": "A coordinator job stopped writing its log. The coordinator is routing a fix; nothing for you unless this stays up."}]
            for _ in range(2):
                lane.watchdog()
                exact(state["items"], expected)
            mtimes[path] = now
            lane.watchdog()
            exact(state["items"], [other])
        exact(replace.call_count, 16)
        for call in replace.call_args_list:
            exact(call.args, (decisions + ".tmp", decisions))


def zero_merge():
    import datetime as dt
    import lane_driver as lane
    other = {"id": "unrelated"}
    state = {"items": [other]}
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
    alert = {"id": "factory-zero-merge", "group": "Coordinator", "kind": "action",
        "title": "No merge in 60 minutes with open PRs",
        "why": "The coordinator must inspect blocked PRs and restore merge progress."}
    with patch.object(dt, "datetime", Clock), patch.object(lane, "read_json", side_effect=read), \
         patch("builtins.open", side_effect=opened), patch.object(lane.json, "dump", side_effect=saved), \
         patch.object(lane.os, "replace") as replace:
        for stamps, expected in [([], [other, alert]),
                (["2026-11-15T10:59:59Z"], [other, alert]),
                (["2026-11-15T11:00:00Z"], [other]),
                (["2026-11-15T11:59:00Z"], [other]),
                ([], [other, alert])]:
            rows = [{"mergedAt": stamp} for stamp in stamps]
            lane.zero_merge(snapshot)
            exact(state["items"], expected)
        exact(calls, ["fixture/one", "fixture/two"] * 5)
        with patch.object(lane, "read_json", side_effect=RuntimeError("fixture read failure")):
            try:
                lane.zero_merge(snapshot)
            except RuntimeError as exc:
                exact(str(exc), "fixture read failure")
            else:
                raise AssertionError("read failure was swallowed")
        exact(state["items"], [other, alert])
        exact(replace.call_count, 5)
        snapshot["repos"]["fixture/one"]["prs"] = []
        lane.zero_merge(snapshot)
        exact(state["items"], [other])
        exact(len(calls), 10)
        exact(replace.call_count, 6)
        for call in replace.call_args_list:
            exact(call.args, ("/Users/shyamsivakumar/Code/coordinator/decisions.json.tmp",
                              "/Users/shyamsivakumar/Code/coordinator/decisions.json"))


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
         patch.object(lane, "api_remaining", return_value={"core": 1000, "graphql": 1000}), \
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
    from unittest.mock import mock_open
    repo = "fixture/repo"
    path = "/Users/shyamsivakumar/Code/fixture"
    local, origin = "a" * 40, "b" * 40
    calls = []
    ancestor = True

    def run(cmd, **kwargs):
        if cmd == ["git", "-C", path, "rev-parse", "main", "origin/main"]:
            return f"{local} {origin}"
        if cmd == ["git", "-C", path, "merge-base", "--is-ancestor", local, origin]:
            if not ancestor:
                raise subprocess.CalledProcessError(1, cmd)
            return ""
        if cmd[:2] == [lane.COORDQ, "start"]:
            exact(cmd[3:], ["--priority", "700"])
            payload = json.loads(cmd[2])
            exact(payload["title"], "Chore · level local main (FIX)")
            calls.append(origin)
            return "fixture-queued"
        raise AssertionError(f"unexpected command: {cmd}")

    with patch.object(lane, "PATHS", {repo: "fixture"}), \
         patch.object(lane, "LANE_REPOS", [repo]), \
         patch.object(lane, "CFG", {repo: {"key": "FIX"}}), \
         patch.object(lane, "DRY", False), \
         patch.object(lane.os.path, "isdir", return_value=True), \
         patch.object(lane, "run", side_effect=run), \
         patch("builtins.open", mock_open(read_data="fixture chore")):
        ledger = {}
        lane.drift_ff(ledger)
        lane.drift_ff(ledger)
        exact(calls, [origin])
        exact(ledger, {f"ff:{repo}:{origin}": "fixture-queued"})
        origin = "c" * 40
        lane.drift_ff(ledger)
        exact(calls, ["b" * 40, origin])
        local = origin
        lane.drift_ff(ledger)
        exact(calls, ["b" * 40, origin])
        origin = "d" * 40
        ancestor = False
        before = dict(ledger)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            lane.drift_ff(ledger)
        exact(output.getvalue().splitlines(), [
            f"FIX   left alone, not fast-forwardable ({local} vs {origin})"])
        exact(ledger, before)
        exact(calls, ["b" * 40, "c" * 40])


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
    cfg = {"types": {"review": "gate"}}
    item = {"body": "Implement the scoped fixture. Report leftover work in the PR.",
            "url": "https://fixture/issue/1"}
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
                return {"thread": thread}
            def command(cmd, timeout=150):
                exact(reads, ["read"])
                exact(cmd[:2], [lane.COORDQ, "start"])
                payload = json.loads(cmd[2])
                if live:
                    exact(payload, {"threadId": "old", "message": "brief"})
                    exact(cmd[3:], ["--tool", "t3_thread_send", "--priority", "800", "--title", "fix"])
                else:
                    exact(payload, {"projectId": "fixture", "title": "fix", "modelSelection": lane.SOL,
                          "runtimeMode": "full-access", "workspaceStrategy": {"type": "root"}, "message": "brief"})
                    exact(cmd[3:], ["--priority", "800"])
                actions.append("send" if live else "fresh")
                if failure == "error":
                    raise subprocess.CalledProcessError(1, cmd)
                return "" if failure == "empty" else "receipt"
            output = io.StringIO()
            with patch.object(lane, "CFG", {repo: {"projectId": "fixture"}}), \
                 patch.object(lane, "DRY", False), patch.object(lane, "t3", read), \
                 patch.object(lane, "run", command), contextlib.redirect_stdout(output):
                try:
                    result = lane.send("old", "brief", "fix", ledger, key)
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
         patch.object(lane, "t3", side_effect=AssertionError("dry read")), \
         patch.object(lane, "run", side_effect=AssertionError("dry dispatch")):
        ledger = {}
        exact(lane.send("old", "brief", "fix", ledger, key), f"DRY {key}")
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
        exact(actions, ["fresh"])
        exact(f"cont:old" in ledger, not failure)
        if failure:
            exact("started" in result, False)
        else:
            exact(result, "continue #385: fresh (old unreachable): receipt")


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


EVALS = {"send-integrity": send_integrity, "consolidation-guard": consolidation_guard, "script-results": script_results,"start-routing": start_routing, "gate-pipeline": gate_pipeline, "no-parking": no_parking, "turncap": turncap, "watchdog": watchdog, "zero-merge": zero_merge, "board-integrity": board_integrity, "api-budget": api_budget, "ff-drift": ff_drift, "cycle-health": cycle_health}


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
                    if name == "send-integrity":
                        import lane_driver
                        with patch.object(lane_driver, "send", return_value="started"):
                            try:
                                evaluate()
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError("negative control accepted unchecked send")
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
