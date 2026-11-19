"""Proof for #543: a prompt change stops at the verdict.

The `ticket gate` dry run is the real command with its GitHub reads served
from fixtures, so the brief that a live gate would receive is built by the
real code path. The lane replay is the registered `gate-pipeline` eval in
`coordinator/overnight/selftest.py`, and it runs here too, with a negative
control that must fail.

    python3 evidence/MO-543/proof.py
"""
import argparse
import importlib.machinery
import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "coordinator" / "bin"
OVERNIGHT = ROOT / "coordinator" / "overnight"
for folder in (BIN, OVERNIGHT):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import prompt_paths  # noqa: E402

HEAD = "b" * 40
PROMPT_PATHS = ["coordinator/config/AGENT-RULES.md", "coordinator/bin/gate_bar.py"]
CODE_PATHS = ["coordinator/bin/ticket", "docs/ticket-gate.md"]
RESULTS = []


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def grant(gate, check, command):
    RESULTS.append((gate, check, command))


def dry_run_brief(ticket, paths):
    """The brief `ticket gate --print-brief` prints for one changed-file list."""
    pull = {"number": 544, "state": "OPEN", "isDraft": False, "title": "fixture",
            "body": "Refs #543", "headRefOid": HEAD, "baseRefName": "main",
            "url": "https://github.com/shyamsivakumar/mac-ops/pull/544",
            "changedFiles": len(paths)}
    import proof_file
    args = argparse.Namespace(ref="shyamsivakumar/mac-ops#544", print_brief=True,
                              dry_run=False, print_model=False)
    out = io.StringIO()

    def api_read(command):
        """The pinned trees of the pull request, which now classify it."""
        endpoint = command[-1]
        if "/compare/" in endpoint:
            return {"merge_base_commit": {"sha": "base"}}
        if endpoint.endswith("/git/trees/base?recursive=1"):
            return {"tree": [{"type": "blob", "path": path, "sha": "1"} for path in paths]}
        if endpoint.endswith(f"/git/trees/{HEAD}?recursive=1"):
            return {"tree": [{"type": "blob", "path": path, "sha": "2"} for path in paths]}
        raise AssertionError(f"unexpected read {command}")

    with patch.object(ticket, "load_config", return_value={}), \
            patch.object(ticket, "repo_config", return_value={"key": "MO", "projectId": "fixture"}), \
            patch.object(ticket, "fetch_pull", return_value=pull), \
            patch.object(ticket, "fetch_issue", return_value={"number": 543, "title": "MO-543 · hold prompt changes", "comments": []}), \
            patch.object(ticket, "check_ticket_key", return_value=None), \
            patch.object(ticket, "builder_models", return_value=(["gpt-6.2-astra"], False)), \
            patch.object(ticket, "authed_login", return_value="shyamsivakumar"), \
            patch.object(ticket, "check_publisher", return_value=False), \
            patch.object(ticket, "ascend_repo", return_value=False), \
            patch.object(ticket, "gh_json", side_effect=api_read), \
            patch.object(proof_file, "fetch", return_value=(proof_file.MISSING, None)), \
            redirect_stdout(out):
        ticket.cmd_gate(args)
    return out.getvalue()


def gate_briefs():
    ticket = load(BIN / "ticket", "proof_ticket")
    prompt = dry_run_brief(ticket, PROMPT_PATHS)
    code = dry_run_brief(ticket, CODE_PATHS)
    grant("gate brief: AGENT-RULES PR", "never auto-merges" in prompt
          and "do not merge" in prompt and "gh pr merge" not in prompt
          and "review only" in prompt, "python3 evidence/MO-543/proof.py")
    grant("gate brief: AGENT-RULES PR closes no issue", "gh issue close" not in prompt,
          "python3 evidence/MO-543/proof.py")
    grant("gate brief: AGENT-RULES PR keeps the verdict lines",
          f"CHECK: PASS {HEAD}" in prompt and "VERDICT: PASS" in prompt,
          "python3 evidence/MO-543/proof.py")
    grant("gate brief: code-only PR keeps the merge order",
          "gh pr merge 544 -R shyamsivakumar/mac-ops --squash" in code
          and "never auto-merges" not in code, "python3 evidence/MO-543/proof.py")
    print("--- prompt PR brief tail ---")
    print("\n".join(prompt.strip().splitlines()[-2:]))
    print("--- code-only PR brief tail ---")
    print("\n".join(code.strip().splitlines()[-2:]))


