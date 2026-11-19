"""Prompt, skill and playbook changes never auto-merge (Refs #543).

One path list decides it, and two places read it: the gate brief built by
`ticket gate`, and the lane driver that merges a passing pull request. The
tests here pin the list and both call sites.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_check_proof import load

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "coordinator" / "bin"
OVERNIGHT = ROOT / "coordinator" / "overnight"
# `ticket`, `gate_policy` and `lane_driver` import their neighbours by bare
# name, the way they run from the installed bin directory.
for folder in (BIN, OVERNIGHT):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import prompt_paths  # noqa: E402


class PromptPathTest(unittest.TestCase):
    """The paths that stop a pull request at the verdict."""

    def test_the_prompt_paths_are_prompt_paths(self):
        for path in ("AGENT-RULES.md",
                     "coordinator/config/AGENT-RULES.md",
                     "coordinator/bin/answer_format.py",
                     "coordinator/bin/gate_bar.py",
                     "coordinator/bin/gate_policy.py",
                     "coordinator/overnight/playbook.md",
                     "coordinator/config/agents/code-reviewer.md",
                     "skills/animate/SKILL.md",
                     "runtime/codex/skills/animate/SKILL.md",
                     "prompts/builder.md"):
            with self.subTest(path=path):
                self.assertTrue(prompt_paths.is_prompt_path(path))

    def test_runtime_code_is_not_a_prompt_path(self):
        for path in ("coordinator/bin/ticket",
                     "coordinator/overnight/lane_driver.py",
                     "coordinator/bin/gate_reviewers.py",
                     "scripts/mac_ops_fast_check.py",
                     "docs/ticket-gate.md",
                     "evidence/MO-543/check-proof.md",
                     "tests/test_prompt_paths.py",
                     "",
                     None):
            with self.subTest(path=path):
                self.assertFalse(prompt_paths.is_prompt_path(path))

    def test_one_prompt_path_is_enough(self):
        self.assertTrue(prompt_paths.prompt_change(
            ["coordinator/bin/ticket", "coordinator/config/AGENT-RULES.md"]))
        self.assertFalse(prompt_paths.prompt_change(["coordinator/bin/ticket"]))

    def test_an_unreadable_list_is_unknown_never_clear(self):
        """An unknown list must not read as clear: clear authorizes a merge."""
        self.assertEqual(prompt_paths.prompt_scan(None), prompt_paths.UNKNOWN)
        self.assertEqual(prompt_paths.prompt_scan([]), prompt_paths.CLEAR)
        with self.assertRaises(ValueError):
            prompt_paths.prompt_change(None)

    def test_a_renamed_prompt_file_still_counts(self):
        """Moving prompt text out of a prompt directory still changed it."""
        entry = {"filename": "archive/reviewer.md",
                 "previous_filename": "prompts/reviewer.md"}
        self.assertEqual(prompt_paths.entry_paths(entry),
                         ["archive/reviewer.md", "prompts/reviewer.md"])
        self.assertEqual(prompt_paths.entries_paths([entry]), prompt_paths.entry_paths(entry))
        self.assertEqual(prompt_paths.prompt_scan(prompt_paths.entries_paths([entry])),
                         prompt_paths.HOLD)
        self.assertEqual(prompt_paths.entry_paths(None), [])
        self.assertEqual(prompt_paths.entry_paths("not an entry"), [])

    def test_a_short_list_is_not_complete(self):
        """GitHub stops the files endpoint at 3,000, so a short list hides files."""
        entries = [{"filename": "coordinator/bin/ticket"}]
        self.assertFalse(prompt_paths.list_is_complete(entries, 3001))
        self.assertTrue(prompt_paths.list_is_complete(entries, 1))
        self.assertFalse(prompt_paths.list_is_complete(entries, None))
        self.assertFalse(prompt_paths.list_is_complete(entries, []))

    def test_slurped_pages_are_flattened(self):
        """`--slurp` wraps every page, so 101 files arrive as two arrays."""
        pages = [[{"filename": "a.py"}], [{"filename": "prompts/reviewer.md"}]]
        self.assertEqual(prompt_paths.page_entries(pages),
                         [{"filename": "a.py"}, {"filename": "prompts/reviewer.md"}])
        self.assertIsNone(prompt_paths.page_entries([{"filename": "a.py"}]))
        self.assertIsNone(prompt_paths.page_entries(None))
        self.assertIsNone(prompt_paths.page_entries("not a page list"))

    def test_an_entry_with_no_name_is_not_a_complete_list(self):
        """A nameless entry could be the prompt file, so the list is unusable."""
        self.assertFalse(prompt_paths.list_is_complete([{}], 1))
        self.assertFalse(prompt_paths.list_is_complete([{"filename": ""}], 1))
        self.assertTrue(prompt_paths.list_is_complete([{"filename": "a.py"}], 1))

    def test_a_huge_code_pull_request_clears_from_its_trees(self):
        """The files endpoint stops at 3,000, so the trees give the whole diff."""
        def fetch(endpoint):
            if "/compare/" in endpoint:
                return {"merge_base_commit": {"sha": "base"}}
            if endpoint.endswith("/git/trees/base?recursive=1"):
                return {"tree": [{"type": "blob", "path": "coordinator/bin/ticket", "sha": "1"}]}
            if endpoint.endswith("/git/trees/head?recursive=1"):
                return {"tree": [{"type": "blob", "path": "coordinator/bin/ticket", "sha": "2"},
                                 {"type": "blob", "path": "prompts/reviewer.md", "sha": "3"}]}
            raise AssertionError(endpoint)

        self.assertEqual(prompt_paths.tree_diff(fetch, "o/r", "main", "head"),
                         ["coordinator/bin/ticket", "prompts/reviewer.md"])
        self.assertEqual(prompt_paths.prompt_scan(
            prompt_paths.tree_diff(fetch, "o/r", "main", "head")), prompt_paths.HOLD)

    def test_a_submodule_under_a_prompt_directory_is_a_change(self):
        """A submodule is a `commit` entry, not a blob, and still counts."""
        def fetch(endpoint):
            if "/compare/" in endpoint:
                return {"merge_base_commit": {"sha": "base"}}
            if endpoint.endswith("/git/trees/base?recursive=1"):
                return {"tree": [{"type": "blob", "path": "a.py", "mode": "100644", "sha": "1"}]}
            return {"tree": [{"type": "blob", "path": "a.py", "mode": "100644", "sha": "2"},
                             {"type": "commit", "path": "skills/reviewer",
                              "mode": "160000", "sha": "abc"}]}

        paths = prompt_paths.tree_diff(fetch, "o/r", "main", "head")
        self.assertEqual(paths, ["a.py", "skills/reviewer"])
        self.assertEqual(prompt_paths.prompt_scan(paths), prompt_paths.HOLD)

    def test_a_mode_only_change_is_a_change(self):
        """The blob sha stays the same, yet the path changed."""
        def fetch(endpoint):
            if "/compare/" in endpoint:
                return {"merge_base_commit": {"sha": "base"}}
            if endpoint.endswith("/git/trees/base?recursive=1"):
                return {"tree": [{"type": "blob", "path": "prompts/reviewer.md",
                                  "mode": "100644", "sha": "same"}]}
            return {"tree": [{"type": "blob", "path": "prompts/reviewer.md",
                              "mode": "100755", "sha": "same"}]}

        self.assertEqual(prompt_paths.tree_diff(fetch, "o/r", "main", "head"),
                         ["prompts/reviewer.md"])
        self.assertEqual(prompt_paths.prompt_scan(
            prompt_paths.tree_diff(fetch, "o/r", "main", "head")), prompt_paths.HOLD)

    def test_a_tree_entry_without_a_path_is_no_diff(self):
        self.assertIsNone(prompt_paths.tree_entries({"tree": [{"type": "blob", "sha": "1"}]}))

    def test_a_truncated_tree_is_walked_from_a_fresh_root(self):
        """A cut-short listing is no list: walk the root, files included."""
        def fetch(endpoint):
            if "/compare/" in endpoint:
                return [{"merge_base_commit": {"sha": "base"}}]
            if endpoint.endswith("/git/trees/head?recursive=1"):
                return {"truncated": True,
                        "tree": [{"type": "tree", "path": "skills", "sha": "sub"}]}
            if endpoint.endswith("/git/trees/head"):
                # The fresh root listing: a root file and a directory.
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
        self.assertEqual(paths, ["AGENT-RULES.md", "a.py", "skills/x/SKILL.md"])
        self.assertEqual(prompt_paths.prompt_scan(paths), prompt_paths.HOLD)

    def test_a_walk_spends_its_requests_on_the_changed_directories(self):
        """Two truncated trees are walked in step, and equal subtrees are skipped.

        A code-only pull request in a repository of 5,000 directories gives
        the same subtree sha on both sides for every directory it did not
        touch, so those cost no request at all.
        """
        reads = []

        def fetch(endpoint):
            reads.append(endpoint)
            if "/compare/" in endpoint:
                return {"merge_base_commit": {"sha": "base"}}
            if endpoint.endswith("?recursive=1"):
                return {"truncated": True, "tree": []}
            if endpoint.endswith("/git/trees/base"):
                return {"tree": [{"type": "tree", "path": "docs", "sha": "same-docs"},
                                 {"type": "tree", "path": "vendor", "sha": "same-vendor"},
                                 {"type": "tree", "path": "bin", "sha": "old-bin"}]}
            if endpoint.endswith("/git/trees/head"):
                return {"tree": [{"type": "tree", "path": "docs", "sha": "same-docs"},
                                 {"type": "tree", "path": "vendor", "sha": "same-vendor"},
                                 {"type": "tree", "path": "bin", "sha": "new-bin"}]}
            if endpoint.endswith("/git/trees/old-bin"):
                return {"tree": [{"type": "blob", "path": "run.py", "sha": "1"}]}
            if endpoint.endswith("/git/trees/new-bin"):
                return {"tree": [{"type": "blob", "path": "run.py", "sha": "2"}]}
            raise AssertionError(f"unexpected endpoint {endpoint}")

        self.assertEqual(prompt_paths.tree_diff(fetch, "o/r", "main", "head"),
                         ["bin/run.py"])
        # compare, the two truncated listings, the two roots, and the one
        # directory that changed: the untouched subtrees cost nothing.
        self.assertEqual(len(reads), 7)
        for endpoint in reads:
            self.assertNotIn("same-docs", endpoint)
            self.assertNotIn("same-vendor", endpoint)

    def test_a_walk_that_runs_out_of_requests_is_no_diff(self):
        def fetch(endpoint):
            if "/compare/" in endpoint:
                return {"merge_base_commit": {"sha": "base"}}
            if endpoint.endswith("?recursive=1"):
                return {"truncated": True, "tree": []}
            raise AssertionError(endpoint)

        self.assertIsNone(prompt_paths.tree_paths(fetch, "o/r", "head", requests=[0]))
        self.assertIsNone(prompt_paths.changed_paths(None, {}))
        self.assertIsNone(prompt_paths.tree_entries([{"sha": "x"}]))
        self.assertEqual(prompt_paths.one_object([{"a": 1}]), {"a": 1})
        self.assertIsNone(prompt_paths.one_object([]))

    def test_a_skills_directory_at_the_top_counts(self):
        self.assertTrue(prompt_paths.is_prompt_path("skills/SKILL.md"))
        self.assertTrue(prompt_paths.is_prompt_path("prompts/x.md"))


class GateBriefTest(unittest.TestCase):
    """The gate brief says do not merge, in place of the merge order."""

    def brief(self, **kwargs):
        gate_policy = load(BIN / "gate_policy.py", "gate_policy")
        return gate_policy.build_gate_brief(
            {"key": "MO"}, "shyamsivakumar/mac-ops", 543, 544, "a" * 40, False,
            proof="| syntax | passed |", proof_path="evidence/MO-543/check-proof.md",
            proof_state="found", **kwargs)

    def test_a_prompt_change_gets_no_merge_order(self):
        text = self.brief(prompt=True)
        self.assertIn("never auto-merges", text)
        self.assertIn("do not merge", text)
        self.assertNotIn("gh pr merge", text)
        self.assertIn("review only", text)

    def test_a_prompt_change_closes_no_issue(self):
        text = self.brief(prompt=True)
        self.assertNotIn("gh issue close", text)

    def test_code_only_keeps_the_merge_order(self):
        text = self.brief(prompt=False)
        self.assertIn("gh pr merge 544 -R shyamsivakumar/mac-ops --squash", text)
        self.assertNotIn("never auto-merges", text)
        self.assertIn("review and merge", text)

    def test_the_verdict_lines_are_the_same_either_way(self):
        for prompt in (True, False):
            with self.subTest(prompt=prompt):
                text = self.brief(prompt=prompt)
                self.assertIn("CHECK: PASS " + "a" * 40, text)
                self.assertIn("VERDICT: PASS", text)


class TicketGateTest(unittest.TestCase):
    """`ticket gate` reads the pull request's paths through the list."""

    def setUp(self):
        self.ticket = load(BIN / "ticket", "ticket")

    def prompt_pull(self, paths):
        with patch.object(self.ticket, "pull_files", return_value=paths):
            return self.ticket.prompt_pull("shyamsivakumar/mac-ops", 544, None)

    def test_a_prompt_pull_request_is_held(self):
        self.assertEqual(self.prompt_pull(["coordinator/config/AGENT-RULES.md"]),
                         prompt_paths.HOLD)

    def test_a_code_pull_request_is_not_held(self):
        self.assertEqual(self.prompt_pull(["coordinator/bin/ticket", "docs/ticket-gate.md"]),
                         prompt_paths.CLEAR)

    def test_an_unreadable_list_is_unknown_and_holds_the_merge(self):
        self.assertEqual(self.prompt_pull(None), prompt_paths.UNKNOWN)

    def test_the_brief_refuses_an_unreadable_list(self):
        with patch.object(self.ticket, "pull_files", return_value=None):
            with self.assertRaises(self.ticket.Refuse):
                self.ticket.prompt_hold("shyamsivakumar/mac-ops", 544)

    def test_the_brief_holds_a_renamed_prompt_file(self):
        with patch.object(self.ticket, "pull_files",
                          return_value=["archive/reviewer.md", "prompts/reviewer.md"]):
            self.assertTrue(self.ticket.prompt_hold("shyamsivakumar/mac-ops", 544))

    def test_the_read_flattens_pages(self):
        """The files read is slurped, so 101 files arrive as two pages."""
        pages = [[{"filename": "coordinator/bin/ticket"}],
                 [{"filename": "prompts/reviewer.md"}]]
        with patch.object(self.ticket, "gh_json", return_value=pages):
            self.assertEqual(self.ticket.pull_files("shyamsivakumar/mac-ops", 544, 2),
                             ["coordinator/bin/ticket", "prompts/reviewer.md"])
            self.assertIsNone(self.ticket.pull_files("shyamsivakumar/mac-ops", 544, 3))

    def test_a_huge_prompt_pull_request_holds_through_the_trees(self):
        """The list cannot be complete, so the merge base's trees decide."""

        def gh(args):
            endpoint = args[-1]
            if endpoint.endswith("/files?per_page=100"):
                return [{"filename": "coordinator/bin/ticket"}]
            if "/compare/" in endpoint:
                return {"merge_base_commit": {"sha": "base"}}
            if endpoint.endswith("/git/trees/base?recursive=1"):
                return {"tree": [{"type": "blob", "path": "a.py", "sha": "1"}]}
            if endpoint.endswith("/git/trees/head?recursive=1"):
                return {"tree": [{"type": "blob", "path": "a.py", "sha": "2"},
                                 {"type": "blob", "path": "skills/x/SKILL.md", "sha": "3"}]}
            raise AssertionError(args)

        with patch.object(self.ticket, "gh_json", gh), \
                patch.object(self.ticket, "pull_changed_count", return_value=3001):
            self.assertTrue(self.ticket.prompt_hold("shyamsivakumar/mac-ops", 544,
                                                    base="main", head="head"))

    def test_the_brief_does_not_hold_code(self):
        with patch.object(self.ticket, "pull_files", return_value=["coordinator/bin/ticket"]):
            self.assertFalse(self.ticket.prompt_hold("shyamsivakumar/mac-ops", 544))


