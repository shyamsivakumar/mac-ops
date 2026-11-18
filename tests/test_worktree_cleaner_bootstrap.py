"""MO-514: the cleaner must never treat a worktree with real work as bootstrap.

Each test here is one of the cases the gate reported:

- the status keeps its columns, so an unstaged edit to ``x.specstory/notes``
  is not read as ``.specstory/notes``;
- the ``AGENTS.md`` check compares file contents, so a genuine line that
  begins with ``++`` cannot hide behind the rules block.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLEANER = ROOT / "scripts/worktree-cleaner/cleaner.py"
RULES = ROOT / "coordinator/config/AGENT-RULES.md"


def load_cleaner():
    spec = importlib.util.spec_from_file_location("worktree_cleaner", CLEANER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cleaner = load_cleaner()


def git_bytes(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=True
    ).stdout


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def commit(repo: Path, name: str, content: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(repo, "add", name)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
            "commit", "-m", name,
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def agents_bootstrap(repo: Path) -> bool:
    """Call the cleaner across its signature changes."""
    try:
        return cleaner.agents_only_rules(repo)
    except TypeError:
        return cleaner.agents_only_rules(repo, untracked=False)


class StatusColumnsTest(unittest.TestCase):
    def test_status_keeps_columns_and_paths(self):
        with tempfile.TemporaryDirectory(prefix="mo514-status-") as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            git(repo, "init", "-b", "main")
            git(repo, "config", "user.name", "Fixture")
            git(repo, "config", "user.email", "fixture@example.test")
            commit(repo, "x.specstory/notes", "notes\n")
            (repo / "x.specstory" / "notes").write_text("edited\n", encoding="utf-8")
            records = cleaner.status_for(repo)
            self.assertEqual([(code, name) for code, name, _original in records], [(" M", "x.specstory/notes")])
            bootstrap, real = cleaner.classify_changes(repo, records)
            self.assertEqual(bootstrap, [])
            self.assertEqual(real, ["x.specstory/notes"])
            self.assertIsNone(cleaner.clear_bootstrap_changes(repo, records))


class AgentsBootstrapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mo514-agents-")
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@example.test")
        commit(self.repo, "AGENTS.md", "# Repository rules\n\n")
        self.block = RULES.read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def append(self, text: str) -> None:
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(text)

    def test_exact_block_is_bootstrap(self):
        self.append(self.block)
        self.assertTrue(agents_bootstrap(self.repo))

    def test_block_plus_genuine_line_is_real_work(self):
        self.append(self.block + "++ genuine edit\n")
        self.assertFalse(agents_bootstrap(self.repo))

    def test_single_rule_is_real_work(self):
        self.append("- CI is agent checks only: no Woodpecker, no GitHub Actions.\n")
        self.assertFalse(agents_bootstrap(self.repo))

    def test_genuine_line_before_block_is_real_work(self):
        self.append("++ genuine edit\n" + self.block)
        self.assertFalse(agents_bootstrap(self.repo))

    def test_user_heading_between_file_and_block_is_real_work(self):
        self.append("# My own heading\n" + self.block)
        self.assertFalse(agents_bootstrap(self.repo))

    def test_staged_genuine_edit_is_real_work(self):
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write("genuine edit\n")
        git(self.repo, "add", "AGENTS.md")
        head = git(self.repo, "show", "HEAD:AGENTS.md")
        with (self.repo / "AGENTS.md").open("w", encoding="utf-8") as handle:
            handle.write(head + self.block)
        self.assertFalse(agents_bootstrap(self.repo))

    def test_mode_change_is_real_work(self):
        self.append(self.block)
        os.chmod(self.repo / "AGENTS.md", 0o755)
        self.assertFalse(agents_bootstrap(self.repo))

    def test_staged_mode_change_is_real_work(self):
        self.append(self.block)
        git(self.repo, "update-index", "--chmod=+x", "AGENTS.md")
        self.assertFalse(agents_bootstrap(self.repo))

    def test_removed_trailing_newline_is_real_work(self):
        # The committed file ends in two newlines. Removing one of them and
        # appending the block is an edit, not the bootstrap.
        head = git_bytes(self.repo, "show", "HEAD:AGENTS.md")
        self.assertTrue(head.endswith(b"\n\n"))
        with (self.repo / "AGENTS.md").open("wb") as handle:
            handle.write(head.rstrip(b"\n") + b"\n" + self.block.encode("utf-8"))
        self.assertFalse(agents_bootstrap(self.repo))

    def test_line_ending_change_is_real_work(self):
        head = git_bytes(self.repo, "show", "HEAD:AGENTS.md")
        with (self.repo / "AGENTS.md").open("wb") as handle:
            handle.write(head.replace(b"\n", b"\r\n") + self.block.encode("utf-8"))
        self.assertFalse(agents_bootstrap(self.repo))


    def test_untracked_symlink_agents_file_is_real_work(self):
        # An untracked AGENTS.md that is a symlink to a rules file must not
        # be read through the link and accepted as the bootstrap.
        target = self.repo / "rules-copy.md"
        target.write_bytes(self.block.encode("utf-8"))
        link = self.repo / "AGENTS.md"
        if link.exists():
            link.unlink()
        link.symlink_to(target)
        self.assertFalse(agents_bootstrap(self.repo))

    def test_untracked_executable_agents_file_is_real_work(self):
        link = self.repo / "AGENTS.md"
        if link.exists():
            link.unlink()
        link.write_bytes(self.block.encode("utf-8"))
        os.chmod(link, 0o755)
        self.assertFalse(agents_bootstrap(self.repo))


class ClearBootstrapChangesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mo514-clear-")
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@example.test")
        commit(self.repo, "AGENTS.md", "# Repository rules\n\n")
        self.block = RULES.read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_bootstrap_changes_are_cleared(self):
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        (self.repo / ".specstory").mkdir()
        (self.repo / ".specstory" / "session.md").write_text("history\n", encoding="utf-8")
        records = cleaner.status_for(self.repo)
        cleared = cleaner.clear_bootstrap_changes(self.repo, records)
        self.assertEqual(sorted(cleared or []), [".specstory/session.md", "AGENTS.md"])
        self.assertFalse((self.repo / ".specstory" / "session.md").exists())
        self.assertEqual(cleaner.status_for(self.repo), [])

    def test_a_real_change_is_never_cleared(self):
        (self.repo / "notes.txt").write_text("real work\n", encoding="utf-8")
        records = cleaner.status_for(self.repo)
        self.assertIsNone(cleaner.clear_bootstrap_changes(self.repo, records))
        self.assertTrue((self.repo / "notes.txt").exists())


class DefaultBranchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mo514-default-")
        base = Path(self.tmp.name)
        self.repo = base / "repo"
        self.remote = base / "remote.git"
        self.remote.mkdir()
        self.repo.mkdir()
        subprocess.run(["git", "init", "--bare", str(self.remote)], capture_output=True, check=True)
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@example.test")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        commit(self.repo, "base.txt", "base\n")
        git(self.repo, "push", "-u", "origin", "main")
        git(self.repo, "checkout", "-b", "master")
        commit(self.repo, "master-only.txt", "master\n")
        self.master_head = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "push", "origin", "master")
        git(self.repo, "fetch", "origin")
        git(self.repo, "checkout", "main")
        git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ancestry_is_decided_by_github(self):
        github = cleaner.GitHub()
        github.default_branch = lambda repo: "main"
        github.contains = lambda repo, base, head: head == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        row = {"head": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "unpushed": 0, "remote_commit_present": True}
        self.assertTrue(cleaner.published_on_default_branch(row, github, "fixture/repo"))
        stale = {"head": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "unpushed": 0, "remote_commit_present": True}
        self.assertFalse(cleaner.published_on_default_branch(stale, github, "fixture/repo"))

    def test_unverified_default_branch_grants_nothing(self):
        github = cleaner.GitHub()
        github.default_branch = lambda repo: None
        github.contains = lambda repo, base, head: True
        row = {"head": self.master_head, "unpushed": 0, "remote_commit_present": True}
        self.assertFalse(cleaner.published_on_default_branch(row, github, "fixture/repo"))

    def test_valid_branch_names_are_accepted(self):
        if not hasattr(cleaner, "valid_branch_name"):
            self.fail("the cleaner rejects valid branch names")
        self.assertTrue(cleaner.valid_branch_name("main"))
        self.assertTrue(cleaner.valid_branch_name("release/main"))
        self.assertTrue(cleaner.valid_branch_name("release-1.2"))
        self.assertTrue(cleaner.valid_branch_name("release/\u00e9t\u00e9"))
        self.assertFalse(cleaner.valid_branch_name(""))
        self.assertFalse(cleaner.valid_branch_name("bad name"))
        self.assertFalse(cleaner.valid_branch_name("bad..name"))
        self.assertFalse(cleaner.valid_branch_name("/leading"))
        self.assertFalse(cleaner.valid_branch_name("trailing/"))
        self.assertFalse(cleaner.valid_branch_name("name.lock"))
        github = cleaner.GitHub()
        github.default_branch = lambda repo: "release/main"
        self.assertEqual(github.default_branch("fixture/repo"), "release/main")


if __name__ == "__main__":
    unittest.main()