def lane_replay():
    selftest = load(OVERNIGHT / "selftest.py", "proof_selftest")
    import lane_driver as lane  # the module the eval itself imports
    command = "python3 evidence/MO-543/proof.py"
    try:
        selftest.gate_pipeline()
    except AssertionError as exc:
        print(f"gate-pipeline: {exc}")
        grant("lane replay: PASS on a prompt PR adds one decisions item and no merge", False, command)
    else:
        grant("lane replay: PASS on a prompt PR adds one decisions item and no merge", True, command)
    # The negative control: with the path list switched off, the same eval
    # must fail on the merge it accepted. A control that still passed would
    # mean the replay proves nothing.
    saved = lane.prompt_pull
    lane.prompt_pull = lambda repo, number, *rest: prompt_paths.CLEAR
    try:
        selftest.gate_pipeline()
    except AssertionError as exc:
        grant("lane replay negative control (hold off)",
              "prompt-pass" in str(exc) and "merge" in str(exc), command)
    else:
        grant("lane replay negative control (hold off)", False, command)
    finally:
        lane.prompt_pull = saved


def queue_briefs():
    """`coordq gatekeep` builds its brief through the same flag.

    The end-to-end gatekeep path (its own candidate scan to the queued
    brief) is `tests/test_prompt_paths.py::CoordqGateTest`, which the
    repository check runs: this is the detection and the brief it feeds.
    """
    coordq = load(BIN / "coordq", "proof_coordq")
    settings = {"key": "MO", "projectId": "fixture"}
    model = {"instanceId": "codex", "model": "gpt-6.2-astra"}
    repo = "shyamsivakumar/mac-ops"
    command = "python3 evidence/MO-543/proof.py"
    briefs = {}
    for name, paths in (("prompt", PROMPT_PATHS), ("code", CODE_PATHS)):
        files = [{"filename": path} for path in paths]
        with patch.object(coordq, "gh_json", return_value=files):
            state = coordq.gate_prompt_state(repo, 544, len(files))
        briefs[name] = coordq.gate_args(settings, repo, 543, 544, HEAD, False, model,
                                        prompt=state == prompt_paths.HOLD)["message"]
    grant("queue gatekeep brief: prompt PR gets the hold",
          "never auto-merges" in briefs["prompt"] and "gh pr merge" not in briefs["prompt"],
          command)
    grant("queue gatekeep brief: code-only PR keeps the merge order",
          "gh pr merge 544 -R shyamsivakumar/mac-ops --squash" in briefs["code"]
          and "never auto-merges" not in briefs["code"], command)
    # A transient GitHub error must not read as clear: no brief is built, so
    # no merge order can be written from a list the queue never saw.
    with patch.object(coordq, "gh_json", side_effect=RuntimeError("transient")) as read:
        unknown = coordq.gate_prompt_state(repo, 544, 1)
    grant("queue gatekeep: an unreadable file list is unknown, never clear",
          unknown == prompt_paths.UNKNOWN and read.call_count > 1, command)
    # A rename carries the name the file left, and that name can be a prompt.
    renamed = [{"filename": "archive/reviewer.md", "previous_filename": "prompts/reviewer.md"}]
    with patch.object(coordq, "gh_json", return_value=renamed):
        state = coordq.gate_prompt_state(repo, 544, len(renamed))
    grant("queue gatekeep: a renamed prompt file holds the PR", state == prompt_paths.HOLD, command)
    # GitHub stops the files endpoint at 3,000: a list shorter than the pull
    # request's own changed-file count may have dropped the one prompt file.
    short = [{"filename": "coordinator/bin/ticket"}]
    code_files = [{"filename": "coordinator/bin/ticket"},
                  {"filename": "docs/ticket-gate.md"}]
    with patch.object(coordq, "gh_json", return_value=short):
        truncated = coordq.gate_prompt_state(repo, 544, 3001)
        complete = coordq.gate_prompt_state(repo, 544, 1)
    grant("queue gatekeep: a truncated file list is unknown, never clear",
          truncated == prompt_paths.UNKNOWN and complete == prompt_paths.CLEAR, command)
    # The count is not taken on trust from the list entry: when the caller has
    # none, the pull request itself gives it, and a count that cannot be read
    # is unknown too. The read is the real helper's own response, a slurped
    # one-row list: reading that list as a dict lost the count and deferred
    # every code-only PR.
    def gh(endpoint):
        if endpoint.endswith("/files?per_page=100"):
            return short
        if endpoint == f"repos/{repo}/pulls/544":
            return [{"number": 544, "changed_files": 3001}]
        raise AssertionError(endpoint)

    with patch.object(coordq, "gh_json", gh):
        fetched = coordq.gate_prompt_state(repo, 544)

    def gh_code(endpoint):
        if endpoint.endswith("/files?per_page=100"):
            return code_files
        return [{"number": 547, "changed_files": len(code_files)}]

    with patch.object(coordq, "gh_json", gh_code):
        code_only = coordq.gate_prompt_state(repo, 547)

    def gh_no_count(endpoint):
        if endpoint.endswith("/files?per_page=100"):
            return short
        raise RuntimeError("count read failed")

    with patch.object(coordq, "gh_json", gh_no_count):
        no_count = coordq.gate_prompt_state(repo, 544)
    grant("queue gatekeep: a missing or unreadable changed-file count is unknown too",
          fetched == prompt_paths.UNKNOWN and no_count == prompt_paths.UNKNOWN, command)
    grant("queue gatekeep: a code-only PR with no list entry count still clears its gate",
          code_only == prompt_paths.CLEAR, command)