class CoordqGateTest(unittest.TestCase):
    """The queue's own gatekeep builds the same held brief."""

    REPO = "shyamsivakumar/fixture"
    HEAD = "a" * 40

    def setUp(self):
        from tests.test_gatekeep_backstop_reviewer import load_coordq
        self.coordq = load_coordq()
        self.coordq._base_pins.clear()

    def test_the_queue_reads_the_same_list(self):
        with patch.object(self.coordq, "gh_json",
                          return_value=[{"filename": "coordinator/config/AGENT-RULES.md"}]):
            self.assertEqual(self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 1),
                             prompt_paths.HOLD)
        with patch.object(self.coordq, "gh_json",
                          return_value=[{"filename": "coordinator/bin/ticket"}]):
            self.assertEqual(self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 1),
                             prompt_paths.CLEAR)

    def test_a_renamed_prompt_file_is_held(self):
        with patch.object(self.coordq, "gh_json",
                          return_value=[{"filename": "archive/reviewer.md",
                                         "previous_filename": "prompts/reviewer.md"}]):
            self.assertEqual(self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 1),
                             prompt_paths.HOLD)

    def test_a_missing_changed_count_is_read_from_the_pull_request(self):
        """The list entry's count is not trusted by presence alone."""
        files = [{"filename": "coordinator/bin/ticket"}]

        def gh(endpoint):
            if endpoint.endswith("/files?per_page=100"):
                return files
            self.assertEqual(endpoint, "repos/shyamsivakumar/mac-ops/pulls/544")
            # The real helper slurps its pages, so one pull request arrives as
            # the only row of a list. A dict here hid that shape, and the
            # missing count deferred every code-only pull request.
            return [{"changed_files": 3001}]

        with patch.object(self.coordq, "gh_json", gh):
            self.assertEqual(self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544),
                             prompt_paths.UNKNOWN)

    def test_a_huge_code_pull_request_clears_through_the_trees(self):
        """3,001 files never fit the list, so the trees decide it."""

        def gh(endpoint):
            if endpoint.endswith("/files?per_page=100"):
                return [{"filename": "coordinator/bin/coordq"}]
            if endpoint.endswith("/git/ref/heads/main"):
                return [{"object": {"sha": "mainsha"}}]
            if endpoint.endswith("/compare/mainsha...head"):
                return [{"merge_base_commit": {"sha": "base"}}]
            if endpoint.endswith("/git/trees/base?recursive=1"):
                return [{"tree": [{"type": "blob", "path": "a.py", "sha": "1"}]}]
            if endpoint.endswith("/git/trees/head?recursive=1"):
                return [{"tree": [{"type": "blob", "path": "a.py", "sha": "2"}]}]
            if endpoint == "repos/shyamsivakumar/mac-ops/pulls/544":
                return [{"changed_files": 3001}]
            raise AssertionError(endpoint)

        with patch.object(self.coordq, "gh_json", gh):
            self.assertEqual(
                self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, base="main", head="head"),
                prompt_paths.CLEAR)

    def test_the_base_branch_is_pinned_once_and_an_unreadable_pin_is_unknown(self):
        reads = []

        def gh(endpoint):
            reads.append(endpoint)
            return [{"object": {"sha": "m" * 40}}]

        with patch.object(self.coordq, "gh_json", gh):
            first = self.coordq.pinned_base("o/r", "main")
            self.assertEqual(self.coordq.pinned_base("o/r", "main"), first)
        self.assertEqual(reads, ["repos/o/r/git/ref/heads/main"])
        self.coordq._base_pins.clear()
        with patch.object(self.coordq, "gh_json", return_value=[]):
            self.assertEqual(self.coordq.gate_prompt_state("o/r", 1, base="main", head="h"),
                             prompt_paths.UNKNOWN)

    def test_the_open_pulls_read_is_never_served_from_the_cache(self):
        seen = {}

        def run(argv, **kwargs):
            seen[argv[-1]] = kwargs.get("fresh")
            return subprocess.CompletedProcess(argv, 0, "[[]]", "")

        with patch.object(self.coordq.gh_gateway, "run", run):
            self.coordq.gh_json("repos/o/r/pulls?state=open&per_page=100")
            self.coordq.gh_json("repos/o/r/issues/9/comments?per_page=100")
        self.assertIs(seen["repos/o/r/pulls?state=open&per_page=100"], True)
        self.assertIs(seen["repos/o/r/issues/9/comments?per_page=100"], False)

    def test_only_reads_of_full_shas_are_kept_for_long(self):
        import gh_gateway
        sha, other = "a" * 40, "b" * 40
        kept = [f"repos/o/r/git/trees/{sha}", f"repos/o/r/git/trees/{sha}?recursive=1",
                f"repos/o/r/compare/{sha}...{other}", f"repos/o/r/contents/evidence/x.md?ref={sha}"]
        moving = ["repos/o/r/git/trees/main", "repos/o/r/compare/main..." + other,
                  "repos/o/r/contents/x.md?ref=main", f"repos/o/r/commits/{sha}/statuses?per_page=100",
                  "repos/o/r/git/ref/heads/main"]
        for route in kept:
            self.assertTrue(gh_gateway.immutable(["gh", "api", route]), route)
        for route in moving:
            self.assertFalse(gh_gateway.immutable(["gh", "api", route]), route)
        self.assertFalse(gh_gateway.immutable(["gh", "api", "-X", "POST", kept[0]]))

    def test_a_code_pull_request_without_a_list_count_is_clear(self):
        """The count read is a one-row list, and its count is used."""
        files = [{"filename": "coordinator/bin/ticket"},
                 {"filename": "docs/ticket-gate.md"}]

        def gh(endpoint):
            if endpoint.endswith("/files?per_page=100"):
                return files
            return [{"changed_files": len(files)}]

        with patch.object(self.coordq, "gh_json", gh):
            self.assertEqual(self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544),
                             prompt_paths.CLEAR)

    def test_a_failed_changed_count_read_is_unknown(self):
        """No count means no completeness, and no completeness means no merge."""
        def gh(endpoint):
            if endpoint.endswith("/files?per_page=100"):
                return [{"filename": "coordinator/bin/ticket"}]
            raise RuntimeError("count read failed")

        with patch.object(self.coordq, "gh_json", gh):
            self.assertEqual(self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544),
                             prompt_paths.UNKNOWN)

    def test_a_nameless_entry_is_unknown_never_clear(self):
        with patch.object(self.coordq, "gh_json", return_value=[{}]):
            self.assertEqual(self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 1),
                             prompt_paths.UNKNOWN)

    def test_a_timeout_defers_instead_of_stopping_the_scan(self):
        """One slow read must not end the pass before later PRs are read."""
        import subprocess as real_subprocess

        with patch.object(self.coordq, "gh_json",
                          side_effect=real_subprocess.TimeoutExpired("gh api", 40)):
            self.assertEqual(self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 1),
                             prompt_paths.UNKNOWN)

    def test_a_failed_read_is_unknown_never_clear(self):
        """A transient GitHub error must not authorize the merge it once did."""
        with patch.object(self.coordq, "gh_json", side_effect=RuntimeError("boom")) as read:
            self.assertEqual(self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 1),
                             prompt_paths.UNKNOWN)
        self.assertEqual(read.call_count, 2)

    def test_a_truncated_list_is_unknown_never_clear(self):
        """A 3,001-file PR may have dropped its one prompt file from the list."""
        files = [{"filename": "coordinator/bin/ticket"}]
        with patch.object(self.coordq, "gh_json", return_value=files):
            self.assertEqual(
                self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 3001),
                prompt_paths.UNKNOWN)
            self.assertEqual(
                self.coordq.gate_prompt_state("shyamsivakumar/mac-ops", 544, 1),
                prompt_paths.CLEAR)

    def test_the_pinned_head_decides_the_paths(self):
        """The gate never decides from a file list read by pull-request number.

        Such a list describes whatever head GitHub holds at that moment, so a
        code-only revision with the same file count could clear a prompt
        head, and `--match-head-commit` still merges when that head is
        restored before the merge.
        """
        def gh(endpoint):
            if "/files" in endpoint:
                raise AssertionError("a file list read by number describes a live head")
            if endpoint.endswith("/git/ref/heads/main"):
                return [{"object": {"sha": "mainsha"}}]
            if "/compare/" in endpoint:
                return [{"merge_base_commit": {"sha": "base"}}]
            if endpoint.endswith("/git/trees/base?recursive=1"):
                return [{"tree": [{"type": "blob", "path": "skills/x/SKILL.md", "sha": "1"}]}]
            if endpoint.endswith(f"/git/trees/{self.HEAD}?recursive=1"):
                return [{"tree": [{"type": "blob", "path": "skills/x/SKILL.md", "sha": "2"}]}]
            raise AssertionError(f"unexpected endpoint {endpoint}")

        with patch.object(self.coordq, "gh_json", gh):
            self.assertEqual(
                self.coordq.gate_prompt_state(self.REPO, 7, 1, base="main", head=self.HEAD),
                prompt_paths.HOLD)

    def test_the_queued_brief_says_do_not_merge(self):
        settings = {"key": "MO", "projectId": "fixture"}
        model = {"instanceId": "codex", "model": "gpt-6.2-astra"}
        args = self.coordq.gate_args(settings, "shyamsivakumar/mac-ops", 543, 544,
                                     "a" * 40, False, model, prompt=True)
        self.assertIn("never auto-merges", args["message"])
        self.assertNotIn("gh pr merge", args["message"])
        code = self.coordq.gate_args(settings, "shyamsivakumar/mac-ops", 543, 544,
                                     "a" * 40, False, model)
        self.assertIn("gh pr merge 544 -R shyamsivakumar/mac-ops", code["message"])

    def gatekeep(self, changed):
        """The gate the queue's own gatekeeper would queue, for one file list."""
        import types
        from contextlib import redirect_stderr
        import io
        import json
        coordq = self.coordq
        head = self.HEAD
        repo = self.REPO
        pull = {"draft": False, "number": 7, "head": {"sha": head},
                "changed_files": len(changed), "body": f"Refs #9\nBuilder check: PASS {head}\n"}
        receipt = {"kind": "receipt", "attempt": 1, "requestId": "req-1"}
        comment = {"user": {"login": "me"},
                   "body": "attempt 1\n<!-- coordinator-ticket " + json.dumps(receipt) + " -->"}

        def fake_gh(endpoint):
            if "/files" in endpoint:
                return [{"filename": path} for path in changed]
            if endpoint.startswith(f"repos/{repo}/pulls"):
                return [dict(pull)]
            if endpoint.endswith("/comments?per_page=100"):
                return [comment]
            if endpoint.startswith(f"repos/{repo}/commits/"):
                return []
            raise AssertionError(f"unexpected endpoint {endpoint}")

        quiet = types.SimpleNamespace(returncode=0, stdout="me\n", stderr="")
        fake_subprocess = types.SimpleNamespace(run=lambda *a, **k: quiet,
                                               SubprocessError=subprocess.SubprocessError)
        with patch.object(coordq, "subprocess", fake_subprocess), \
                patch.object(coordq.gh_gateway, "run", return_value=quiet), \
                patch.object(coordq, "reviewer_model",
                             return_value={"providerInstanceId": "openai-api", "model": "openai/gpt-6.2-astra"}), \
                patch.object(coordq, "gh_json", fake_gh), \
                patch.object(coordq, "load_receipts", return_value={"req-1": "thread-1"}), \
                patch.object(coordq, "read_builder_thread",
                             return_value=({"providerInstanceId": "codex", "model": "gpt-6.2-astra"}, [])), \
                patch.object(coordq, "builder_thread_for_issue", return_value="thread-1"), \
                patch("builtins.open", side_effect=AssertionError("live filesystem forbidden")), \
                redirect_stderr(io.StringIO()):
            events = list(coordq.gate_candidates({"repos": {repo: {"key": "T", "projectId": "P"}}}))
        messages = [event["args"]["message"] for event in events if event["kind"] == "candidate"]
        self.assertEqual(len(messages), 1)
        return messages[0]

    def test_the_gatekeep_queues_a_held_gate(self):
        message = self.gatekeep(["coordinator/config/AGENT-RULES.md"])
        self.assertIn("never auto-merges", message)
        self.assertNotIn("gh pr merge", message)

    def test_the_gatekeep_queues_a_mergeable_gate_for_code(self):
        message = self.gatekeep(["coordinator/bin/ticket"])
        self.assertIn("gh pr merge 7 -R shyamsivakumar/fixture --squash", message)
        self.assertNotIn("never auto-merges", message)

    def test_an_unreadable_file_list_defers_the_gate(self):
        """No queue entry means no brief, so no merge order can be written."""
        import types
        from contextlib import redirect_stderr
        import io
        import json
        coordq = self.coordq
        head, repo = self.HEAD, self.REPO
        pull = {"draft": False, "number": 7, "head": {"sha": head},
                "changed_files": 1, "body": f"Refs #9\nBuilder check: PASS {head}\n"}
        receipt = {"kind": "receipt", "attempt": 1, "requestId": "req-1"}
        comment = {"user": {"login": "me"},
                   "body": "attempt 1\n<!-- coordinator-ticket " + json.dumps(receipt) + " -->"}

        def fake_gh(endpoint):
            if "/files" in endpoint:
                raise RuntimeError("transient GitHub error")
            if endpoint.startswith(f"repos/{repo}/pulls"):
                return [dict(pull)]
            if endpoint.endswith("/comments?per_page=100"):
                return [comment]
            if endpoint.startswith(f"repos/{repo}/commits/"):
                return []
            raise AssertionError(f"unexpected endpoint {endpoint}")

        quiet = types.SimpleNamespace(returncode=0, stdout="me\n", stderr="")
        fake_subprocess = types.SimpleNamespace(run=lambda *a, **k: quiet,
                                               SubprocessError=subprocess.SubprocessError)
        with patch.object(coordq, "subprocess", fake_subprocess), \
                patch.object(coordq.gh_gateway, "run", return_value=quiet), \
                patch.object(coordq, "reviewer_model",
                             return_value={"providerInstanceId": "openai-api", "model": "openai/gpt-6.2-astra"}), \
                patch.object(coordq, "gh_json", fake_gh), \
                patch.object(coordq, "load_receipts", return_value={"req-1": "thread-1"}), \
                patch.object(coordq, "read_builder_thread",
                             return_value=({"providerInstanceId": "codex", "model": "gpt-6.2-astra"}, [])), \
                patch.object(coordq, "builder_thread_for_issue", return_value="thread-1"), \
                patch("builtins.open", side_effect=AssertionError("live filesystem forbidden")), \
                redirect_stderr(io.StringIO()):
            events = list(coordq.gate_candidates({"repos": {repo: {"key": "T", "projectId": "P"}}}))
        self.assertEqual([event["kind"] for event in events], ["skip"])
        self.assertIn("unreadable", events[0]["reason"])


