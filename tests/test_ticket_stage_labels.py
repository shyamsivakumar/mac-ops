"""Tests for the one stage label a ticket keeps (mac-ops #533).

`ticket start` and `ticket deliver` both move the stage label through the
same helper, so a started or delivered ticket carries exactly one stage
label. The GitHub command is answered by a fake that keeps the issue's
labels, so nothing on GitHub is read or written.
"""
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_ticket():
    path = ROOT / "coordinator" / "bin" / "ticket"
    # The CLI imports its siblings by name, so the bin folder is on the path.
    sys.path.insert(0, str(path.parent))
    loader = SourceFileLoader("ticket_cli", str(path))
    spec = importlib.util.spec_from_loader("ticket_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


ticket = load_ticket()

REPO = "shyamsivakumar/mac-ops"
NUMBER = 9001
REF = f"{REPO}#{NUMBER}"
TEMPLATE = ["Goal and why", "Context", "Scope and non-goals", "Design fit", "Blocked by",
            "Acceptance and proof", "CI", "Must not cause", "Data/secrets and stop conditions",
            "Rollback", "Gate", "Finish"]
CFG = {
    "repos": {REPO: {"key": "MO", "projectId": "fixture"}},
    "models": {"builder": {"selection": {}, "vendor": "one"},
               "astra": {"selection": {}, "vendor": "two"}},
    "types": {"standard": "builder", "review": "astra"},
    "labels": {"stage": ["backlog", "todo", "started"], "priority": ["1"], "type": ["standard"]},
    "template": TEMPLATE,
}


def body():
    return "\n".join(f"## {name}\nx" for name in TEMPLATE)


class FakeGitHub:
    """The GitHub commands the ticket CLI makes, and the labels they change.

    `failing_edits` counts how many of the next label updates fail. A real
    update removes the labels it was told to remove before it reports that
    the new one could not be added, so a failing update leaves the ticket
    stage-less. One failing update is the failure the helper has to repair,
    and two are the failure it cannot.
    """

    def __init__(self, labels, pulls=(), failing_edits=0):
        self.labels = list(labels)
        # The repository's label set is apart from the issue's labels, so a
        # created label does not land on the issue by itself.
        self.repo_labels = set(labels)
        self.pulls = list(pulls)
        self.edits = []
        self.failing_edits = failing_edits
        self.comments = []

    def issue(self):
        return {"id": "I_1", "number": NUMBER, "url": f"https://github.com/{REF.split('#')[0]}/issues/{NUMBER}",
                "title": "MO-9001 · Stage labels", "state": "OPEN", "body": body(), "comments": [],
                "labels": [{"name": name} for name in self.labels],
                "blockedBy": {"nodes": [], "totalCount": 0}}

    def run(self, cmd, timeout=None, stdin=None):
        args = cmd[1:]
        if args[:2] == ["issue", "view"]:
            return self.done(cmd, json.dumps(self.issue()))
        if args[:2] == ["issue", "edit"]:
            return self.edit(cmd, args)
        if args[:2] == ["issue", "comment"]:
            self.comments.append(args[-1])
            return self.done(cmd, "")
        if args[:2] == ["label", "list"]:
            return self.done(cmd, json.dumps([{"name": name} for name in sorted(self.repo_labels)]))
        if args[:2] == ["label", "create"]:
            self.repo_labels.add(args[2])
            return self.done(cmd, "")
        if args[:2] == ["api", "user"]:
            return self.done(cmd, "shyamsivakumar\n")
        if args[:1] == ["api"] and any("timeline" in arg for arg in args):
            return self.done(cmd, json.dumps(self.timeline()))
        if args[:1] == ["api"] and any("/pulls/" in arg for arg in args):
            return self.done(cmd, json.dumps({"number": self.pulls[0], "state": "open",
                                              "merged": False, "body": f"Refs #{NUMBER}"}))
        if args[:2] == ["repo", "view"]:
            return self.done(cmd, "main\n")
        if args[:2] == ["api", "--paginate"]:
            return self.done(cmd, "[]")
        if cmd[0] == "coordq":
            return self.done(cmd, "queued #1")
        raise AssertionError(f"unexpected command: {cmd}")

    def timeline(self):
        return [{"event": "cross-referenced",
                 "source": {"issue": {"number": pull, "body": f"Refs #{NUMBER}",
                                      "repository": {"full_name": REPO},
                                      "pull_request": {"url": "fixture"}}}}
                for pull in self.pulls]

    def edit(self, cmd, args):
        self.edits.append(args)
        for name in self.option(args, "--remove-label"):
            if name in self.labels:
                self.labels.remove(name)
        if self.failing_edits:
            self.failing_edits -= 1
            return subprocess.CompletedProcess(cmd, 1, "",
                                               "could not add label: 'stage:started' not found")
        for name in self.option(args, "--add-label"):
            if name not in self.labels:
                self.labels.append(name)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    @staticmethod
    def option(args, name):
        if name not in args:
            return []
        return [value for value in args[args.index(name) + 1].split(",") if value]

    @staticmethod
    def done(cmd, out):
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def stages(self):
        return sorted(name for name in self.labels if name.startswith("stage:"))


def start(github):
    """Run the real start path against the fake GitHub."""
    args = Namespace(ref=REF, force_text_blockers=False, print_brief=False, dry_run=False)
    with tempfile.TemporaryDirectory() as scratch, contextlib.ExitStack() as stack:
        for name, value in {"load_config": CFG, "repo_config": dict(CFG["repos"][REPO]),
                            "authed_login": "shyamsivakumar", "default_branch": "main"}.items():
            stack.enter_context(patch.object(ticket, name, return_value=value))
        stack.enter_context(patch.object(ticket, "CACHE_DIR", scratch))
        stack.enter_context(patch.object(ticket, "run", github.run))
        stack.enter_context(patch.object(ticket.time, "sleep", lambda seconds: None))
        ticket.cmd_start(args)


def deliver(github):
    args = Namespace(ref=REF, dry_run=False)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(ticket, "load_config", return_value=CFG))
        stack.enter_context(patch.object(ticket, "run", github.run))
        ticket.cmd_deliver(args)