def lane_truncation():
    """The lane defers a passing PR whose file list may be short."""
    import lane_driver as lane
    command = "python3 evidence/MO-543/proof.py"
    written = []
    with patch.object(lane, "run",
                      return_value='[[{"filename": "coordinator/bin/ticket"}]]'), \
            patch.object(lane, "publish_decision", lambda item: written.append(item)):
        state = lane.prompt_pull("shyamsivakumar/mac-ops", 544, 3001)
        held = lane.prompt_pass("shyamsivakumar/mac-ops", 544, HEAD, state)
        complete = lane.prompt_pull("shyamsivakumar/mac-ops", 544, 1)
    grant("lane: a truncated file list defers the pass, and a complete one is clear",
          state == prompt_paths.UNKNOWN and "next run retries" in (held or "")
          and complete == prompt_paths.CLEAR and written == [], command)

    def command_without_count(cmd, timeout=150):
        if cmd[:2] == ["gh", "api"] and cmd[2] != "--paginate":
            return '{"changed_files": 3001}'
        return '[[{"filename": "coordinator/bin/ticket"}]]'

    with patch.object(lane, "run", command_without_count), \
            patch.object(lane, "publish_decision", lambda item: written.append(item)):
        missing = lane.prompt_pull("shyamsivakumar/mac-ops", 544)
        held = lane.prompt_pass("shyamsivakumar/mac-ops", 544, HEAD, missing)
    grant("lane: a missing changed-file count is read from the pull request and defers",
          missing == prompt_paths.UNKNOWN and "next run retries" in (held or "")
          and written == [], command)