class LanePassTest(unittest.TestCase):
    """A passing prompt pull request writes one item and merges nothing."""

    def setUp(self):
        import lane_driver
        self.lane = lane_driver
        self.saved_cfg = lane_driver.CFG
        lane_driver.CFG = {"shyamsivakumar/mac-ops": {"key": "MO", "projectId": "fixture"}}
        self.addCleanup(lambda: setattr(lane_driver, "CFG", self.saved_cfg))
        self.item = self.lane.prompt_merge_item("shyamsivakumar/mac-ops", 544, "a" * 40)

    def test_the_item_is_one_action_for_shyam(self):
        self.assertEqual(self.item["id"], "prompt-merge-MO-544")
        self.assertEqual(self.item["group"], "Coordinator")
        self.assertEqual(self.item["kind"], "action")
        self.assertNotIn("options", self.item)
        self.assertIn("gh pr merge 544 -R shyamsivakumar/mac-ops", self.item["why"])

    def test_the_lane_reads_the_same_list(self):
        with patch.object(self.lane, "run", return_value='[[{"filename": "skills/x/SKILL.md"}]]'):
            self.assertEqual(self.lane.prompt_pull("shyamsivakumar/mac-ops", 544, 1),
                             prompt_paths.HOLD)
        with patch.object(self.lane, "run", return_value='[[{"filename": "coordinator/bin/ticket"}]]'):
            self.assertEqual(self.lane.prompt_pull("shyamsivakumar/mac-ops", 544, 1),
                             prompt_paths.CLEAR)

    def test_a_renamed_prompt_file_is_held(self):
        files = '[[{"filename": "archive/reviewer.md", "previous_filename": "prompts/reviewer.md"}]]'
        with patch.object(self.lane, "run", return_value=files):
            self.assertEqual(self.lane.prompt_pull("shyamsivakumar/mac-ops", 544, 1),
                             prompt_paths.HOLD)

    def test_a_missing_changed_count_defers_the_pass(self):
        """Without a count the lane cannot tell a capped list from a complete one."""
        written = []

        def command(cmd, timeout=150):
            if cmd[:2] == ["gh", "api"] and cmd[2] != "--paginate":
                self.assertEqual(cmd[2], "repos/shyamsivakumar/mac-ops/pulls/544")
                return '{"changed_files": 3001}'
            return '[{"filename": "coordinator/bin/ticket"}]'

        with patch.object(self.lane, "run", command), \
                patch.object(self.lane, "publish_decision", lambda item: written.append(item)):
            state = self.lane.prompt_pull("shyamsivakumar/mac-ops", 544)
            held = self.lane.prompt_pass("shyamsivakumar/mac-ops", 544, "a" * 40, state)
        self.assertEqual(state, prompt_paths.UNKNOWN)
        self.assertIn("next run retries", held)
        self.assertEqual(written, [])

    def test_an_unreadable_list_defers_the_pass(self):
        """A list the lane cannot read is retried, then merged nothing on."""
        written = []
        with patch.object(self.lane, "run", side_effect=RuntimeError("boom")), \
                patch.object(self.lane, "publish_decision", lambda item: written.append(item)):
            state = self.lane.prompt_pull("shyamsivakumar/mac-ops", 544, 1)
            held = self.lane.prompt_pass("shyamsivakumar/mac-ops", 544, "a" * 40, state)
        self.assertEqual(state, prompt_paths.UNKNOWN)
        self.assertIn("could not be read", held)
        self.assertIn("next run retries", held)
        self.assertEqual(written, [])

    def test_a_truncated_list_defers_the_pass(self):
        """A short list may have hidden the prompt file, so it is no list."""
        written = []
        with patch.object(self.lane, "run",
                          return_value='[[{"filename": "coordinator/bin/ticket"}]]'), \
                patch.object(self.lane, "publish_decision", lambda item: written.append(item)):
            state = self.lane.prompt_pull("shyamsivakumar/mac-ops", 544, 3001)
            held = self.lane.prompt_pass("shyamsivakumar/mac-ops", 544, "a" * 40, state)
        self.assertEqual(state, prompt_paths.UNKNOWN)
        self.assertIn("could not be read", held)
        self.assertEqual(written, [])

    def test_a_complete_list_of_code_is_clear(self):
        with patch.object(self.lane, "run",
                          return_value='[[{"filename": "coordinator/bin/ticket"}]]'):
            self.assertEqual(self.lane.prompt_pull("shyamsivakumar/mac-ops", 544, 1),
                             prompt_paths.CLEAR)

    def test_a_multi_page_list_holds_its_prompt_file(self):
        """A 101-file PR arrives as two pages, and page 2 still counts."""
        pages = ('[[{"filename": "coordinator/bin/ticket"}],'
                 ' [{"filename": "prompts/reviewer.md"}]]')
        with patch.object(self.lane, "run", return_value=pages):
            self.assertEqual(self.lane.prompt_pull("shyamsivakumar/mac-ops", 544, 2),
                             prompt_paths.HOLD)
        with patch.object(self.lane, "run",
                          return_value='[[{"filename": "coordinator/bin/ticket"}],'
                                       ' [{"filename": "docs/ticket-gate.md"}]]'):
            self.assertEqual(self.lane.prompt_pull("shyamsivakumar/mac-ops", 544, 2),
                             prompt_paths.CLEAR)

    def test_a_huge_code_pull_request_merges_through_the_trees(self):
        """A 3,001-file PR of code must still merge, not defers for ever."""

        def command(cmd, timeout=150):
            endpoint = cmd[-1]
            if "/files?per_page=100" in endpoint:
                return '[[{"filename": "coordinator/bin/ticket"}]]'
            if "/compare/" in endpoint:
                return '{"merge_base_commit": {"sha": "base"}}'
            if endpoint.endswith("/git/trees/base?recursive=1"):
                return '{"tree": [{"type": "blob", "path": "a.py", "sha": "1"}]}'
            if endpoint.endswith("/git/trees/head?recursive=1"):
                return '{"tree": [{"type": "blob", "path": "a.py", "sha": "2"}]}'
            raise AssertionError(cmd)

        with patch.object(self.lane, "run", command), \
                patch.object(self.lane, "pr_changed_count", return_value=3001):
            self.assertEqual(self.lane.prompt_pull("shyamsivakumar/mac-ops", 544,
                                                   base="main", head="head"),
                             prompt_paths.CLEAR)

    def test_a_timeout_defers_the_pass(self):
        import subprocess as real_subprocess
        written = []
        with patch.object(self.lane, "run",
                          side_effect=real_subprocess.TimeoutExpired("gh api", 40)), \
                patch.object(self.lane, "publish_decision", lambda item: written.append(item)):
            state = self.lane.prompt_pull("shyamsivakumar/mac-ops", 544, 1)
            held = self.lane.prompt_pass("shyamsivakumar/mac-ops", 544, "a" * 40, state)
        self.assertEqual(state, prompt_paths.UNKNOWN)
        self.assertIn("next run retries", held)
        self.assertEqual(written, [])

    def test_a_dry_run_writes_no_board_item(self):
        """The board write is live state, so a dry run must not reach it."""
        written = []
        with patch.object(self.lane, "DRY", True), \
                patch.object(self.lane, "publish_decision", lambda item: written.append(item)):
            held = self.lane.prompt_pass("shyamsivakumar/mac-ops", 544, "a" * 40,
                                         prompt_paths.HOLD)
        self.assertEqual(held, "DRY hold #544 " + "a" * 40)
        self.assertEqual(written, [])

    def test_a_code_pull_request_merges(self):
        with patch.object(self.lane, "publish_decision",
                          side_effect=AssertionError("a code pass writes no board item")):
            self.assertIsNone(self.lane.prompt_pass("shyamsivakumar/mac-ops", 544,
                                                    "a" * 40, prompt_paths.CLEAR))

    def test_a_failed_board_write_is_not_a_merge_ask(self):
        with patch.object(self.lane, "DRY", False), \
                patch.object(self.lane, "publish_decision", return_value="failed"):
            held = self.lane.prompt_pass("shyamsivakumar/mac-ops", 544, "a" * 40,
                                         prompt_paths.HOLD)
        self.assertIn("could not be written", held)
        self.assertNotIn("Shyam merges", held)

    def test_it_publishes_under_the_board_lock(self):
        calls = []

        def board_update(path, alarm_id, action, item=None, attempts=5):
            calls.append((path, alarm_id, action, item))
            return "wrote"

        with patch.object(self.lane.alarms, "board_update", board_update):
            self.assertEqual(self.lane.publish_decision(self.item), "wrote")
        self.assertEqual(calls, [(self.lane.DECISIONS_PATH, "prompt-merge-MO-544", "raise", self.item)])


