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
    args = argparse.Namespace(ref="shyamsivakumar/mac-ops#544", print_brief=True, dry_run=False)
    out = io.StringIO()
    with patch.object(ticket, "load_config", return_value={}), \
            patch.object(ticket, "repo_config", return_value={"key": "MO", "projectId": "fixture"}), \
            patch.object(ticket, "fetch_pull", return_value=pull), \
            patch.object(ticket, "fetch_issue", return_value={"number": 543, "title": "MO-543 · hold prompt changes", "comments": []}), \
            patch.object(ticket, "check_ticket_key", return_value=None), \
            patch.object(ticket, "builder_models", return_value=(["gpt-6.2-astra"], False)), \
            patch.object(ticket, "authed_login", return_value="shyamsivakumar"), \
            patch.object(ticket, "check_publisher", return_value=False), \
            patch.object(ticket, "ascend_repo", return_value=False), \
            patch.object(ticket, "pull_files", return_value=paths), \
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
    lane.prompt_pull = lambda repo, number: False
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
            state = coordq.gate_prompt_state(repo, 544)
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
        unknown = coordq.gate_prompt_state(repo, 544)
    grant("queue gatekeep: an unreadable file list is unknown, never clear",
          unknown == prompt_paths.UNKNOWN and read.call_count > 1, command)
    # A rename carries the name the file left, and that name can be a prompt.
    renamed = [{"filename": "archive/reviewer.md", "previous_filename": "prompts/reviewer.md"}]
    with patch.object(coordq, "gh_json", return_value=renamed):
        state = coordq.gate_prompt_state(repo, 544)
    grant("queue gatekeep: a renamed prompt file holds the PR", state == prompt_paths.HOLD, command)


def ticket_file_read():
    """The real read `ticket gate` makes: the paths of the pull request."""
    ticket = load(BIN / "ticket", "proof_ticket_files")
    command = "python3 evidence/MO-543/proof.py"
    payload = [{"filename": "coordinator/config/AGENT-RULES.md"},
               {"filename": "coordinator/overnight/lane_driver.py",
                "previous_filename": "coordinator/overnight/old_lane.py"}]
    with patch.object(ticket, "gh_json", return_value=payload):
        paths = ticket.pull_files("shyamsivakumar/mac-ops", 544, 2)
    grant("ticket's own file read returns every changed path",
          paths == ["coordinator/config/AGENT-RULES.md",
                    "coordinator/overnight/lane_driver.py",
                    "coordinator/overnight/old_lane.py"], command)
    # A shorter list than the pull request's own changed-file count is a
    # truncated read, and a truncated read is not a known list: no hold.
    with patch.object(ticket, "gh_json", return_value=payload[:1]):
        short = ticket.pull_files("shyamsivakumar/mac-ops", 544, 2)
    grant("a truncated file read is none, so the gate refuses it", short is None, command)
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