def board_reconcile():
    """A merge ask goes only when its pull request says it is settled."""
    import lane_driver as lane
    command = "python3 evidence/MO-543/proof.py"
    saved = lane.CFG
    lane.CFG = {"shyamsivakumar/mac-ops": {"key": "MO", "projectId": "fixture"}}
    SNAPSHOT_BACKUP = [lane.SNAPSHOT]
    board = {"items": [{"id": "prompt-merge-MO-544"}, {"id": "prompt-merge-MO-545"},
                        {"id": "prompt-merge-MO-546"}, {"id": "unrelated"}]}
    # 544 is merged between passes, 545 is in the open list, and 546 is still
    # open but fell outside the 200-row snapshot the lane holds.
    snapshot = {"repos": {"shyamsivakumar/mac-ops": {"prs": [{"number": 545}]}}}
    states = {544: {"state": "MERGED", "mergedAt": "2026-11-18T00:00:00Z"},
              546: {"state": "OPEN", "mergedAt": None}}
    taken = []

    def read(cmd, timeout=150):
        return json.dumps(states[int(cmd[3])])

    try:
        with patch.object(lane, "run", read), \
                patch.object(lane.alarms, "read_board", return_value=(b"", board)), \
                patch.object(lane, "withdraw_decision",
                             lambda item_id: (taken.append(item_id), "wrote")[1]):
            removed = lane.reconcile_prompt_items(snapshot)
        # A state read that fails answers nothing, so the card stays.
        unread = []
        with patch.object(lane, "run", side_effect=RuntimeError("gh failed")), \
                patch.object(lane.alarms, "read_board", return_value=(b"", board)), \
                patch.object(lane, "withdraw_decision",
                             lambda item_id: (unread.append(item_id), "wrote")[1]):
            kept = lane.reconcile_prompt_items(snapshot)
        # A per-PR skip withdraws only on a state that says settled.
        settled = []
        snapshot_open = {"repos": {"shyamsivakumar/mac-ops": {"prs": [{"number": 544, "state": "OPEN"}]}}}
        try:
            lane.SNAPSHOT = snapshot_open
            for state in (None, "MERGED"):
                view = {"number": 544, "state": state,
                        "headRefName": "b", "baseRefName": "main"}
                with patch.object(lane, "read_json", return_value=view), \
                        patch.object(lane, "DRY", False), \
                        patch.object(lane, "withdraw_decision",
                                     lambda item_id, view=view: (
                                         settled.append((view["state"], item_id)), "wrote")[1]):
                    lane.act_on_pr("shyamsivakumar/mac-ops", 544, {})
        finally:
            lane.SNAPSHOT = SNAPSHOT_BACKUP[0]
    finally:
        lane.CFG = saved
    grant("board: a merge ask for a settled prompt PR is taken down, an open one stays",
          taken == ["prompt-merge-MO-544"] and removed == 1, command)
    grant("board: an open PR outside the capped snapshot and an unread state keep the card",
          "prompt-merge-MO-546" not in taken and (kept, unread) == (0, []), command)
    grant("board: a per-PR skip withdraws the merge ask only on a settled state",
          settled == [("MERGED", "prompt-merge-MO-544")], command)


def timeout_and_unnamed():
    """A slow read and a nameless entry both defer; neither stops the scan."""
    import subprocess as real_subprocess
    coordq = load(BIN / "coordq", "proof_coordq_timeout")
    lane = load(OVERNIGHT / "lane_driver.py", "proof_lane_timeout")
    command = "python3 evidence/MO-543/proof.py"
    with patch.object(coordq, "gh_json", side_effect=real_subprocess.TimeoutExpired("gh api", 40)):
        slow = coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 1)
    with patch.object(coordq, "gh_json", return_value=[{}]):
        unnamed = coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 1)
    grant("queue gatekeep: a gh timeout and a nameless entry both read unknown",
          slow == prompt_paths.UNKNOWN and unnamed == prompt_paths.UNKNOWN, command)
    with patch.object(lane, "run", side_effect=real_subprocess.TimeoutExpired("gh api", 40)):
        state = lane.prompt_pull("shyamsivakumar/mac-ops", 544, 1)
        held = lane.prompt_pass("shyamsivakumar/mac-ops", 544, HEAD, state)
    grant("lane: a gh timeout defers the pass instead of stopping it",
          state == prompt_paths.UNKNOWN and "next run retries" in (held or ""), command)