class BoardReconcileTest(unittest.TestCase):
    """A merge ask for a settled pull request is taken down."""

    def setUp(self):
        import lane_driver
        self.lane = lane_driver
        self.saved_cfg = lane_driver.CFG
        lane_driver.CFG = {"shyamsivakumar/mac-ops": {"key": "MO", "projectId": "fixture"}}
        self.addCleanup(lambda: setattr(lane_driver, "CFG", self.saved_cfg))
        self.board = {"items": [{"id": "prompt-merge-MO-544"},
                                {"id": "prompt-merge-MO-545"},
                                {"id": "prompt-merge-MO-546"},
                                {"id": "unrelated"}]}
        self.snapshot = {"repos": {"shyamsivakumar/mac-ops": {"prs": [{"number": 545}]}}}

    def reconcile(self, states=None, removed_writes=("wrote",), read_error=None):
        taken = []
        # 544 is merged, 546 is still open but fell outside the capped list.
        by_number = states or {544: {"state": "MERGED", "mergedAt": "2026-11-18T00:00:00Z"},
                               546: {"state": "OPEN", "mergedAt": None}}

        def read(cmd, timeout=150):
            if read_error is not None:
                raise read_error
            return json.dumps(by_number[int(cmd[3])])

        def withdraw(item_id):
            taken.append(item_id)
            return removed_writes[0]

        with patch.object(self.lane, "run", read), \
                patch.object(self.lane.alarms, "read_board", return_value=(b"", self.board)), \
                patch.object(self.lane, "withdraw_decision", withdraw):
            removed = self.lane.reconcile_prompt_items(self.snapshot)
        return removed, taken

    def test_a_merged_prompt_request_is_taken_down(self):
        """The pull request's own state says it is settled."""
        removed, taken = self.reconcile()
        self.assertEqual(taken, ["prompt-merge-MO-544"])
        self.assertEqual(removed, 1)

    def test_a_closed_prompt_request_is_taken_down(self):
        removed, taken = self.reconcile(
            states={544: {"state": "CLOSED", "mergedAt": None},
                    546: {"state": "CLOSED", "mergedAt": None}})
        self.assertEqual(taken, ["prompt-merge-MO-544", "prompt-merge-MO-546"])
        self.assertEqual(removed, 2)

    def test_an_open_request_outside_the_capped_list_stays(self):
        """Absence from a 200-row snapshot is not proof of closure."""
        removed, taken = self.reconcile()
        self.assertNotIn("prompt-merge-MO-546", taken)
        self.assertEqual(removed, 1)

    def test_an_unread_state_leaves_the_card(self):
        """A state that did not come back is not a closed pull request."""
        removed, taken = self.reconcile(read_error=RuntimeError("gh failed"))
        self.assertEqual((removed, taken), (0, []))

    def test_an_open_prompt_request_stays(self):
        self.assertNotIn("prompt-merge-MO-545", self.reconcile()[1])

    def test_someone_elses_item_is_left_alone(self):
        self.assertNotIn("unrelated", self.reconcile()[1])

    def test_a_dry_run_takes_nothing_down(self):
        with patch.object(self.lane, "DRY", True):
            removed, taken = self.reconcile()
        self.assertEqual((removed, taken), (0, []))

    def test_an_unreadable_board_is_not_an_error(self):
        with patch.object(self.lane.alarms, "read_board", return_value=(b"", None)):
            self.assertEqual(self.lane.reconcile_prompt_items(self.snapshot), 0)