class StartTest(unittest.TestCase):
    def test_start_leaves_one_stage_label_in_one_update(self):
        github = FakeGitHub(["stage:todo", "type:standard", "priority:1"])
        start(github)
        self.assertEqual(github.stages(), ["stage:started"])
        self.assertEqual(len(github.edits), 1)
        self.assertEqual(FakeGitHub.option(github.edits[0], "--remove-label"), ["stage:todo"])
        self.assertEqual(FakeGitHub.option(github.edits[0], "--add-label"), ["stage:started"])

    def test_start_keeps_the_old_stage_when_the_add_fails(self):
        github = FakeGitHub(["stage:todo", "type:standard", "priority:1"], failing_edits=1)
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as caught:
                start(github)
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("keeps stage:todo", errors.getvalue())
        # The failed update removed the old stage, so the stage is back only
        # because the helper put it back.
        self.assertEqual(github.stages(), ["stage:todo"])
        self.assertEqual(len(github.edits), 2)
        self.assertEqual(FakeGitHub.option(github.edits[1], "--add-label"), ["stage:todo"])

    def test_start_says_when_the_old_stage_could_not_be_put_back(self):
        github = FakeGitHub(["stage:todo", "type:standard", "priority:1"], failing_edits=2)
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as caught:
                start(github)
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("may now carry no stage label", errors.getvalue())
        self.assertNotIn("keeps stage:todo", errors.getvalue())
        self.assertEqual(github.stages(), [])

    def test_start_does_not_write_an_unchanged_stage(self):
        github = FakeGitHub(["stage:started", "type:standard", "priority:1"])
        start(github)
        self.assertEqual(github.stages(), ["stage:started"])
        self.assertEqual(github.edits, [])


class DeliverTest(unittest.TestCase):
    def test_deliver_gives_a_stageless_ticket_its_stage_back(self):
        github = FakeGitHub(["type:standard", "priority:1"], pulls=[20])
        deliver(github)
        self.assertEqual(github.stages(), ["stage:started"])

    def test_deliver_leaves_exactly_one_stage_label(self):
        github = FakeGitHub(["stage:todo", "stage:backlog", "type:standard"], pulls=[20])
        deliver(github)
        self.assertEqual(github.stages(), ["stage:started"])

    def test_deliver_does_not_churn_an_unchanged_ticket(self):
        github = FakeGitHub(["stage:started", "type:standard"], pulls=[20])
        deliver(github)
        self.assertEqual(github.edits, [])

    def test_deliver_refuses_without_an_open_pull_request(self):
        github = FakeGitHub(["stage:todo", "type:standard"])
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as caught:
                deliver(github)
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("refused: no open pull request references this issue", errors.getvalue())
        self.assertEqual(github.stages(), ["stage:todo"])

    def test_start_then_deliver_leaves_one_stage_label_at_each_step(self):
        github = FakeGitHub(["stage:todo", "type:standard", "priority:1"])
        start(github)
        self.assertEqual(github.stages(), ["stage:started"])
        # The builder opens its pull request after the start.
        github.pulls = [20]
        deliver(github)
        self.assertEqual(github.stages(), ["stage:started"])
        # Delivery writes nothing on a ticket that is already delivered.
        self.assertEqual(len(github.edits), 1)


if __name__ == "__main__":
    unittest.main()