def tree_entries():
    """A submodule and a mode-only change are changes too."""
    command = "python3 evidence/MO-543/proof.py"

    def fetch(endpoint):
        if "/compare/" in endpoint:
            return {"merge_base_commit": {"sha": "base"}}
        if endpoint.endswith("/git/trees/base?recursive=1"):
            return {"tree": [{"type": "blob", "path": "prompts/reviewer.md",
                              "mode": "100644", "sha": "same"},
                             {"type": "blob", "path": "a.py", "mode": "100644", "sha": "1"}]}
        return {"tree": [{"type": "blob", "path": "prompts/reviewer.md",
                          "mode": "100755", "sha": "same"},
                         {"type": "blob", "path": "a.py", "mode": "100644", "sha": "1"},
                         {"type": "commit", "path": "skills/reviewer",
                          "mode": "160000", "sha": "cafe"}]}

    paths = prompt_paths.tree_diff(fetch, "o/r", "main", "head")
    grant("trees: a submodule and a mode-only change are both changed paths",
          paths == ["prompts/reviewer.md", "skills/reviewer"]
          and prompt_paths.prompt_scan(paths) == prompt_paths.HOLD, command)


def truncated_tree_walk():
    """A truncated repository tree is walked by subtree, not deferred."""
    command = "python3 evidence/MO-543/proof.py"

    def fetch(endpoint):
        if "/compare/" in endpoint:
            return {"merge_base_commit": {"sha": "base"}}
        if endpoint.endswith("/git/trees/head?recursive=1"):
            return {"truncated": True, "tree": []}
        if endpoint.endswith("/git/trees/head"):
            # The fresh root listing carries the root files a truncated
            # recursive listing never showed.
            return {"tree": [{"type": "blob", "path": "AGENT-RULES.md",
                              "mode": "100644", "sha": "root"},
                             {"type": "tree", "path": "skills", "sha": "sub"}]}
        if endpoint.endswith("/git/trees/sub"):
            return {"tree": [{"type": "blob", "path": "x/SKILL.md",
                              "mode": "100644", "sha": "9"}]}
        if endpoint.endswith("/git/trees/base?recursive=1"):
            return {"tree": [{"type": "blob", "path": "a.py", "mode": "100644", "sha": "1"}]}
        raise AssertionError(endpoint)

    paths = prompt_paths.tree_diff(fetch, "o/r", "main", "head")
    grant("trees: a truncated tree is walked from a fresh root, root files included",
          paths == ["AGENT-RULES.md", "a.py", "skills/x/SKILL.md"]
          and prompt_paths.prompt_scan(paths) == prompt_paths.HOLD, command)


def moved_base_refuses_merge():
    """A base the merge cannot enforce merges nothing, so nothing is reverted."""
    import lane_driver as lane
    command = "python3 evidence/MO-543/proof.py"
    calls = []

    def run_cmd(cmd, timeout=150):
        calls.append(cmd)
        if cmd[:2] == ["gh", "pr"] and "view" in cmd and any(
                "baseRefName" in str(part) for part in cmd):
            return '{"baseRefName": "release/next", "headRefOid": "%s"}' % HEAD
        return ""

    with patch.object(lane, "run", run_cmd):
        merged, note = lane.merge_on_reviewed_base(
            "shyamsivakumar/mac-ops", 544, HEAD, "main")
    issued = [call for call in calls if call[:3] == ["gh", "pr", "merge"]]
    reverted = [call for call in calls if "revert" in " ".join(call)]
    grant("lane: a moved base is never merged, so nothing has to be reverted",
          merged is False and "nothing merged" in note
          and issued == [] and reverted == [], command)