class LandedBaseTest(unittest.TestCase):
    """A merge that landed on another base reaches Shyam as a board item."""

    def setUp(self):
        import lane_driver
        self.lane = lane_driver
        self.saved = lane_driver.CFG
        lane_driver.CFG = {"shyamsivakumar/mac-ops": {"key": "MO", "projectId": "fixture"}}
        self.addCleanup(lambda: setattr(lane_driver, "CFG", self.saved))

    def merge(self, landed):
        published = []

        def command(cmd, timeout=150):
            if cmd[:2] == ["gh", "pr"] and "view" in cmd:
                if any("headRefOid" in str(part) for part in cmd):
                    return '{"baseRefName": "main", "headRefOid": "%s"}' % ("a" * 40)
                return '{"baseRefName": "%s"}' % landed
            return ""

        with patch.object(self.lane, "run", command), \
                patch.object(self.lane, "publish_decision",
                             lambda item: (published.append(item), "wrote")[1]):
            merged, note = self.lane.merge_on_reviewed_base(
                "shyamsivakumar/mac-ops", 544, "a" * 40, "main")
        return merged, note, published

    def test_a_merge_that_landed_on_the_reviewed_base_stands(self):
        merged, note, published = self.merge("main")
        self.assertTrue(merged)
        self.assertEqual(published, [])
        self.assertEqual(note, "#544: merged " + "a" * 40)

    def test_a_merge_that_landed_elsewhere_reaches_shyam(self):
        merged, note, published = self.merge("release/next")
        self.assertFalse(merged)
        self.assertIn("critical", note)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["id"], "base-moved-MO-544")
        self.assertEqual(published[0]["kind"], "action")
        self.assertIn("release/next", published[0]["title"])


