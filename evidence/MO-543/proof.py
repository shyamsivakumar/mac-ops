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


def main():
    gate_briefs()
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