def retarget_after_the_merge_is_reported():
    """A retarget that slips past the pre-merge read is not a reviewed merge.

    No `gh` call can pin the base, so the base is read once more after the
    merge. A merge that landed on another base is reported as one, and the
    caller closes nothing and fast-forwards nothing.
    """
    import lane_driver as lane
    command = "python3 evidence/MO-543/proof.py"
    calls = []
    state = {"base": "release/next", "slip": True}

    def run_cmd(cmd, timeout=150):
        calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "merge"]:
            # The retarget lands in the interval the merge call cannot guard.
            if state["slip"]:
                state["base"] = "main"
            return ""
        if cmd[:2] == ["gh", "pr"] and "view" in cmd and any(
                "baseRefName" in str(part) for part in cmd):
            return json.dumps({"baseRefName": state["base"], "headRefOid": HEAD})
        return ""

    saved_cfg = lane.CFG
    lane.CFG = {"shyamsivakumar/mac-ops": {"key": "MO", "projectId": "fixture"}}
    with patch.object(lane, "run", run_cmd), \
            patch.object(lane, "publish_decision", lambda item: "wrote"):
        merged, note = lane.merge_on_reviewed_base(
            "shyamsivakumar/mac-ops", 544, HEAD, "release/next")
        reported = "not the reviewed release/next" in note and merged is False
        # The same merge with nothing slipping is the reviewed merge.
        state["base"], state["slip"] = "release/next", False
        again, ok_note = lane.merge_on_reviewed_base(
            "shyamsivakumar/mac-ops", 544, HEAD, "release/next")
    lane.CFG = saved_cfg
    grant("lane: a retarget after the merge read is reported, never counted as merged",
          reported and again is True and ok_note == f"#544: merged {HEAD}", command)


def classification_reads_the_own_base():
    """A child pull request is not held for prompt text it inherited."""
    import lane_driver as lane
    command = "python3 evidence/MO-543/proof.py"

    def fetch(endpoint):
        if "/compare/" in endpoint:
            return {"merge_base_commit": {"sha": "base"}}
        if endpoint.endswith("/git/trees/base?recursive=1"):
            return {"tree": [{"type": "blob", "path": "skills/x/SKILL.md",
                              "mode": "100644", "sha": "2"}]}
        return {"tree": [{"type": "blob", "path": "skills/x/SKILL.md",
                          "mode": "100644", "sha": "2"},
                         {"type": "blob", "path": "a.py", "mode": "100644", "sha": "3"}]}

    with patch.object(lane, "api_json", fetch):
        state = lane.prompt_pull("shyamsivakumar/mac-ops", 544, base="feature", head=HEAD)
    grant("lane: an inherited prompt edit does not hold a code-only child pull request",
          state == prompt_paths.CLEAR, command)

def landed_elsewhere_reaches_shyam():
    """A merge that landed on another base becomes a board item, not a log line."""
    import lane_driver as lane
    command = "python3 evidence/MO-543/proof.py"
    published = []
    saved = lane.CFG
    lane.CFG = {"shyamsivakumar/mac-ops": {"key": "MO", "projectId": "fixture"}}

    def run_cmd(cmd, timeout=150):
        if cmd[:2] == ["gh", "pr"] and "view" in cmd:
            if any("headRefOid" in str(part) for part in cmd):
                return '{"baseRefName": "main", "headRefOid": "%s"}' % HEAD
            return '{"baseRefName": "release/next"}'
        return ""

    try:
        with patch.object(lane, "run", run_cmd), \
                patch.object(lane, "publish_decision",
                             lambda item: (published.append(item), "wrote")[1]):
            merged, note = lane.merge_on_reviewed_base(
                "shyamsivakumar/mac-ops", 544, HEAD, "main")
    finally:
        lane.CFG = saved
    grant("lane: a merge that landed on another base reaches Shyam as a board item",
          merged is False and "critical" in note
          and [item["id"] for item in published] == ["base-moved-MO-544"], command)


