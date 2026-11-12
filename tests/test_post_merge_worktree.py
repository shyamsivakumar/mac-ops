import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("post_merge", ROOT / "coordinator/bin/post_merge.py")
post = importlib.util.module_from_spec(spec)
spec.loader.exec_module(post)


class PostMergeWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.remote = self.home / "remote.git"
        self.clone = self.home / "Code" / "example"
        self.clone.parent.mkdir(parents=True)
        self.git(self.home, "init", "--bare", str(self.remote))
        self.git(self.home, "clone", str(self.remote), str(self.clone))
        self.git(self.clone, "checkout", "-b", "main")
        self.git(self.clone, "config", "user.email", "test@example.org")
        self.git(self.clone, "config", "user.name", "Test")
        (self.clone / "file").write_text("initial")
        self.git(self.clone, "add", "file")
        self.git(self.clone, "commit", "-m", "initial")
        self.git(self.clone, "push", str(self.remote), "main")
        self.git(self.clone, "remote", "set-url", "origin", "https://github.com/test/example.git")
        self.git(self.clone, "config", "url." + str(self.remote) + ".insteadOf", "https://github.com/test/example.git")
        self.other = self.home / "other"
        self.git(self.home, "clone", "-b", "main", str(self.remote), str(self.other))
        self.git(self.other, "config", "user.email", "test@example.org")
        self.git(self.other, "config", "user.name", "Test")
        (self.other / "file").write_text("remote")
        self.git(self.other, "commit", "-am", "remote")
        self.git(self.other, "push", str(self.remote), "main")
        # The clone keeps its own branch and its own local work; the live main
        # checkout is a linked worktree that shares the clone's metadata.
        self.git(self.clone, "checkout", "-b", "work/607")
        (self.clone / "local").write_text("local")
        self.worktree = self.home / "Code" / "example-main"
        self.git(self.clone, "worktree", "add", str(self.worktree), "main")
        self.config = self.home / ".coordinator" / "post-merge.json"
        self.config.parent.mkdir(parents=True, exist_ok=True)

    def git(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()

    def write_config(self, **entry):
        self.config.write_text(json.dumps({"test/example": entry}))

    def run_post(self, base="main"):
        return post.post_merge("test/example", base, self.home, str(self.config))

    def test_a_linked_worktree_is_fast_forwarded(self):
        self.write_config(checkout="example-main")
        result = self.run_post()
        self.assertEqual(result["fastForward"]["status"], "ok")
        self.assertEqual(result["status"], "ok")
        self.assertEqual((self.worktree / "file").read_text(), "remote")

    def test_the_fast_forward_leaves_the_clone_it_shares_with_untouched(self):
        self.write_config(checkout="example-main")
        branch = self.git(self.clone, "branch", "--show-current")
        status = self.git(self.clone, "status", "--porcelain", "--untracked-files=all")
        result = self.run_post()
        self.assertEqual(result["fastForward"]["status"], "ok")
        self.assertEqual(self.git(self.clone, "branch", "--show-current"), branch)
        self.assertEqual(self.git(self.clone, "status", "--porcelain", "--untracked-files=all"), status)
        self.assertEqual((self.clone / "local").read_text(), "local")

    def test_a_worktree_with_local_changes_is_skipped(self):
        self.write_config(checkout="example-main")
        (self.worktree / "file").write_text("local")
        result = self.run_post()
        self.assertEqual(result["fastForward"]["status"], "skipped")
        self.assertIn("local changes", result["reason"])
        self.assertEqual((self.worktree / "file").read_text(), "local")

    def test_a_directory_without_git_metadata_is_skipped(self):
        (self.home / "Code" / "plain").mkdir()
        self.write_config(checkout="plain")
        result = self.run_post()
        self.assertEqual(result["fastForward"]["status"], "skipped")
        self.assertIn("no checkout at", result["reason"])


if __name__ == "__main__":
    unittest.main()
