"""Gate regressions: until atomic hub coordination exists, removal is disabled."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/worktree-cleaner/cleaner.py"
spec = importlib.util.spec_from_file_location("gate_cleaner", SCRIPT)
cleaner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleaner)


class GateSafety(unittest.TestCase):
    def held_scan(self, reason):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree = root / "tree"
            tree.mkdir()
            (tree / "ignored-unsaved.txt").write_text("user work")
            row = {"repo": str(root), "path": str(tree), "branch": "task", "head": "a" * 40,
                   "main_checkout": False, "eligible": True, "prunable": True, "reasons": [],
                   "dirty": False, "remote_commit_present": True, "empryo_threads": []}
            with mock.patch.object(cleaner, "EmpryoState") as state, \
                 mock.patch.object(cleaner, "GitHub"), \
                 mock.patch.object(cleaner, "discover_repositories", return_value=[root]), \
                 mock.patch.object(cleaner, "discover_hub_repositories", return_value=[]), \
                 mock.patch.object(cleaner, "inventory", return_value=[row]), \
                 mock.patch.object(cleaner, "run", side_effect=AssertionError("unexpected command")):
                state.return_value.thread_count = 0
                state.return_value.unfinished_count = 0
                state.return_value.page_count = 0
                result = cleaner.scan(root, root / "hub", root / "state", True, False, True)
            self.assertEqual(result["removed"], 0, reason)
            self.assertEqual(result["pruned"], 0, reason)
            self.assertIn("removal_disabled_no_hub_lease", row["reasons"])
            self.assertEqual((tree / "ignored-unsaved.txt").read_text(), "user work")

    def test_ignored_unsaved_work(self):
        self.held_scan("ignored files")

    def test_thread_starts_after_snapshot(self):
        self.held_scan("thread start is uncoordinated")

    def test_archived_unfinished_thread(self):
        self.held_scan("archived thread not listed")

    def test_partial_github_failure(self):
        self.held_scan("partial GitHub failure")

    def test_external_hub_owner_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, hub = root / "outside" / "repo", root / "hub"
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "--allow-empty", "-qm", "base"], check=True)
            subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach", str(hub / "project" / "task")], check=True, capture_output=True)
            self.assertIn(Path(cleaner.canonical(repo)), cleaner.discover_hub_repositories(hub))

    def test_interval_exists_but_not_installed(self):
        import plistlib
        plist = SCRIPT.parent / "com.shyam.worktree-cleaner.plist"
        self.assertEqual(plistlib.loads(plist.read_bytes())["StartInterval"], 900)
        self.held_scan("installation not authorized")


if __name__ == "__main__":
    unittest.main()