def action_path_replay():
    """The real action path, not the helper: act_on_pr decides both outcomes.

    The lane replay is the registered `gate-pipeline` eval. It calls the
    production `act_on_pr` with fake GitHub and T3 responses, forbids the
    filesystem, and asserts the exact commands each case issues: a code PASS
    merges, a prompt PASS writes one decisions item and merges nothing.
    """
    selftest = load(OVERNIGHT / "selftest.py", "proof_selftest_actions")
    command = "python3 coordinator/overnight/overnight selftest"
    try:
        selftest.gate_pipeline()
    except AssertionError as exc:
        print(f"gate-pipeline: {exc}")
        grant("action path: a code PASS merges and a prompt PASS writes one decision",
              False, command)
    else:
        grant("action path: a code PASS merges and a prompt PASS writes one decision",
              True, command)


def tree_fallback():
    """A 3,001-file PR never fits the file list, so the trees classify it."""
    coordq = load(BIN / "coordq", "proof_coordq_trees")
    lane = load(OVERNIGHT / "lane_driver.py", "proof_lane_trees")
    command = "python3 evidence/MO-543/proof.py"

    def gh(endpoint):
        if endpoint.endswith("/files?per_page=100"):
            return [{"filename": "coordinator/bin/coordq"}]
        if "/compare/" in endpoint:
            return [{"merge_base_commit": {"sha": "base"}}]
        if endpoint.endswith("/git/trees/base?recursive=1"):
            return [{"tree": [{"type": "blob", "path": "a.py", "sha": "1"}]}]
        if endpoint.endswith("/git/trees/head?recursive=1"):
            return [{"tree": [{"type": "blob", "path": "a.py", "sha": "2"}]}]
        raise AssertionError(endpoint)

    with patch.object(coordq, "gh_json", gh):
        code = coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 3001, "main", "head")
    grant("queue gatekeep: a 3,001-file code PR clears through the trees",
          code == prompt_paths.CLEAR, command)

    def pinned_only(endpoint):
        """The pinned trees, and a live file list that must never be read."""
        if "/files" in endpoint:
            raise AssertionError("a file list read by number describes a live head")
        if "/compare/" in endpoint:
            return [{"merge_base_commit": {"sha": "base"}}]
        if endpoint.endswith("/git/trees/base?recursive=1"):
            return [{"tree": [{"type": "blob", "path": "a.py", "sha": "1"}]}]
        if endpoint.endswith("/git/trees/head?recursive=1"):
            return [{"tree": [{"type": "blob", "path": "skills/x/SKILL.md", "sha": "2"}]}]
        raise AssertionError(endpoint)

    with patch.object(coordq, "gh_json", pinned_only):
        pinned = coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 1, "main", "head")
    grant("queue gatekeep: the pinned head and base decide, never the live file list",
          pinned == prompt_paths.HOLD, command)

    def gh_prompt(endpoint):
        if endpoint.endswith("/files?per_page=100"):
            return [{"filename": "coordinator/bin/coordq"}]
        if "/compare/" in endpoint:
            return [{"merge_base_commit": {"sha": "base"}}]
        if endpoint.endswith("/git/trees/base?recursive=1"):
            return [{"tree": [{"type": "blob", "path": "a.py", "sha": "1"}]}]
        return [{"tree": [{"type": "blob", "path": "a.py", "sha": "2"},
                          {"type": "blob", "path": "prompts/reviewer.md", "sha": "3"}]}]

    with patch.object(coordq, "gh_json", gh_prompt):
        prompt = coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 3001, "main", "head")
    grant("queue gatekeep: a 3,001-file prompt PR still holds through the trees",
          prompt == prompt_paths.HOLD, command)

    def command_lane(cmd, timeout=150):
        endpoint = cmd[-1]
        if "/files?per_page=100" in endpoint:
            return '[[{"filename": "coordinator/bin/ticket"}]]'
        if "/compare/" in endpoint:
            return '{"merge_base_commit": {"sha": "base"}}'
        if endpoint.endswith("/git/trees/base?recursive=1"):
            return '{"tree": [{"type": "blob", "path": "a.py", "sha": "1"}]}'
        return '{"tree": [{"type": "blob", "path": "a.py", "sha": "2"}]}'

    with patch.object(lane, "run", command_lane), \
            patch.object(lane, "pr_changed_count", return_value=3001):
        state = lane.prompt_pull("shyamsivakumar/mac-ops", 544, base="main", head="head")
    grant("lane: a 3,001-file code PR merges instead of deferring for ever",
          state == prompt_paths.CLEAR, command)