class MergeBaseGuardTest(unittest.TestCase):
    """A pull request is merged only when its base is still the reviewed one."""

    def setUp(self):
        import lane_driver
        self.lane = lane_driver
        self.saved = lane_driver.CFG
        lane_driver.CFG = {"shyamsivakumar/mac-ops": {"key": "MO", "projectId": "fixture"}}
        self.addCleanup(lambda: setattr(lane_driver, "CFG", self.saved))

    def merge(self, base_after):
        calls = []

        def command(cmd, timeout=150):
            calls.append(cmd)
            if cmd[:2] == ["gh", "pr"] and "view" in cmd and any(
                    "baseRefName" in str(part) for part in cmd):
                return '{"baseRefName": "%s", "headRefOid": "%s"}' % (base_after, "a" * 40)
            return ""

        with patch.object(self.lane, "run", command):
            merged, note = self.lane.merge_on_reviewed_base(
                "shyamsivakumar/mac-ops", 544, "a" * 40, "main")
        return merged, note, calls

    def test_a_merge_on_the_reviewed_base_is_issued(self):
        merged, note, calls = self.merge("main")
        self.assertTrue(merged)
        self.assertEqual(note, "#544: merged " + "a" * 40)
        self.assertEqual(len([c for c in calls if c[:3] == ["gh", "pr", "merge"]]), 1)

    def test_a_moved_base_merges_nothing(self):
        """The merge cannot enforce the base, so a moved base is refused."""
        merged, note, calls = self.merge("release/next")
        self.assertFalse(merged)
        self.assertIn("nothing merged", note)
        self.assertEqual([c for c in calls if c[:3] == ["gh", "pr", "merge"]], [])

    def test_a_moved_base_reverts_nothing(self):
        """No merge is issued, so there is nothing to take back."""
        merged, _note, calls = self.merge("release/next")
        self.assertFalse(merged)
        self.assertEqual([c for c in calls if "revert" in " ".join(c)], [])

    def test_a_retarget_after_the_merge_is_reported_not_merged(self):
        """A base that moves in the merge call cannot be refused, so it is read again.

        No `gh` call pins the base, so the pre-merge read covers only the
        interval before it. A pull request that lands on another base is
        reported as one, and the caller closes and fast-forwards nothing.
        """
        calls = []
        base = {"now": "main"}

        def command(cmd, timeout=150):
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "merge"]:
                base["now"] = "release/next"
                return ""
            if cmd[:2] == ["gh", "pr"] and "view" in cmd and any(
                    "baseRefName" in str(part) for part in cmd):
                return '{"baseRefName": "%s", "headRefOid": "%s"}' % (base["now"], "a" * 40)
            return ""

        published = []
        with patch.object(self.lane, "run", command), \
                patch.object(self.lane, "publish_decision",
                             lambda item: (published.append(item), "wrote")[1]):
            merged, note = self.lane.merge_on_reviewed_base(
                "shyamsivakumar/mac-ops", 544, "a" * 40, "main")
        self.assertFalse(merged)
        self.assertIn("not the reviewed main", note)
        self.assertEqual([item["id"] for item in published], ["base-moved-MO-544"])
        self.assertEqual(len([c for c in calls if c[:3] == ["gh", "pr", "merge"]]), 1)

    def test_the_base_is_read_before_and_after_the_merge(self):
        """One read guards the interval before the merge, one the merge itself."""
        _merged, _note, calls = self.merge("main")
        views = [c for c in calls if c[:2] == ["gh", "pr"] and "view" in c]
        self.assertEqual(len(views), 2)
        merge_at = next(i for i, c in enumerate(calls) if c[:3] == ["gh", "pr", "merge"])
        self.assertLess(calls.index(views[0]), merge_at)
        self.assertGreater(calls.index(views[1]), merge_at)


