"""MO-514: the cleaner must never treat a worktree with real work as bootstrap.

Each test here is one of the cases the gate reported:

- the status keeps its columns, so an unstaged edit to ``x.specstory/notes``
  is not read as ``.specstory/notes``;
- the ``AGENTS.md`` check compares file contents, so a genuine line that
  begins with ``++`` cannot hide behind the rules block.
"""
from __future__ import annotations

import importlib.util
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
            self.assertEqual(cleaner.removal_force_flags(repo, records), [])


class AgentsBootstrapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mo514-agents-")
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@example.test")
        commit(self.repo, "AGENTS.md", "# Repository rules\n")
        self.block = RULES.read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def append(self, text: str) -> None:
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(text)

    def test_exact_block_is_bootstrap(self):
        self.append(self.block)
        self.assertTrue(cleaner.agents_only_rules(self.repo, untracked=False))

    def test_block_plus_genuine_line_is_real_work(self):
        self.append(self.block + "++ genuine edit\n")
        self.assertFalse(cleaner.agents_only_rules(self.repo, untracked=False))

    def test_single_rule_is_real_work(self):
        self.append("- CI is agent checks only: no Woodpecker, no GitHub Actions.\n")
        self.assertFalse(cleaner.agents_only_rules(self.repo, untracked=False))

    def test_genuine_line_before_block_is_real_work(self):
        self.append("++ genuine edit\n" + self.block)
        self.assertFalse(cleaner.agents_only_rules(self.repo, untracked=False))

    def test_user_heading_between_file_and_block_is_real_work(self):
        self.append("# My own heading\n" + self.block)
        self.assertFalse(cleaner.agents_only_rules(self.repo, untracked=False))

    def test_staged_genuine_edit_is_real_work(self):
        # A genuine edit is staged, and the working copy holds only the
        # committed file plus the rules block. The staged edit is real work.
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write("genuine edit\n")
        git(self.repo, "add", "AGENTS.md")
        head = git(self.repo, "show", "HEAD:AGENTS.md")
        with (self.repo / "AGENTS.md").open("w", encoding="utf-8") as handle:
            handle.write(head + self.block)
        self.assertFalse(cleaner.agents_only_rules(self.repo, untracked=False))


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

    def test_only_the_default_branch_qualifies(self):
        github = cleaner.GitHub()
        github.default_branch = lambda repo: None
        refs = cleaner.default_branch_refs(self.repo, github, "fixture/repo")
        self.assertEqual(refs, ["refs/remotes/origin/main"])
        self.assertFalse(cleaner.on_default_branch(self.repo, self.master_head, refs))
        self.assertTrue(cleaner.on_default_branch(self.repo, self.master_head, ["refs/remotes/origin/master"]))
        main_head = git(self.repo, "rev-parse", "main")
        self.assertTrue(cleaner.on_default_branch(self.repo, main_head, refs))


if __name__ == "__main__":
    unittest.main()
