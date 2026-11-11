"""Regression coverage for worktree bases without starting the hub process."""

import ast
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "empryo/bin/emp-hub"


def load_worktree_functions():
    tree = ast.parse(SOURCE.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"git", "create_worktree", "remote_default_branch", "worktree_for_branch", "advance_branch"}]
    namespace = {"os": os, "subprocess": subprocess, "HubError": type("HubError", (Exception,), {}), "slugify": lambda value: value, "WORKTREES": "unused"}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class FreshWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.writer = self.root / "writer"
        self.checkout = self.root / "checkout"
        self.run_git("init", "--bare", "--initial-branch=main", str(self.remote))
        self.run_git("clone", str(self.remote), str(self.writer))
        self.commit()
        self.run_git("-C", str(self.writer), "push", "origin", "main")
        self.run_git("clone", str(self.remote), str(self.checkout))
        self.commit()
        self.run_git("-C", str(self.writer), "push", "origin", "main")
        self.tip = self.run_git("-C", str(self.writer), "rev-parse", "HEAD")
        self.first = self.run_git("-C", str(self.writer), "rev-parse", "HEAD~1")
        self.hub = load_worktree_functions()

    def run_git(self, *args):
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()

    def commit(self):
        self.run_git("-C", str(self.writer), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-m", "test")

    def create(self, name, base=None):
        strategy = {"type": "worktree", "branch": name, "worktreePath": str(self.root / name)}
        if base is not None:
            strategy["baseRef"] = base
        return self.hub["create_worktree"]({"workspaceRoot": str(self.checkout), "title": "project"}, "emp:123456", "task", strategy)

    def test_fresh_default_and_explicit_bases(self):
        for name, base in (("absent", None), ("head", "HEAD"), ("origin-head", "origin/HEAD"), ("remote", "origin/main"), ("plain", "main")):
            with self.subTest(base=base):
                # Reset the tracking ref to simulate a checkout that has not fetched the new tip.
                self.run_git("-C", str(self.checkout), "update-ref", "refs/remotes/origin/main", self.first)
                path, _ = self.create(name, base)
                self.assertEqual(self.run_git("-C", path, "rev-parse", "HEAD"), self.tip)

    def test_fetch_failure_does_not_create_worktree(self):
        self.run_git("-C", str(self.checkout), "remote", "set-url", "origin", str(self.root / "missing"))
        with self.assertRaisesRegex(self.hub["HubError"], "git fetch origin.*failed"):
            self.create("failed", "main")
        self.assertFalse((self.root / "failed").exists())

    def test_existing_branch_without_worktree_is_reused(self):
        self.run_git("-C", str(self.checkout), "branch", "old", self.first)
        path, branch = self.create("old", "main")
        self.assertEqual(branch, "old")
        self.assertEqual(self.run_git("-C", path, "rev-parse", "HEAD"), self.tip)

    def test_existing_branch_keeps_its_own_commits(self):
        self.run_git("-C", str(self.checkout), "checkout", "-b", "wip", self.first)
        self.run_git("-C", str(self.checkout), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-m", "work")
        wip = self.run_git("-C", str(self.checkout), "rev-parse", "HEAD")
        self.run_git("-C", str(self.checkout), "checkout", "main")
        path, _ = self.create("wip", "main")
        self.assertEqual(self.run_git("-C", path, "rev-parse", "HEAD"), wip)

    def test_existing_branch_checked_out_elsewhere_is_refused(self):
        self.run_git("-C", str(self.checkout), "branch", "busy", self.first)
        self.run_git("-C", str(self.checkout), "worktree", "add", str(self.root / "busy-here"), "busy")
        with self.assertRaisesRegex(self.hub["HubError"], "already checked out at"):
            self.create("busy", "main")


if __name__ == "__main__":
    unittest.main()
