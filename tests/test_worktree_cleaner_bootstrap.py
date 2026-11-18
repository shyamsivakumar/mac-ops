"""MO-514: the cleaner must never treat a worktree with real work as bootstrap.

Each test here is one of the cases the gate reported:

- the status keeps its columns, so an unstaged edit to ``x.specstory/notes``
  is not read as ``.specstory/notes``;
- the ``AGENTS.md`` check compares file contents, so a genuine line that
  begins with ``++`` cannot hide behind the rules block.
"""
from __future__ import annotations

import importlib.util
import json
import os
from unittest import mock
from pathlib import Path
import subprocess
import time
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


def scan_deleted(records) -> list[str]:
    """The paths the scan saw as deleted."""
    deleted = [name for code, name, original in records if original is None and "D" in code]
    deleted.extend(original for code, name, original in records if original is not None)
    return deleted


def agents_bootstrap(repo: Path) -> bool:
    """Call the cleaner across its signature changes."""
    try:
        return cleaner.agents_only_rules(repo)
    except TypeError:
        return cleaner.agents_only_rules(repo, untracked=False)


def scan_digests(repo: Path, records: list[tuple[str, str, str | None]]) -> dict[str, str | None]:
    """The digests the scan records for the changes it put through the cleaner."""
    digests: dict[str, str | None] = {}
    for _code, name, _original in records:
        digests[name] = cleaner.file_digest(repo / name)
    return digests


def clear_bootstrap(repo: Path, records, trash: Path, digests=None, index_before=None, deleted=None):
    """Call the cleaner across its signature changes."""
    if deleted is None:
        deleted = [name for code, name, original in records if original is None and "D" in code]
        deleted.extend(original for code, name, original in records if original is not None)
    if digests is None:
        digests = {name: cleaner.file_digest(repo / name) for code, name, original in records if original is None}
    if index_before is None:
        index_before = cleaner.index_digest(repo)
    for arguments in ((repo, records, trash, digests, index_before, None, deleted), (repo, records, trash, digests, index_before, None), (repo, records, trash, digests, index_before), (repo, records, trash, digests), (repo, records, trash), (repo, records)):
        try:
            return cleaner.clear_bootstrap_changes(*arguments)
        except TypeError:
            continue
        except AttributeError:
            return None
    return None


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
            trash = Path(tmp) / "trash"
            trash.mkdir()
            self.assertIsNone(cleaner.clear_bootstrap_changes(repo, records, trash))


class AgentsBootstrapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mo514-agents-")
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.trash = Path(self.tmp.name) / "trash"
        self.trash.mkdir()
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
        self.trash = Path(self.tmp.name) / "trash"
        self.trash.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@example.test")
        commit(self.repo, "AGENTS.md", "# Repository rules\n\n")
        self.block = RULES.read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def tracked_specstory(self) -> Path:
        """A repository that commits the bootstrap file `.specstory/a.md`."""
        repo = Path(self.tmp.name) / "specstory-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        commit(repo, ".specstory/a.md", "history\n")
        return repo

    def test_only_bootstrap_changes_are_cleared(self):
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        (self.repo / ".specstory").mkdir()
        (self.repo / ".specstory" / "session.md").write_text("history\n", encoding="utf-8")
        records = cleaner.status_for(self.repo)
        cleared = cleaner.clear_bootstrap_changes(self.repo, records, self.trash, scan_digests(self.repo, records), cleaner.index_digest(self.repo), None, scan_deleted(records))
        self.assertEqual(sorted(cleared or []), [".specstory/session.md", "AGENTS.md"])
        self.assertFalse((self.repo / ".specstory" / "session.md").exists())
        self.assertEqual(cleaner.status_for(self.repo), [])

    def test_a_bootstrap_rename_is_cleared(self):
        # A rename has already taken the source away, so the committed bytes are
        # restored instead of read back from the working tree.
        repo = self.tracked_specstory()
        git(repo, "mv", ".specstory/a.md", ".specstory/b.md")
        records = cleaner.status_for(repo)
        self.assertEqual(cleaner.classify_changes(repo, records), ([".specstory/b.md"], []))
        cleared = cleaner.clear_bootstrap_changes(repo, records, self.trash, scan_digests(repo, records), cleaner.index_digest(repo), None, scan_deleted(records))
        self.assertEqual(cleared, [".specstory/b.md"])
        self.assertEqual((repo / ".specstory" / "a.md").read_text(encoding="utf-8"), "history\n")
        self.assertFalse((repo / ".specstory" / "b.md").exists())
        self.assertEqual(cleaner.status_for(repo), [])

    def test_a_deleted_bootstrap_file_is_restored(self):
        repo = self.tracked_specstory()
        (repo / ".specstory" / "a.md").unlink()
        records = cleaner.status_for(repo)
        cleared = cleaner.clear_bootstrap_changes(repo, records, self.trash, scan_digests(repo, records), cleaner.index_digest(repo), None, scan_deleted(records))
        self.assertEqual(cleared, [".specstory/a.md"])
        self.assertEqual(cleaner.status_for(repo), [])

    def test_a_save_at_a_renamed_source_keeps_the_worktree(self):
        # The scan never hashed the source of a rename, so a file that came back
        # there holds bytes nobody verified and must be kept.
        repo = self.tracked_specstory()
        git(repo, "mv", ".specstory/a.md", ".specstory/b.md")
        digests = scan_digests(repo, cleaner.status_for(repo))
        (repo / ".specstory" / "a.md").write_text("saved by an editor\n", encoding="utf-8")
        records = cleaner.status_for(repo)
        self.assertIsNone(cleaner.clear_bootstrap_changes(repo, records, self.trash, digests))
        self.assertTrue((repo / ".specstory" / "a.md").exists())

    def test_a_save_after_the_scan_keeps_the_worktree(self):
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        digests = {"AGENTS.md": cleaner.file_digest(self.repo / "AGENTS.md")}
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write("saved by an editor\n")
        records = cleaner.status_for(self.repo)
        self.assertIsNone(cleaner.clear_bootstrap_changes(self.repo, records, self.trash, digests, cleaner.index_digest(self.repo)))
        self.assertIn("saved by an editor", (self.repo / "AGENTS.md").read_text(encoding="utf-8"))

    def test_a_newly_staged_bootstrap_file_is_cleared(self):
        # A staged addition has no path in HEAD, so the cleanup must remove
        # the file and drop the index entry instead of restoring from HEAD.
        repo = Path(self.tmp.name) / "new-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        commit(repo, "base.txt", "base\n")
        (repo / "AGENTS.md").write_text(self.block, encoding="utf-8")
        git(repo, "add", "AGENTS.md")
        (repo / ".specstory").mkdir()
        (repo / ".specstory" / "session.md").write_text("history\n", encoding="utf-8")
        git(repo, "add", ".specstory/session.md")
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, original in records if original is None}
        try:
            cleared = clear_bootstrap(repo, records, self.trash, digests)
        except Exception:
            cleared = None
        self.assertEqual(sorted(cleared or []), [".specstory/session.md", "AGENTS.md"])
        self.assertEqual(cleaner.status_for(repo), [])

    def test_a_staged_edit_after_the_scan_is_never_erased(self):
        # Another process stages genuine content while the working copy
        # stays as it was. The index must not be reset over that edit.
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        index_before = cleaner.index_digest(self.repo)
        staged = self.repo / "staged.txt"
        staged.write_text("genuine staged edit\n", encoding="utf-8")
        git(self.repo, "add", "staged.txt")
        records = cleaner.status_for(self.repo)
        digests = {"AGENTS.md": cleaner.file_digest(self.repo / "AGENTS.md")}
        self.assertIsNone(clear_bootstrap(self.repo, records, self.trash, digests, index_before))
        listing = git(self.repo, "ls-files", "-s", "--", "staged.txt")
        self.assertIn("staged.txt", listing)

    def test_a_recovery_keeps_both_copies(self):
        # The file changes while it is moved aside and the editor recreates
        # the path: neither copy may be overwritten.
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        digests = {"AGENTS.md": cleaner.file_digest(self.repo / "AGENTS.md")}
        original_replace = os.replace

        def replace_and_save(source, destination, *args, **kwargs):
            result = original_replace(source, destination, *args, **kwargs)
            if str(destination).startswith("moved"):
                # The editor wrote through its open handle into the moved
                # file and recreated the path with its own copy.
                moved = self.trash / str(destination)
                with moved.open("a", encoding="utf-8") as handle:
                    handle.write("saved by an editor\n")
                with (self.repo / "AGENTS.md").open("w", encoding="utf-8") as handle:
                    handle.write("saved by an editor\n")
            return result

        with mock.patch.object(cleaner.os, "replace", replace_and_save):
            cleared = clear_bootstrap(self.repo, cleaner.status_for(self.repo), self.trash, digests)
        self.assertIsNone(cleared)
        self.assertIn("saved by an editor", (self.repo / "AGENTS.md").read_text(encoding="utf-8"))
        kept = [item for item in self.trash.iterdir() if item.is_file()]
        self.assertTrue(kept, "the recovered copy must be kept")

    def test_a_save_that_lands_before_the_restore_is_never_overwritten(self):
        # The editor saves after the cleaner read the changed bytes and before
        # it restores them, so the path looks free when the cleaner checks.
        # The save must keep its file and the recovered copy must be kept.
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        target = self.repo / "AGENTS.md"
        digests = {"AGENTS.md": cleaner.file_digest(target)}
        original_replace = os.replace

        def replace_and_save(source, destination, *args, **kwargs):
            result = original_replace(source, destination, *args, **kwargs)
            if str(destination).startswith("moved"):
                moved = self.trash / str(destination)
                with moved.open("a", encoding="utf-8") as handle:
                    handle.write("write-through bytes\n")
                target.write_text("saved by an editor\n", encoding="utf-8")
            return result

        with mock.patch.object(cleaner.os, "replace", replace_and_save):
            cleared = clear_bootstrap(self.repo, cleaner.status_for(self.repo), self.trash, digests)
        self.assertIsNone(cleared)
        self.assertEqual(target.read_text(encoding="utf-8"), "saved by an editor\n")
        kept = [item.read_text(encoding="utf-8") for item in self.trash.iterdir() if item.is_file()]
        self.assertTrue(any("write-through bytes" in text for text in kept), "the recovered copy must be kept")

    def test_a_missing_index_digest_refuses_the_cleanup(self):
        # The scan could not read the index, so what is staged is unknown and
        # the index must be left alone.
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        staged = self.repo / "staged.txt"
        staged.write_text("genuine staged edit\n", encoding="utf-8")
        git(self.repo, "add", "staged.txt")
        records = cleaner.status_for(self.repo)
        digests = {"AGENTS.md": cleaner.file_digest(self.repo / "AGENTS.md")}
        self.assertIsNone(cleaner.clear_bootstrap_changes(self.repo, records, self.trash, digests, None))
        self.assertIn("staged.txt", git(self.repo, "ls-files", "-s", "--", "staged.txt"))

    def test_recovery_copies_of_two_worktrees_do_not_collide(self):
        # Two worktrees with the same relative path must not share the name
        # of the copy that is kept when a save is raced.
        names = []
        for index in range(2):
            repo = Path(self.tmp.name) / f"repo-{index}"
            repo.mkdir()
            git(repo, "init", "-b", "main")
            git(repo, "config", "user.name", "Fixture")
            git(repo, "config", "user.email", "fixture@example.test")
            commit(repo, "AGENTS.md", "# Repository rules\n\n")
            with (repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
                handle.write(self.block)
            digests = {"AGENTS.md": cleaner.file_digest(repo / "AGENTS.md")}
            original_replace = os.replace

            def replace_and_save(source, destination, *args, index=index, **kwargs):
                result = original_replace(source, destination, *args, **kwargs)
                if str(destination).startswith("moved"):
                    moved = self.trash / str(destination)
                    with moved.open("a", encoding="utf-8") as handle:
                        handle.write(f"saved by an editor {index}\n")
                    with (repo / "AGENTS.md").open("w", encoding="utf-8") as handle:
                        handle.write(f"saved by an editor {index}\n")
                return result

            with mock.patch.object(cleaner.os, "replace", replace_and_save):
                clear_bootstrap(repo, cleaner.status_for(repo), self.trash, digests)
            names.append((repo / "AGENTS.md").read_text(encoding="utf-8"))
        kept = sorted(item.name for item in self.trash.iterdir() if item.is_file())
        self.assertEqual(len(kept), 2, kept)
        self.assertEqual(len(set(kept)), 2, kept)

    def test_a_file_name_that_is_not_utf8_does_not_abort_the_scan(self):
        # A path that is not valid UTF-8 must not raise out of the status
        # reader, and it must come back unchanged. macOS refuses to create
        # such a name, so the status output is fed to the reader directly.
        raw = b"\xff\xfe-notes.txt"

        def fake_status(path, *args):
            return b"?? " + raw + b"\0"

        with mock.patch.object(cleaner, "git_bytes", fake_status):
            records = cleaner.status_for(self.repo)
        self.assertEqual([name for _code, name, _original in records], [os.fsdecode(raw)])

    def test_a_cleared_file_is_kept_in_recovery_storage(self):
        # The moved file is the only place a save through an open descriptor
        # can live, so it is kept instead of deleted.
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        records = cleaner.status_for(self.repo)
        digests = {name: cleaner.file_digest(self.repo / name) for code, name, original in records if original is None}
        cleared = clear_bootstrap(self.repo, records, self.trash, digests, cleaner.index_digest(self.repo))
        self.assertEqual(sorted(cleared or []), ["AGENTS.md"])
        kept = [item for item in self.trash.iterdir() if item.is_file()]
        self.assertTrue(kept, "the moved file must be kept")
        self.assertTrue(any(item.read_bytes().endswith(self.block.encode("utf-8")) for item in kept), kept)

    def test_a_deleted_bootstrap_file_with_a_missing_parent_is_restored(self):
        # The whole directory is gone, so the parent of the file has to come
        # back before the file can be written.
        repo = Path(self.tmp.name) / "nested-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".specstory" / "nested").mkdir(parents=True)
        (repo / ".specstory" / "nested" / "a.md").write_text("history\n", encoding="utf-8")
        git(repo, "add", ".specstory/nested/a.md")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=a@b.c", "commit", "-m", "history"], check=True, capture_output=True)
        (repo / ".specstory" / "nested" / "a.md").unlink()
        (repo / ".specstory" / "nested").rmdir()
        (repo / ".specstory").rmdir()
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, original in records if original is None}
        cleared = clear_bootstrap(repo, records, self.trash, digests, cleaner.index_digest(repo))
        self.assertEqual(sorted(cleared or []), [".specstory/nested/a.md"])
        self.assertTrue((repo / ".specstory" / "nested" / "a.md").exists())
        self.assertEqual(cleaner.status_for(repo), [])

    def test_a_tracked_symlink_is_restored_as_a_link(self):
        repo = Path(self.tmp.name) / "link-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".specstory").mkdir()
        os.symlink("../elsewhere.md", repo / ".specstory" / "link.md")
        git(repo, "add", ".specstory/link.md")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=a@b.c", "commit", "-m", "link"], check=True, capture_output=True)
        (repo / ".specstory" / "link.md").unlink()
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, original in records if original is None}
        cleared = clear_bootstrap(repo, records, self.trash, digests, cleaner.index_digest(repo))
        self.assertEqual(sorted(cleared or []), [".specstory/link.md"])
        link = repo / ".specstory" / "link.md"
        self.assertTrue(link.is_symlink(), "the link must be restored as a link")
        self.assertEqual(os.readlink(link), "../elsewhere.md")
        self.assertEqual(cleaner.status_for(repo), [])

    def test_a_deleted_symlink_with_a_missing_parent_is_restored(self):
        # The link and its directory are both gone, so the parent has to come
        # back before the link can be restored.
        repo = Path(self.tmp.name) / "link-nested-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".specstory" / "nested").mkdir(parents=True)
        os.symlink("../../elsewhere.md", repo / ".specstory" / "nested" / "link.md")
        git(repo, "add", ".specstory/nested/link.md")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=a@b.c", "commit", "-m", "link"], check=True, capture_output=True)
        (repo / ".specstory" / "nested" / "link.md").unlink()
        (repo / ".specstory" / "nested").rmdir()
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, original in records if original is None}
        cleared = clear_bootstrap(repo, records, self.trash, digests, cleaner.index_digest(repo))
        self.assertEqual(sorted(cleared or []), [".specstory/nested/link.md"])
        link = repo / ".specstory" / "nested" / "link.md"
        self.assertTrue(link.is_symlink(), "the link must be restored as a link")
        self.assertEqual(os.readlink(link), "../../elsewhere.md")
        self.assertEqual(cleaner.status_for(repo), [])

    def test_a_link_that_replaces_the_directory_stops_the_restore(self):
        # A link that replaces the directory after the scan must not let the
        # restore write outside the worktree.
        repo = Path(self.tmp.name) / "swapped-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".specstory").mkdir()
        (repo / ".specstory" / "notes").write_text("history\n", encoding="utf-8")
        git(repo, "add", ".specstory/notes")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=a@b.c", "commit", "-m", "notes"], check=True, capture_output=True)
        (repo / ".specstory" / "notes").write_text("edited\n", encoding="utf-8")
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, original in records if original is None}
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (repo / ".specstory" / "notes").unlink()
        (repo / ".specstory").rmdir()
        os.symlink(str(outside), repo / ".specstory")
        cleared = clear_bootstrap(repo, records, self.trash, digests, cleaner.index_digest(repo))
        self.assertIsNone(cleared)
        self.assertFalse((outside / "notes").exists(), "nothing may be written outside the worktree")

    def test_a_moved_link_is_compared_by_its_target(self):
        # The link is moved aside, where its relative target no longer
        # resolves, so the target itself has to be compared.
        repo = Path(self.tmp.name) / "moved-link-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".specstory").mkdir()
        (repo / "notes.md").write_text("notes\n", encoding="utf-8")
        os.symlink("../notes.md", repo / ".specstory" / "link.md")
        git(repo, "add", ".specstory/link.md", "notes.md")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=a@b.c", "commit", "-m", "link"], check=True, capture_output=True)
        (repo / ".specstory" / "link.md").unlink()
        os.symlink("../other.md", repo / ".specstory" / "link.md")
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, original in records if original is None}
        cleared = clear_bootstrap(repo, records, self.trash, digests, cleaner.index_digest(repo))
        self.assertEqual(sorted(cleared or []), [".specstory/link.md"])
        link = repo / ".specstory" / "link.md"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "../notes.md")

    def test_a_link_that_appears_after_the_check_cannot_redirect_the_restore(self):
        # The directory is replaced by a link after the parent was opened.
        # The create is relative to the descriptor, so it cannot land outside.
        repo = Path(self.tmp.name) / "late-link-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".specstory").mkdir()
        (repo / ".specstory" / "notes").write_text("history\n", encoding="utf-8")
        git(repo, "add", ".specstory/notes")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=a@b.c", "commit", "-m", "notes"], check=True, capture_output=True)
        (repo / ".specstory" / "notes").write_text("edited\n", encoding="utf-8")
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, original in records if original is None}
        (repo / ".specstory" / "notes").unlink()
        outside = Path(self.tmp.name) / "outside-late"
        outside.mkdir()
        original_open = cleaner._open_parent_fd
        swapped = []

        def open_then_swap(repo_arg, relative):
            descriptor = original_open(repo_arg, relative)
            if descriptor is not None and not swapped:
                swapped.append(True)
                os.rename(repo / ".specstory", repo / ".specstory-real")
                os.symlink(str(outside), repo / ".specstory")
            return descriptor

        with mock.patch.object(cleaner, "_open_parent_fd", open_then_swap):
            clear_bootstrap(repo, records, self.trash, digests, cleaner.index_digest(repo))
        self.assertFalse((outside / "notes").exists(), "nothing may be written outside the worktree")

    def test_a_link_that_appears_before_the_move_cannot_take_an_outside_file(self):
        # The directory turns into a link after the parent was opened. The
        # move is relative to the descriptor, so the file that is moved is the
        # one inside the worktree, never the one outside.
        repo = Path(self.tmp.name) / "move-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".specstory").mkdir()
        (repo / ".specstory" / "notes").write_text("history\n", encoding="utf-8")
        git(repo, "add", ".specstory/notes")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=a@b.c", "commit", "-m", "notes"], check=True, capture_output=True)
        (repo / ".specstory" / "notes").write_text("edited\n", encoding="utf-8")
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, original in records if original is None}
        outside = Path(self.tmp.name) / "outside-move"
        outside.mkdir()
        (outside / "notes").write_text("outside\n", encoding="utf-8")
        original_open = cleaner._open_parent_fd
        swapped = []

        def open_then_swap(repo_arg, relative):
            descriptor = original_open(repo_arg, relative)
            if descriptor is not None and not swapped:
                swapped.append(True)
                os.rename(repo / ".specstory", repo / ".specstory-real")
                os.symlink(str(outside), repo / ".specstory")
            return descriptor

        with mock.patch.object(cleaner, "_open_parent_fd", open_then_swap):
            clear_bootstrap(repo, records, self.trash, digests, cleaner.index_digest(repo))
        self.assertEqual((outside / "notes").read_text(encoding="utf-8"), "outside\n")
        for item in self.trash.iterdir():
            if item.is_file():
                self.assertNotIn(b"outside\n", item.read_bytes())

    def test_the_cleanup_does_not_leak_descriptors(self):
        # Every cleared file opens a directory descriptor, and each one has
        # to be closed again.
        repo = Path(self.tmp.name) / "leak-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".specstory").mkdir()
        for index in range(40):
            (repo / ".specstory" / f"note{index}.md").write_text("history\n", encoding="utf-8")
        git(repo, "add", ".specstory")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=a@b.c", "commit", "-m", "notes"], check=True, capture_output=True)
        for index in range(40):
            (repo / ".specstory" / f"note{index}.md").write_text("edited\n", encoding="utf-8")
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, original in records if original is None}
        before = len(os.listdir("/dev/fd"))
        cleared = clear_bootstrap(repo, records, self.trash, digests, cleaner.index_digest(repo))
        after = len(os.listdir("/dev/fd"))
        self.assertEqual(len(cleared or []), 40)
        self.assertLessEqual(after - before, 2, "the cleanup must not leak descriptors")

    def test_a_changed_link_target_is_restored_as_a_link(self):
        # The editor repoints the link between the read and the move, so the
        # recovery has to restore a link and not a file with the target.
        repo = Path(self.tmp.name) / "changed-link-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".specstory").mkdir()
        (repo / "notes.md").write_text("notes\n", encoding="utf-8")
        os.symlink("../notes.md", repo / ".specstory" / "link.md")
        git(repo, "add", ".specstory/link.md", "notes.md")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=a@b.c", "commit", "-m", "link"], check=True, capture_output=True)
        (repo / ".specstory" / "link.md").unlink()
        os.symlink("../other.md", repo / ".specstory" / "link.md")
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, original in records if original is None}
        original_replace = os.replace

        def replace_and_repoint(source, destination, *args, **kwargs):
            result = original_replace(source, destination, *args, **kwargs)
            if str(destination).startswith("moved"):
                moved = self.trash / str(destination)
                moved.unlink()
                os.symlink("../third.md", moved)
            return result

        with mock.patch.object(cleaner.os, "replace", replace_and_repoint):
            cleared = clear_bootstrap(repo, records, self.trash, digests, cleaner.index_digest(repo))
        link = repo / ".specstory" / "link.md"
        self.assertTrue(link.is_symlink(), "the link must be restored as a link")
        self.assertEqual(os.readlink(link), "../third.md")
        self.assertIsNone(cleared)

    def test_a_mode_change_after_the_scan_keeps_the_worktree(self):
        # The file becomes executable after the scan. The bytes still match,
        # so the mode has to be compared as well, and the worktree has to be
        # kept with that change in it.
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        records = cleaner.status_for(self.repo)
        digests = {name: cleaner.file_digest(self.repo / name) for code, name, original in records if original is None}
        signatures = {name: cleaner._working_signature(self.repo / name) for code, name, original in records if original is None}
        index_before = cleaner.index_digest(self.repo)
        os.chmod(self.repo / "AGENTS.md", 0o755)
        cleared = cleaner.clear_bootstrap_changes(self.repo, records, self.trash, digests, index_before, signatures)
        self.assertIsNone(cleared)
        self.assertTrue(os.access(self.repo / "AGENTS.md", os.X_OK), "the mode change has to survive")
        self.assertNotEqual(cleaner.status_for(self.repo), [])

    def test_the_stamp_sees_a_mode_change(self):
        # The stamp of a checkout has to hold the mode of a file. A file
        # that only gained its executable bit leaves the bytes, the size and
        # the time alone, so without the mode the change would not be seen
        # and the checkout that holds it would be removed.
        directory = Path(self.tmp.name) / "checkout"
        directory.mkdir()
        script = directory / "run.sh"
        script.write_text("echo hello\n", encoding="utf-8")
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            stamp = cleaner._snapshot_all(descriptor)
        finally:
            os.close(descriptor)
        self.assertTrue(
            cleaner._tree_matches(directory, stamp),
            "the stamp has to match the tree it was taken from",
        )
        os.chmod(script, 0o755)
        self.assertFalse(
            cleaner._tree_matches(directory, stamp),
            "a mode change has to be seen by the stamp",
        )

    def _renamed_repo(self, name: str) -> Path:
        repo = Path(self.tmp.name) / name
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".specstory").mkdir()
        (repo / ".specstory" / "a.md").write_text("history\n", encoding="utf-8")
        git(repo, "add", ".specstory/a.md")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=a@b.c", "commit", "-m", "history"], check=True, capture_output=True)
        git(repo, "mv", ".specstory/a.md", ".specstory/b.md")
        return repo

    def test_a_rename_destination_is_cleared(self):
        # The same rename as below, without a mode change, has to succeed, so
        # the test that follows cannot pass for the wrong reason.
        repo = self._renamed_repo("rename-plain-repo")
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, _original in records}
        signatures = {name: cleaner._working_signature(repo / name) for code, name, _original in records}
        cleared = cleaner.clear_bootstrap_changes(repo, records, self.trash, digests, cleaner.index_digest(repo), signatures, scan_deleted(records))
        self.assertEqual(sorted(cleared or []), [".specstory/b.md"])
        self.assertEqual(cleaner.status_for(repo), [])

    def test_a_mode_change_on_a_rename_destination_keeps_the_worktree(self):
        # The destination of a staged rename becomes executable after the
        # scan. The bytes still match, so the mode has to be compared too,
        # and the file has to stay in the worktree with its new mode.
        repo = self._renamed_repo("rename-mode-repo")
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, _original in records}
        signatures = {name: cleaner._working_signature(repo / name) for code, name, _original in records}
        os.chmod(repo / ".specstory" / "b.md", 0o755)
        cleared = cleaner.clear_bootstrap_changes(repo, records, self.trash, digests, cleaner.index_digest(repo), signatures, scan_deleted(records))
        self.assertIsNone(cleared)
        destination = repo / ".specstory" / "b.md"
        self.assertTrue(destination.exists(), "the file must stay in the worktree")
        self.assertTrue(os.access(destination, os.X_OK), "the mode change has to survive")

    def test_a_deletion_after_the_scan_keeps_the_worktree(self):
        # The file is deleted after the scan, so the deletion is kept and the
        # committed copy is not restored over it.
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        records = cleaner.status_for(self.repo)
        digests = {name: cleaner.file_digest(self.repo / name) for code, name, original in records if original is None}
        signatures = {name: cleaner._working_signature(self.repo / name) for code, name, original in records if original is None}
        (self.repo / "AGENTS.md").unlink()
        cleared = cleaner.clear_bootstrap_changes(self.repo, records, self.trash, digests, cleaner.index_digest(self.repo), signatures)
        self.assertIsNone(cleared)
        self.assertFalse((self.repo / "AGENTS.md").exists(), "the deletion has to survive")

    def test_the_moved_original_is_kept_when_the_mode_changed(self):
        # The mode changes while the file is moved aside. The file goes back
        # to its own path, and the moved original stays in the recovery
        # storage, so an editor that still has it open can finish saving.
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        records = cleaner.status_for(self.repo)
        digests = {name: cleaner.file_digest(self.repo / name) for code, name, _original in records}
        signatures = {name: cleaner._working_signature(self.repo / name) for code, name, _original in records}
        index_before = cleaner.index_digest(self.repo)
        original_replace = os.replace

        def replace_and_change_mode(source, destination, *args, **kwargs):
            result = original_replace(source, destination, *args, **kwargs)
            if str(destination).startswith("moved"):
                os.chmod(self.trash / str(destination), 0o755)
            return result

        with mock.patch.object(cleaner.os, "replace", replace_and_change_mode):
            cleared = cleaner.clear_bootstrap_changes(self.repo, records, self.trash, digests, index_before, signatures)
        self.assertIsNone(cleared)
        restored = self.repo / "AGENTS.md"
        self.assertTrue(restored.exists(), "the file must be back at its path")
        self.assertTrue(restored.read_text(encoding="utf-8").endswith(self.block))
        kept = [item for item in self.trash.iterdir() if item.is_file()]
        self.assertTrue(kept, "the moved original has to stay in the recovery storage")

    def test_a_restore_refuses_an_occupied_path(self):
        # The path is taken by an editor between the check and the restore, so
        # the restore has to refuse it and keep the recovery copy.
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(self.block)
        records = cleaner.status_for(self.repo)
        digests = {name: cleaner.file_digest(self.repo / name) for code, name, _original in records}
        signatures = {name: cleaner._working_signature(self.repo / name) for code, name, _original in records}
        index_before = cleaner.index_digest(self.repo)
        original_replace = os.replace

        def replace_and_take(source, destination, *args, **kwargs):
            result = original_replace(source, destination, *args, **kwargs)
            if str(destination).startswith("moved"):
                # The editor takes the path back while the file is moved.
                (self.repo / "AGENTS.md").write_text("saved by an editor\n", encoding="utf-8")
            return result

        with mock.patch.object(cleaner.os, "replace", replace_and_take):
            cleared = cleaner.clear_bootstrap_changes(self.repo, records, self.trash, digests, index_before, signatures)
        self.assertIsNone(cleared)
        self.assertEqual((self.repo / "AGENTS.md").read_text(encoding="utf-8"), "saved by an editor\n")
        kept = [item.read_bytes() for item in self.trash.iterdir() if item.is_file()]
        self.assertTrue(any(b"AGENTS.md" in item or b"standing rules" in item for item in kept), "the recovery copy has to be kept")

    def test_a_fifo_is_never_read(self):
        # A file replaced by a FIFO must not block the cleanup.
        repo = Path(self.tmp.name) / "fifo-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        commit(repo, "AGENTS.md", "# Repository rules\n\n")
        (repo / "AGENTS.md").unlink()
        os.mkfifo(repo / "AGENTS.md")
        self.assertEqual(cleaner._file_bytes(repo / "AGENTS.md"), None)
        self.assertEqual(cleaner.file_digest(repo / "AGENTS.md"), None)
        # The classification path must not block on it either.
        self.assertFalse(cleaner.agents_only_rules(repo))

    def test_a_changed_head_is_detected(self):
        # A commit made after the scan moves the head, and the removal has to
        # notice before git removes the worktree with the new commit in it.
        repo = Path(self.tmp.name) / "head-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        commit(repo, "a.txt", "a\n")
        first = git(repo, "rev-parse", "HEAD")
        commit(repo, "b.txt", "b\n")
        second = git(repo, "rev-parse", "HEAD")
        self.assertFalse(cleaner._head_matches(repo, first))
        self.assertTrue(cleaner._head_matches(repo, second))

    def test_a_pull_request_is_found_by_its_commit(self):
        # The branch of the pull request is gone, so the pull requests of the
        # commit itself have to be asked for.
        github = cleaner.GitHub()
        head = "a" * 40
        github.pulls_for_commit = lambda repo, sha, **_kwargs: [
            {"number": 7, "state": "CLOSED", "merged": "2026-11-18T00:00:00Z", "headSha": head},
            {"number": 8, "state": "OPEN", "merged": None, "headSha": head},
        ]
        ok, why, url = cleaner.verify_pr_for_head(github, "owner/repo", self.repo, head)
        self.assertTrue(ok)
        self.assertEqual(url, "https://github.com/owner/repo/pull/7")

    def test_the_live_github_answer_decides_about_ancestry(self):
        # The local repository may not have fetched, so the local count of
        # unpushed commits can be positive while GitHub already has the head
        # on the default branch.
        github = cleaner.GitHub()
        head = "a" * 40
        github.default_branch = lambda repo, **_kwargs: "main"
        github.contains = lambda repo, base, sha, **_kwargs: True
        row = {"head": head, "unpushed": 3, "remote_commit_present": True}
        self.assertTrue(cleaner.published_on_default_branch(row, github, "owner/repo"))

    def test_the_recovery_storage_is_on_the_same_filesystem(self):
        # The recovery storage has to be on the filesystem of the worktree,
        # so that moving a file into it is a rename.
        base = Path(self.tmp.name)
        state = base / "state"
        state.mkdir()
        worktree = base / "worktree"
        worktree.mkdir()
        trash = cleaner._trash_for(state, worktree)
        self.assertEqual(os.stat(trash).st_dev, os.stat(worktree).st_dev)

    def test_a_replaced_worktree_root_is_refused(self):
        # The worktree directory is renamed and a link takes its place: the
        # cleaner must not follow it into the other directory.
        repo = Path(self.tmp.name) / "root-repo"
        repo.mkdir()
        (repo / ".specstory").mkdir()
        (repo / ".specstory" / "notes.md").write_text("history\n", encoding="utf-8")
        elsewhere = Path(self.tmp.name) / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / ".specstory").mkdir()
        (elsewhere / ".specstory" / "notes.md").write_text("history\n", encoding="utf-8")
        os.rename(repo, repo.with_name("root-repo-moved"))
        os.symlink(str(elsewhere), repo)
        self.assertIsNone(cleaner._open_parent_fd(repo, Path(".")))

    def test_a_refused_cleanup_leaves_an_index_of_another_client(self):
        # Another git client may use a file next to the index. A cleanup that
        # refuses must not remove it.
        repo = Path(self.tmp.name) / "index-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        commit(repo, "a.txt", "a\n")
        index = Path(git(repo, "rev-parse", "--git-path", "index").strip())
        if not index.is_absolute():
            index = repo / index
        other = index.with_name(index.name + ".cleaner")
        other.write_text("staged work of another client\n", encoding="utf-8")
        # The digest does not match, so the cleanup refuses.
        self.assertFalse(cleaner._reset_index_to_head(repo, "0" * 64))
        self.assertTrue(other.exists(), "the file of another client must stay")
        self.assertEqual(other.read_text(encoding="utf-8"), "staged work of another client\n")

    def test_a_refused_publish_leaves_no_temporary_file(self):
        # The publication writes a private file first, so a refused publish
        # leaves neither the editor's file nor a temporary file behind.
        repo = Path(self.tmp.name) / "publish-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        commit(repo, "a.txt", "a\n")
        target = repo / "AGENTS.md"
        target.write_text("saved by an editor\n", encoding="utf-8")
        self.assertFalse(cleaner._exclusive_write(repo, Path("AGENTS.md"), b"recovered\n", 0o644))
        self.assertEqual(target.read_text(encoding="utf-8"), "saved by an editor\n")
        self.assertEqual([item.name for item in repo.iterdir() if item.name.startswith(".cleaner-")], [])

    def test_a_branch_name_is_encoded_in_the_comparison_url(self):
        # A branch name can hold characters that would change the meaning of
        # the url, so it is encoded before it goes into the request.
        github = cleaner.GitHub()
        requests = []
        original_run = cleaner.run

        def record(argv, **kwargs):
            requests.append(argv)
            class Result:
                returncode = 0
                stdout = "behind"
                stderr = ""
            return Result()

        with mock.patch.object(cleaner, "run", record):
            self.assertTrue(github.contains("owner/repo", "release#1", "a" * 40))
        url = next(argv[2] for argv in requests if "compare" in argv[2])
        self.assertIn("release%231", url)
        self.assertNotIn("release#1", url)

    def test_a_replaced_worktree_directory_is_refused(self):
        # Another real directory takes the place of the worktree. The identity
        # the scan saw is not the one at the path now, so nothing in the
        # replacement may be touched.
        repo = Path(self.tmp.name) / "swapped-worktree"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".specstory").mkdir()
        (repo / ".specstory" / "notes.md").write_text("history\n", encoding="utf-8")
        git(repo, "add", ".specstory/notes.md")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=a@b.c", "commit", "-m", "notes"], check=True, capture_output=True)
        (repo / ".specstory" / "notes.md").write_text("edited\n", encoding="utf-8")
        identity = cleaner.root_identity(repo)
        records = cleaner.status_for(repo)
        digests = {name: cleaner.file_digest(repo / name) for code, name, _original in records}
        signatures = {name: cleaner._working_signature(repo / name) for code, name, _original in records}
        # The same file, in another directory that now carries the name.
        replacement = Path(self.tmp.name) / "replacement"
        (replacement / ".specstory").mkdir(parents=True)
        (replacement / ".specstory" / "notes.md").write_text("edited\n", encoding="utf-8")
        os.rename(repo, repo.with_name("swapped-worktree-moved"))
        os.rename(replacement, repo)
        cleared = cleaner.clear_bootstrap_changes(repo, records, self.trash, digests, cleaner.index_digest(repo), signatures, scan_deleted(records), identity)
        self.assertIsNone(cleared)
        self.assertTrue((repo / ".specstory" / "notes.md").exists(), "the replacement directory must not be touched")

    def test_the_registration_of_a_worktree_is_its_own(self):
        # Two worktrees can share a basename. Each one has to name its own
        # registration, not the one git derived from the basename.
        base = Path(self.tmp.name)
        repo = base / "shared-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        commit(repo, "a.txt", "a\n")
        first = base / "a" / "topic"
        second = base / "b" / "topic"
        first.parent.mkdir(parents=True)
        second.parent.mkdir(parents=True)
        git(repo, "worktree", "add", "--detach", str(first), git(repo, "rev-parse", "HEAD"))
        git(repo, "worktree", "add", "--detach", str(second), git(repo, "rev-parse", "HEAD"))
        first_admin = cleaner._worktree_registration(first)
        second_admin = cleaner._worktree_registration(second)
        self.assertIsNotNone(first_admin)
        self.assertIsNotNone(second_admin)
        self.assertNotEqual(first_admin, second_admin)
        listed = git(repo, "worktree", "list", "--porcelain")
        self.assertIn(str(first), listed)
        self.assertIn(str(second), listed)

    def test_the_recovery_names_are_unique(self):
        # Every file that is kept under a recovery name gets a name of its
        # own, so a later cleanup cannot overwrite a preserved file.
        repo = Path(self.tmp.name) / "recovery-repo"
        repo.mkdir()
        for index in range(6):
            (repo / f"file{index}.md").write_text("content\n", encoding="utf-8")
        descriptor = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index in range(6):
                wrong = (0, 0, 0, 0)
                self.assertEqual(cleaner._unlink_verified(descriptor, f"file{index}.md", wrong), 1)
        finally:
            os.close(descriptor)
        kept = sorted(item.name for item in repo.iterdir())
        self.assertEqual(len(kept), 6, kept)
        self.assertEqual(len(set(kept)), 6, kept)

    def test_a_directory_restore_keeps_both_copies(self):
        # A directory that took the path is preserved and the copy that was
        # moved aside is kept.
        base = Path(self.tmp.name)
        source = base / "aside"
        source.mkdir()
        (source / "kept.md").write_text("kept\n", encoding="utf-8")
        destination = base / "path"
        destination.mkdir()
        (destination / "other.md").write_text("other\n", encoding="utf-8")
        self.assertFalse(cleaner._rename_exclusive(source, destination))
        self.assertTrue((destination / "other.md").exists())
        self.assertTrue((source / "kept.md").exists())

    def test_an_ignored_file_keeps_the_worktree(self):
        # An ignored file is local work: the status without the ignored
        # entries would not show it, and it must not be deleted.
        repo = Path(self.tmp.name) / "ignored-repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / ".gitignore").write_text("notes.local\n", encoding="utf-8")
        commit(repo, ".gitignore", "notes.local\n")
        (repo / "notes.local").write_text("local work\n", encoding="utf-8")
        records = cleaner.status_for(repo, include_ignored=True)
        self.assertTrue(any(code.strip() == "!!" for code, _name, _original in records), records)
        plain = cleaner.status_for(repo)
        self.assertFalse(any(code.strip() == "!!" for code, _name, _original in plain), plain)

    def test_the_sweep_keeps_a_recovery_copy_that_changed(self):
        # A recovery copy is kept when anything inside it changed, and it is
        # removed once nothing in it has changed for the retention.
        base = Path(self.tmp.name)
        state = base / "state"
        state.mkdir()
        recovery = base / "elsewhere" / "recovered"
        recovery.mkdir(parents=True)
        (recovery / "saved.txt").write_text("saved by an editor\n", encoding="utf-8")
        cleaner._TRASH = base / "trash"
        cleaner._record_recovery(state, recovery)
        older = time.time() - 48 * 60 * 60
        # The root directory is old, but the file inside it changed now, so
        # the whole copy has to be kept.
        os.utime(recovery, (older, older))
        (recovery / "saved.txt").write_text("saved by an editor\n", encoding="utf-8")
        cleaner._sweep_recovery(state, time.time() - 24 * 60 * 60)
        self.assertTrue(recovery.exists(), "a recovery copy that changed has to be kept")
        # Nothing in it changed for the retention, so it goes. The retention
        # starts when the copy was recovered, so the recorded time is what
        # expires now.
        os.utime(recovery / "saved.txt", (older, older))
        os.utime(recovery, (older, older))
        manifest = state / "recovery.json"
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in entries:
            entry["recovered_at"] = older
        manifest.write_text(json.dumps(entries), encoding="utf-8")
        cleaner._sweep_recovery(state, time.time() - 24 * 60 * 60)
        self.assertFalse(recovery.exists(), "a copy that did not change has to go")

    def test_the_sweep_removes_links_without_following_them(self):
        # A link to a directory and a dangling link must not stop the sweep.
        base = Path(self.tmp.name)
        state = base / "state"
        state.mkdir()
        recovery = base / "elsewhere" / "recovered"
        (recovery / "sub").mkdir(parents=True)
        (recovery / "sub" / "file.txt").write_text("content\n", encoding="utf-8")
        os.symlink("sub", recovery / "link-to-dir")
        os.symlink("missing.txt", recovery / "dangling")
        older = time.time() - 48 * 60 * 60
        for entry in (recovery / "sub" / "file.txt", recovery / "link-to-dir", recovery / "dangling"):
            os.utime(entry, (older, older), follow_symlinks=False)
        os.utime(recovery / "sub", (older, older))
        os.utime(recovery, (older, older))
        cleaner._TRASH = base / "trash"
        cleaner._record_recovery(state, recovery)
        manifest = state / "recovery.json"
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in entries:
            entry["recovered_at"] = time.time() - 48 * 60 * 60
        manifest.write_text(json.dumps(entries), encoding="utf-8")
        cleaner._sweep_recovery(state, time.time() - 24 * 60 * 60)
        self.assertFalse(recovery.exists(), "the copy has to go")

    def test_the_sweep_keeps_a_copy_when_the_open_files_are_unknown(self):
        # When the open files cannot be read, the copy is kept: the sweep never
        # removes a copy it cannot show to be safe.
        base = Path(self.tmp.name)
        state = base / "state"
        state.mkdir()
        recovery = base / "elsewhere" / "recovered"
        recovery.mkdir(parents=True)
        (recovery / "saved.txt").write_text("saved\n", encoding="utf-8")
        older = time.time() - 48 * 60 * 60
        os.utime(recovery / "saved.txt", (older, older))
        os.utime(recovery, (older, older))
        cleaner._TRASH = base / "trash"
        cleaner._record_recovery(state, recovery)
        manifest = state / "recovery.json"
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in entries:
            entry["recovered_at"] = older
        manifest.write_text(json.dumps(entries), encoding="utf-8")
        original_run = cleaner.run

        def failing_lsof(argv, **kwargs):
            if argv and argv[0] == "lsof":
                raise cleaner.SafetyError("lsof_unavailable")
            return original_run(argv, **kwargs)

        with mock.patch.object(cleaner, "run", failing_lsof):
            cleaner._sweep_recovery(state, time.time() - 24 * 60 * 60)
        self.assertTrue(recovery.exists(), "a copy has to be kept when the open files are unknown")

    def test_a_held_file_keeps_the_whole_copy(self):
        # A file that a process holds open keeps the whole copy: nothing in
        # it is removed.
        base = Path(self.tmp.name)
        state = base / "state"
        state.mkdir()
        recovery = base / "elsewhere" / "recovered"
        recovery.mkdir(parents=True)
        (recovery / "first.txt").write_text("one\n", encoding="utf-8")
        (recovery / "held.txt").write_text("two\n", encoding="utf-8")
        older = time.time() - 48 * 60 * 60
        for name in ("first.txt", "held.txt"):
            os.utime(recovery / name, (older, older))
        os.utime(recovery, (older, older))
        cleaner._TRASH = base / "trash"
        cleaner._record_recovery(state, recovery)
        manifest = state / "recovery.json"
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in entries:
            entry["recovered_at"] = older
        manifest.write_text(json.dumps(entries), encoding="utf-8")
        with (recovery / "held.txt").open("r") as held:
            cleaner._sweep_recovery(state, time.time() - 24 * 60 * 60)
            self.assertTrue((recovery / "first.txt").exists(), "the whole copy has to be kept")
            self.assertTrue((recovery / "held.txt").exists())

    def test_the_sweep_moves_the_copy_and_keeps_its_names(self):
        # The copy is moved, not unlinked: every file keeps its name, so a
        # save an editor makes after the move still has a home.
        base = Path(self.tmp.name)
        state = base / "state"
        state.mkdir()
        trash = base / "trash"
        recovery = base / "elsewhere" / "recovered"
        recovery.mkdir(parents=True)
        (recovery / "saved.txt").write_text("saved\n", encoding="utf-8")
        older = time.time() - 48 * 60 * 60
        os.utime(recovery / "saved.txt", (older, older))
        os.utime(recovery, (older, older))
        cleaner._TRASH = trash
        cleaner._record_recovery(state, recovery)
        manifest = state / "recovery.json"
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in entries:
            entry["recovered_at"] = older
        manifest.write_text(json.dumps(entries), encoding="utf-8")
        cleaner._sweep_recovery(state, time.time() - 24 * 60 * 60)
        self.assertFalse(recovery.exists(), "the copy has to leave the recovery storage")
        moved = list(trash.iterdir())
        self.assertEqual(len(moved), 1, moved)
        self.assertTrue((moved[0] / "saved.txt").exists(), "every file keeps its name")

    def test_the_sweep_catches_a_link_that_appears_after_the_check(self):
        # The link appears after the copy was checked, so the move takes the
        # link and the post-move check has to catch it.
        base = Path(self.tmp.name)
        state = base / "state"
        state.mkdir()
        trash = base / "trash"
        trash.mkdir(exist_ok=True)
        recovery = base / "elsewhere" / "recovered"
        recovery.mkdir(parents=True)
        (recovery / "saved.txt").write_text("saved\n", encoding="utf-8")
        cleaner._TRASH = trash
        original_rename = os.rename

        swapped = []

        def rename_with_a_link(source, destination, *args, **kwargs):
            if str(source).endswith("recovered") and not swapped:
                swapped.append(True)
                os.rename(str(source), str(source) + "-moved")
                os.symlink(str(source) + "-moved", str(source))
            return original_rename(source, destination, *args, **kwargs)

        with mock.patch.object(cleaner.os, "rename", rename_with_a_link):
            moved = cleaner._remove_recovery_copy(recovery, time.time() + 3600)
        self.assertFalse(moved, "the move of a link is not a successful move")

    def test_the_sweep_never_moves_a_link(self):
        # A link in place of the copy is not the directory that was checked,
        # so it is not moved and the copy stays.
        base = Path(self.tmp.name)
        state = base / "state"
        state.mkdir()
        elsewhere = base / "elsewhere"
        elsewhere.mkdir()
        recovery = elsewhere / "recovered"
        recovery.mkdir()
        (recovery / "saved.txt").write_text("saved\n", encoding="utf-8")
        link = base / "copy-link"
        os.symlink(str(recovery), link)
        self.assertFalse(cleaner._remove_recovery_copy(link, time.time() + 3600))
        self.assertTrue(link.is_symlink(), "the link is not moved")
        self.assertTrue((recovery / "saved.txt").exists(), "the copy stays")

    def test_a_real_change_is_never_cleared(self):
        (self.repo / "notes.txt").write_text("real work\n", encoding="utf-8")
        records = cleaner.status_for(self.repo)
        self.assertIsNone(cleaner.clear_bootstrap_changes(self.repo, records, self.trash))
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
        github.default_branch = lambda repo, **_kwargs: "main"
        github.contains = lambda repo, base, head, **_kwargs: head == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        row = {"head": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "unpushed": 0, "remote_commit_present": True}
        self.assertTrue(cleaner.published_on_default_branch(row, github, "fixture/repo"))
        stale = {"head": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "unpushed": 0, "remote_commit_present": True}
        self.assertFalse(cleaner.published_on_default_branch(stale, github, "fixture/repo"))

    def test_unverified_default_branch_grants_nothing(self):
        github = cleaner.GitHub()
        github.default_branch = lambda repo, **_kwargs: None
        github.contains = lambda repo, base, head, **_kwargs: True
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
        github.default_branch = lambda repo, **_kwargs: "release/main"
        self.assertEqual(github.default_branch("fixture/repo"), "release/main")


if __name__ == "__main__":
    unittest.main()