def ticket_file_read():
    """The real read `ticket gate` makes: the paths of the pull request."""
    ticket = load(BIN / "ticket", "proof_ticket_files")
    command = "python3 evidence/MO-543/proof.py"
    # The read is slurped: a page is a list of entries, so two pages are two
    # lists. The earlier payload was a flat list, which hid the multi-page case.
    payload = [[{"filename": "coordinator/config/AGENT-RULES.md"},
                {"filename": "coordinator/overnight/lane_driver.py",
                 "previous_filename": "coordinator/overnight/old_lane.py"}]]
    with patch.object(ticket, "gh_json", return_value=payload):
        paths = ticket.pull_files("shyamsivakumar/mac-ops", 544, 2)
    grant("ticket's own file read returns every changed path",
          paths == ["coordinator/config/AGENT-RULES.md",
                    "coordinator/overnight/lane_driver.py",
                    "coordinator/overnight/old_lane.py"], command)
    # A shorter list than the pull request's own changed-file count is a
    # truncated read, and a truncated read is not a known list: no hold.
    with patch.object(ticket, "gh_json", return_value=[[payload[0][0]]]):
        short = ticket.pull_files("shyamsivakumar/mac-ops", 544, 2)
    grant("a truncated file read is none, so the gate refuses it", short is None, command)
    # Two pages are two arrays, and both are read: a 101-file pull request
    # used to fail the parse and read as unknown on every run.
    two_pages = [[{"filename": "coordinator/bin/ticket"}],
                 [{"filename": "prompts/reviewer.md", "previous_filename": None}]]
    with patch.object(ticket, "gh_json", return_value=two_pages):
        paths = ticket.pull_files("shyamsivakumar/mac-ops", 544, 2)
    grant("ticket's read flattens two pages, and page two still counts",
          paths == ["coordinator/bin/ticket", "prompts/reviewer.md"], command)
    with patch.object(ticket, "pull_files", return_value=None):
        try:
            ticket.prompt_hold("shyamsivakumar/mac-ops", 544)
        except ticket.Refuse:
            refused = True
        else:
            refused = False
    grant("the brief refuses an unknown file list instead of ordering a merge",
          refused, command)


def main():
    gate_briefs()
    queue_briefs()
    ticket_file_read()
    timeout_and_unnamed()
    tree_entries()
    truncated_tree_walk()
    moved_base_refuses_merge()
    retarget_after_the_merge_is_reported()
    classification_reads_the_own_base()
    landed_elsewhere_reaches_shyam()
    action_path_replay()
    tree_fallback()
    lane_truncation()
    board_reconcile()
    lane_replay()
    failures = [row for row in RESULTS if not row[1]]
    for gate, ok, command in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'} {gate} | {command}")
    if failures:
        print(f"proof: {len(failures)} check(s) failed")
        return 1
    print(f"proof: {len(RESULTS)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