class BaseScopeTest(unittest.TestCase):
    """The classification reads the pull request's own base and nothing else."""

    def test_a_prompt_change_against_the_own_base_holds(self):
        import lane_driver

        def fetch(endpoint):
            if "/compare/" in endpoint:
                return {"merge_base_commit": {"sha": "base"}}
            if endpoint.endswith("/git/trees/base?recursive=1"):
                return {"tree": [{"type": "blob", "path": "a.py", "mode": "100644", "sha": "1"}]}
            return {"tree": [{"type": "blob", "path": "skills/x/SKILL.md",
                              "mode": "100644", "sha": "2"}]}

        with patch.object(lane_driver, "api_json", fetch):
            self.assertEqual(lane_driver.prompt_pull("o/r", 544, base="feature", head="head"),
                             prompt_paths.HOLD)

    def test_an_inherited_prompt_change_does_not_hold_code_work(self):
        """A feature branch's own prompt edit is not the child's change."""
        import lane_driver

        def fetch(endpoint):
            if "/compare/" in endpoint:
                return {"merge_base_commit": {"sha": "base"}}
            if endpoint.endswith("/git/trees/base?recursive=1"):
                return {"tree": [{"type": "blob", "path": "skills/x/SKILL.md",
                                  "mode": "100644", "sha": "2"}]}
            return {"tree": [{"type": "blob", "path": "skills/x/SKILL.md",
                              "mode": "100644", "sha": "2"},
                             {"type": "blob", "path": "a.py", "mode": "100644", "sha": "3"}]}

        with patch.object(lane_driver, "api_json", fetch):
            self.assertEqual(lane_driver.prompt_pull("o/r", 544, base="feature", head="head"),
                             prompt_paths.CLEAR)
