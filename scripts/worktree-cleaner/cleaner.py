#!/usr/bin/env python3

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import datetime as dt
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat

import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any

DEFAULT_CODE_ROOT = Path.home() / "Code"
DEFAULT_STATE_ROOT = Path.home() / ".local/state/mac-ops/worktree-cleaner"
T3_WORKTREE_ROOT = Path.home() / ".t3/worktrees"
ARCHIVE_ROOT = Path.home() / ".local/state/archive/worktrees"

SKIP_DIRS = {".git", "node_modules", "vendor", "Pods", ".venv", "venv", "__pycache__", "DerivedData"}
SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")

# Agent bootstrap files: the files an agent bootstrap leaves behind in a
# worktree. They are never the user's work, so they do not make a worktree
# dirty. Anything else in the tree is real work and keeps the worktree.
BOOTSTRAP_PREFIXES = (".specstory/",)
BOOTSTRAP_FILES = (".agents/legacy-instructions.md",)
AGENTS_FILE = "AGENTS.md"

# Ascend repositories are never touched by the cleaner.
ASCEND_NAMES = ("ascend", "ascend-mcp", "slash-eureka")
GITHUB_ORIGIN_RE = re.compile(r"^(?:https://(?:[^@/\s]+@)?|ssh://git@|git@)github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$")
WORKERS = 8


class SafetyError(RuntimeError):
    pass


def run(argv: list[str], *, cwd: Path | None = None, timeout: int = 30, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafetyError(f"command_unavailable:{Path(argv[0]).name}") from exc


def git(root: Path, *args: str, timeout: int = 30) -> str:
    result = run(["git", "-C", str(root), *args], timeout=timeout)
    if result.returncode != 0:
        raise SafetyError(f"git_{args[0].replace('-', '_')}_failed")
    return result.stdout


def canonical(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def inside(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((canonical(path), canonical(root))) == canonical(root)
    except ValueError:
        return False


def ascend_repo(root: Path, repo_slug: str | None = None) -> bool:
    identities = {part.casefold() for part in root.parts} | ({part.casefold() for part in repo_slug.split("/")} if repo_slug else set())
    return any(name in ASCEND_NAMES or name.startswith("ascend") for name in identities)


def srw_repo(root: Path, repo_slug: str | None = None) -> bool:
    identities = {part.casefold() for part in root.parts} | ({part.casefold() for part in repo_slug.split("/")} if repo_slug else set())
    return "srw" in identities or any(part.startswith("srw-") for part in identities) or any("strategy-replay-workbench" in part for part in identities)


def excluded_repo(root: Path, repo_slug: str | None = None) -> bool:
    parts = {part.casefold() for part in root.parts}
    remote_parts = {part.casefold() for part in repo_slug.split("/")} if repo_slug else set()
    if srw_repo(root, repo_slug):
        return True
    if ascend_repo(root, repo_slug):
        return True
    if "slash-eureka" in parts and ("dbt" in parts or "omni" in parts or root.name.casefold() == "slash-eureka"):
        return True
    if "slash-eureka" in remote_parts and remote_parts.intersection({"dbt", "omni"}):
        return True
    if any("slash-eureka" in part and (part.endswith("-dbt") or part.endswith("-omni")) for part in remote_parts):
        return True
    return False


def discover_repositories(code_root: Path) -> list[Path]:
    if not code_root.is_dir() or code_root.is_symlink():
        raise SafetyError("code_root_unavailable")
    found: set[str] = set()
    errors: list[str] = []

    def onerror(exc: OSError) -> None:
        errors.append(type(exc).__name__)

    for current, dirs, _files in os.walk(code_root, topdown=True, followlinks=False, onerror=onerror):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not (Path(current) / name).is_symlink()]
        root = Path(current)
        marker = root / ".git"
        if marker.is_dir() and not marker.is_symlink() and (marker / "HEAD").is_file():
            found.add(canonical(root))
        dirs[:] = [name for name in dirs if name != ".git"]
    if errors:
        raise SafetyError("repository_scan_incomplete")
    return [Path(item) for item in sorted(found)]


def worktrees(repo: Path) -> list[dict[str, Any]]:
    output = git_bytes(repo, "worktree", "list", "--porcelain", "-z")
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for raw in output.split(b"\0"):
        if not raw:
            if current:
                entries.append(current)
                current = {}
            continue
        field = raw.decode("utf-8", "surrogateescape")
        if field.startswith("worktree "):
            if current:
                entries.append(current)
            current = {"path": os.fsdecode(raw[len("worktree "):]), "locked": False, "detached": False, "bare": False}
        elif field == "detached":
            current["detached"] = True
        elif field == "bare":
            current["bare"] = True
        elif field.startswith("HEAD "):
            current["head"] = field[len("HEAD "):]
        elif field.startswith("branch "):
            current["branch"] = field[len("branch "):].removeprefix("refs/heads/")
        elif field.startswith("locked"):
            current["locked"] = True
        elif field.startswith("prunable"):
            current["prunable"] = True
    if not entries:
        raise SafetyError("worktree_inventory_empty")
    return entries


def status_for(path: Path) -> list[tuple[str, str, str | None]]:
    """Parse `git status --porcelain=v1 -z` into (code, path, original path).

    The records keep their status columns and are NUL separated, so a path
    that starts with a space, or that looks like a bootstrap path, cannot
    shift the columns of the record. The status is read as bytes and every
    path is decoded with `os.fsdecode`, so a file name that is not valid
    UTF-8 cannot abort the scan.
    """
    output = git_bytes(path, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = output.split(b"\0")
    records: list[tuple[str, str, str | None]] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if not field:
            continue
        code = field[:2].decode("ascii", "replace")
        name = os.fsdecode(field[3:])
        original: str | None = None
        if code[0] in "RC" or code[1] in "RC":
            original = os.fsdecode(fields[index]) if index < len(fields) else None
            index += 1
        records.append((code, name, original))
    return records


_rules_blocks: list[bytes] | None = None


def rules_blocks() -> list[bytes]:
    """The exact standing rule blocks an agent bootstrap writes, one per source."""
    global _rules_blocks
    if _rules_blocks is None:
        blocks: list[bytes] = []
        root = Path(__file__).resolve().parents[2]
        sources = [
            root / "coordinator/config/AGENT-RULES.md",
            root / "runtime/pi/AGENTS.md",
            root / "runtime/omp/AGENTS.md",
            Path.home() / ".pi/agent/AGENTS.md",
            Path.home() / ".codex/AGENTS.md",
            Path.home() / ".omp/agent/AGENTS.md",
        ]
        for source in sources:
            try:
                data = source.read_bytes()
            except OSError:
                continue
            if data.strip():
                blocks.append(data)
        _rules_blocks = blocks
    return _rules_blocks


def bootstrap_path(name: str) -> bool:
    if name in BOOTSTRAP_FILES:
        return True
    return any(name.startswith(prefix) for prefix in BOOTSTRAP_PREFIXES)


def valid_branch_name(name: str) -> bool:
    """True for a name git accepts as a branch name."""
    if not name or name.startswith("-"):
        return False
    try:
        result = run(["git", "check-ref-format", "--branch", name])
    except SafetyError:
        return False
    return result.returncode == 0


def _permitted_agents_bytes(content: bytes, committed: bytes, block: bytes) -> bool:
    """The only bytes an AGENTS.md may hold after the bootstrap: the committed
    file, or the committed file with exactly the rules block appended.

    The comparison is on bytes: the committed prefix must stay byte for byte
    intact, and a line ending change cannot hide behind a translation.
    """
    return content == committed or content == committed + block


def _kind_and_executable(meta: str) -> tuple[str, bool]:
    kind = "symlink" if meta == "120000" else "submodule" if meta == "160000" else "blob"
    return kind, meta == "100755"


def _committed_signature(repo: Path) -> tuple[str, bool] | None:
    """The type and executable bit of AGENTS.md at HEAD."""
    output = git(repo, "ls-tree", "HEAD", "--", AGENTS_FILE).strip()
    if not output:
        return None
    return _kind_and_executable(output.split()[0])


def _staged_signature(repo: Path) -> tuple[str, bool] | None:
    """The type and executable bit of AGENTS.md in the index."""
    output = git(repo, "ls-files", "-s", "--", AGENTS_FILE).strip()
    if not output:
        return None
    return _kind_and_executable(output.split()[0])


def _working_signature(path: Path) -> tuple[str, bool] | None:
    """The type and executable bit of AGENTS.md in the working copy."""
    try:
        info = path.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(info.st_mode):
        return "symlink", False
    if stat.S_ISREG(info.st_mode):
        return "blob", bool(info.st_mode & 0o111)
    return "other", False


def agents_only_rules(path: Path) -> bool:
    """True when AGENTS.md holds the committed file plus exactly the rules block.

    The file contents are compared, not a diff, so nothing can hide behind a
    line that looks like a diff marker. The staged contents are compared too:
    a genuine edit that is only staged is real work and must not be discarded.
    A part of the block, a single rule added by hand, a heading of the user's
    own, or any other edit is real work.
    """
    blocks = rules_blocks()
    if not blocks:
        return False
    working = _working_signature(path / AGENTS_FILE)
    committed = _committed_signature(path)
    staged = _staged_signature(path)
    if working is None or working[0] != "blob" or working[1]:
        # A symlink or an executable is never the bootstrap file, and reading
        # it would follow the link to whatever it points at.
        return False
    try:
        current = _read_regular(path / AGENTS_FILE)
    except OSError:
        return False
    if committed is not None and (staged is None or staged != committed or working != committed):
        return False
    if committed is None and staged is not None and staged != working:
        return False
    head: bytes | None = None
    try:
        head = git_bytes(path, "show", f"HEAD:{AGENTS_FILE}")
    except SafetyError:
        head = None
    staged_bytes: bytes | None = None
    try:
        staged_bytes = git_bytes(path, "show", f":{AGENTS_FILE}")
    except SafetyError:
        staged_bytes = None
    for block in blocks:
        if head is None:
            if staged_bytes is None:
                if current == block:
                    return True
                continue
            if staged_bytes == block and current == block:
                return True
            continue
        if staged_bytes is None:
            continue
        if not _permitted_agents_bytes(staged_bytes, head, block):
            continue
        if not _permitted_agents_bytes(current, head, block):
            continue
        return True
    return False


def classify_changes(path: Path, records: list[tuple[str, str, str | None]]) -> tuple[list[str], list[str]]:
    """Split porcelain status into bootstrap files and real work."""
    bootstrap: list[str] = []
    real: list[str] = []
    for code, name, original in records:
        if original is not None:
            if bootstrap_path(original) and bootstrap_path(name):
                bootstrap.append(name)
            else:
                real.append(f"{original} -> {name}")
            continue
        if name == AGENTS_FILE:
            only_rules = agents_only_rules(path)
            (bootstrap if only_rules else real).append(name)
            continue
        (bootstrap if bootstrap_path(name) else real).append(name)
    return bootstrap, real


def _file_bytes(path: Path) -> bytes | None:
    """The bytes of a file, or the target of a link, or None.

    A link is never read through: a relative target that resolved inside the
    worktree can dangle once the link is moved aside. A file that is not
    regular is never read, so a FIFO with no writer cannot block.
    """
    try:
        if path.is_symlink():
            return os.readlink(path).encode("utf-8", "surrogateescape")
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            return None
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(descriptor)


def _read_regular(path: Path) -> bytes | None:
    """The bytes of a regular file, read without blocking and without links.

    The file is opened without blocking and the type is checked on the same
    descriptor, so a file that was replaced by a FIFO cannot hang the scan
    and a link is never read through.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            return None
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(descriptor)


def file_digest(path: Path) -> str | None:
    """The digest of a file, or of the target of a link, or None."""
    try:
        if path.is_symlink():
            data = os.readlink(path).encode("utf-8", "surrogateescape")
        else:
            data = _read_regular(path)
    except OSError:
        return None
    if data is None:
        return None
    return hashlib.sha256(data).hexdigest()


def index_digest(repo: Path) -> str | None:
    """The digest of the index of a worktree, or None when it cannot be read."""
    try:
        listing = git(repo, "ls-files", "-s")
    except SafetyError:
        return None
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def _head_entry(repo: Path, name: str) -> tuple[str, str, bytes] | None:
    """The mode, object and bytes of a path at HEAD, or None when it has none."""
    listing = git(repo, "ls-tree", "HEAD", "--", name).strip()
    if not listing:
        return None
    meta, _, listed = listing.partition("\t")
    parts = meta.split()
    if len(parts) < 3 or parts[1] != "blob":
        return None
    try:
        data = git_bytes(repo, "show", f"HEAD:{name}")
    except SafetyError:
        return None
    return parts[0], parts[2], data


def _set_index_to_head(repo: Path, name: str, entry: tuple[str, str, bytes] | None) -> bool:
    """Point the index entry of a path back at HEAD, or drop it when HEAD has none.

    `--add` is needed because a staged addition has no entry, and so has the
    source of a rename, which git already took out of the index.
    """
    if entry is None:
        argv = ["git", "-C", str(repo), "update-index", "--force-remove", "--", name]
    else:
        mode, sha, _data = entry
        argv = ["git", "-C", str(repo), "update-index", "--add", "--cacheinfo", f"{mode},{sha},{name}"]
    return run(argv).returncode == 0


def _exclusive_write(repo: Path, relative: Path, data: bytes, mode: int) -> bool:
    """Publish bytes at a path, without overwriting anything.

    The bytes are written to a private file first and the finished file is
    published with a link, which is atomic and refuses a path that already
    exists. A save that lands at the path keeps its own file, and a save
    that lands after the publication sees a complete file.
    """
    parent = _open_parent_fd(repo, relative.parent)
    if parent is None:
        return False
    temporary: Path | None = None
    try:
        try:
            descriptor, name = tempfile.mkstemp(dir=repo / relative.parent, prefix=".cleaner-", suffix=".tmp")
        except OSError:
            return False
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, relative.name, dst_dir_fd=parent)
        return True
    except OSError:
        return False
    finally:
        os.close(parent)
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _read_at(parent: int, name: str) -> bytes | None:
    """The bytes of a file, or the target of a link, relative to a directory."""
    try:
        return os.readlink(name, dir_fd=parent).encode("utf-8", "surrogateescape")
    except OSError:
        pass
    try:
        # The file is opened without blocking, so a FIFO with no writer
        # cannot hang the cleanup, and it is checked before it is read.
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            # A FIFO, a device or a socket is never read.
            return None
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(descriptor)


def _open_parent_fd(repo: Path, relative: Path) -> int | None:
    """Open the parent directory of a path inside the worktree, without links.

    Every component is opened with `O_NOFOLLOW`, so a component that is a
    link is refused, and the descriptor is what the creation that follows
    uses, so a link that appears in between cannot redirect the write out
    of the worktree.
    """
    if relative.is_absolute() or ".." in relative.parts:
        return None
    try:
        # The root is opened without following a link, and it has to be the
        # directory the scan looked at, so a worktree directory that was
        # renamed and replaced by a link is refused.
        current = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        opened = os.fstat(current)
        at_path = os.lstat(repo)
    except OSError:
        os.close(current)
        return None
    if not stat.S_ISDIR(at_path.st_mode) or (opened.st_dev, opened.st_ino) != (at_path.st_dev, at_path.st_ino):
        os.close(current)
        return None
    for part in relative.parts:
        try:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
        except OSError:
            try:
                os.mkdir(part, 0o755, dir_fd=current)
            except OSError:
                pass
            try:
                following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            except OSError:
                os.close(current)
                return None
        os.close(current)
        current = following
    return current


def _restore_entry(repo: Path, name: str, entry: tuple[str, str, bytes]) -> bool:
    """Recreate a path from its committed bytes without replacing anything.

    The create is exclusive and relative to a directory descriptor that was
    opened without following links, so a file that appeared in the meantime
    is left alone and a link in the path cannot move the restore out of the
    worktree. A symlink is restored as a link, never as a file that holds
    the link target, and the parent directories of the path are created
    again when they are gone.
    """
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        return False
    parent = _open_parent_fd(repo, relative.parent)
    if parent is None:
        return False
    try:
        if entry[0] == "120000":
            target = entry[2].decode("utf-8", "surrogateescape")
            try:
                os.symlink(target, relative.name, dir_fd=parent)
            except OSError:
                return False
            return True
        mode = int(entry[0], 8) & 0o777
        try:
            descriptor = os.open(relative.name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode, dir_fd=parent)
        except OSError:
            return False
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(entry[2])
        return True
    finally:
        os.close(parent)


def _trash_path(trash: Path, prefix: str) -> Path:
    """A unique path in the trash, so two candidates never share a name."""
    descriptor, name = tempfile.mkstemp(dir=trash, prefix=prefix + ".", suffix=".cleaner")
    os.close(descriptor)
    return Path(name)


def _keep_moved(trash: Path, moved: Path, name: str) -> None:
    """Keep a moved file in recovery storage instead of deleting it.

    An editor can hold the file open and save through that descriptor after
    the cleaner read it, so the moved copy is the only place that save can
    live. It is kept beside the other recovery copies.
    """
    try:
        kept = _trash_path(trash, "cleared")
        os.replace(moved, kept)
    except OSError:
        pass


def _restore_link(repo: Path, relative: Path, target: bytes) -> bool:
    """Restore a link at a path, exclusively and without following links."""
    parent = _open_parent_fd(repo, relative.parent)
    if parent is None:
        return False
    try:
        try:
            os.symlink(target.decode("utf-8", "surrogateescape"), relative.name, dir_fd=parent)
        except OSError:
            return False
        return True
    finally:
        os.close(parent)


def _restore_moved(repo: Path, relative: Path, moved: Path, source: int, trash: Path) -> bool:
    """Put a moved file back at its own path, but only when that path is free.

    The create is exclusive, so a path that became occupied keeps the file
    that is there, and the copy that was moved aside is kept in the recovery
    storage. The mode of the moved file is kept as well.
    """
    data = _file_bytes(moved)
    if data is None:
        return False
    try:
        mode = moved.stat().st_mode & 0o777
    except OSError:
        mode = 0o644
    if moved.is_symlink():
        target = data.decode("utf-8", "surrogateescape")
        try:
            os.symlink(target, relative.name, dir_fd=source)
        except OSError:
            # The path is occupied, so the copy that is there stays and the
            # moved file stays in the recovery storage.
            return False
    else:
        if not _exclusive_write(repo, relative, data, mode):
            return False
    # The moved original stays in the recovery storage: an editor that still
    # has it open can finish saving into it, and that save has to survive.
    return True


def _clear_bootstrap_file(repo: Path, trash: Path, name: str, entry: tuple[str, str, bytes] | None, digest: str | None, signature: tuple[str, bool] | None = None, deleted: bool = False) -> bool:
    """Clear one verified bootstrap file without losing an intervening edit.

    The file is moved aside with an atomic rename, and the moved bytes are
    compared with the bytes that were read before the move. A write that
    landed in between is put back into a free path only, and the worktree is
    kept.
    """
    relative = Path(name)
    source = _open_parent_fd(repo, relative.parent)
    if source is None:
        return False
    try:
        expected = _read_at(source, relative.name)
        if expected is None:
            if digest is not None:
                # The scan saw this file and it is gone now, so it was deleted
                # after the scan. The deletion is kept and the cleanup stops.
                return False
            if not deleted:
                # The scan did not record this path as deleted, so the file was
                # there then and is gone now. That deletion is kept.
                return False
            # The scan recorded the deletion, so the committed bytes are
            # restored, or nothing stays when HEAD has none.
            if entry is None:
                return True
            return _restore_entry(repo, name, entry)
        if digest is None or hashlib.sha256(expected).hexdigest() != digest:
            # Either the bytes are not the ones the scan verified or the file
            # changed after the scan, so its contents are kept as real work.
            return False
        if signature is not None and _working_signature(repo / relative) != signature:
            # The file changed its type or its executable bit after the scan.
            return False
        moved = _trash_path(trash, "moved")
        try:
            storage = os.open(trash, os.O_RDONLY | os.O_DIRECTORY)
        except OSError:
            return False
        try:
            # The move is relative to the descriptor, so a parent that turned
            # into a link cannot send an unrelated file into the recovery
            # storage.
            os.replace(relative.name, moved.name, src_dir_fd=source, dst_dir_fd=storage)
        except OSError:
            # The placeholder of a move that did not happen is removed, so a
            # retry does not leave another one behind.
            try:
                moved.unlink()
            except OSError:
                pass
            return False
        finally:
            os.close(storage)
        if signature is not None and _working_signature(moved) != signature:
            # The file changed its type or its executable bit while it was
            # being cleared. It goes back to its own path when that path is
            # free, so the change stays in the worktree instead of the file
            # disappearing from it.
            _restore_moved(repo, relative, moved, source, trash)
            return False
        after = _file_bytes(moved)
        if after != expected:
            # Someone wrote the file while it was being cleared. Only a free
            # path is restored, so a save that landed in the meantime keeps
            # its own file and the recovered bytes stay beside it in the
            # trash, because the copy that would overwrite them is never
            # installed. A link is restored as a link, never as a file that
            # holds its target.
            try:
                mode = os.stat(moved).st_mode & 0o777
            except OSError:
                mode = 0o644
            if after is not None:
                if moved.is_symlink():
                    restored = _restore_link(repo, relative, after)
                else:
                    restored = _exclusive_write(repo, relative, after, mode)
                if restored:
                    _keep_moved(trash, moved, name)
            return False
        if entry is None:
            _keep_moved(trash, moved, name)
            return True
        if not _restore_entry(repo, name, entry):
            # The file came back: someone saved it, so the worktree is kept.
            _keep_moved(trash, moved, name)
            return False
        _keep_moved(trash, moved, name)
        return True
    finally:
        os.close(source)


def _reset_index_to_head(repo: Path, index_before: str | None) -> bool:
    """Reset the index of a worktree to HEAD while holding the index lock.

    The index is compared with the state the scan saw while the lock is
    held, so a staged edit that landed in between is never erased: the
    worktree is kept instead.
    """
    try:
        listed = git(repo, "rev-parse", "--git-path", "index").strip()
    except SafetyError:
        return False
    index_path = Path(listed)
    if not index_path.is_absolute():
        index_path = repo / index_path
    index_path = Path(os.path.abspath(index_path))
    # The temporary index has a name of its own, so the cleanup can only
    # remove the file it created and never a file another git client uses.
    descriptor, spare = tempfile.mkstemp(dir=index_path.parent, prefix=index_path.name + ".cleaner-", suffix=".tmp")
    os.close(descriptor)
    copy = Path(spare)
    try:
        copy.unlink()
    except OSError:
        pass
    lock = index_path.with_name(index_path.name + ".lock")
    try:
        if index_before is None:
            # The scan could not read the index, so what is staged is unknown
            # and the index is left alone.
            return False
        current = index_digest(repo)
        if current is None or current != index_before:
            return False
        result = run(["git", "-C", str(repo), "read-tree", "HEAD"], env={**os.environ, "GIT_INDEX_FILE": str(copy)})
        if result.returncode != 0 or not copy.exists():
            return False
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError:
            # Another process is updating the index, so the worktree is kept.
            return False
        os.close(descriptor)
        try:
            current = index_digest(repo)
            if current is None or current != index_before:
                return False
            os.replace(copy, index_path)
            return True
        finally:
            try:
                lock.unlink()
            except OSError:
                pass
    finally:
        if copy.exists():
            try:
                copy.unlink()
            except OSError:
                pass


def clear_bootstrap_changes(path: Path, records: list[tuple[str, str, str | None]], trash: Path, digests: dict[str, str] | None = None, index_before: str | None = None, signatures: dict[str, tuple[str, bool]] | None = None, deleted: list[str] | None = None) -> list[str] | None:
    """Clear the verified bootstrap changes of a worktree.

    Only the bootstrap files are touched, and only the ones the scan already
    verified. Every other change stays, so an unforced `git worktree remove`
    refuses to delete a worktree that holds anything else, and a file saved
    after the scan is never removed. A path the scan did not hash is kept when
    it still exists, because its bytes were never verified. When a file cannot
    be cleared without losing an edit that landed in between, the worktree is
    kept.
    """
    cleared: list[str] = []
    for code, name, original in records:
        if original is not None:
            if not (bootstrap_path(original) and bootstrap_path(name)):
                return None
            entry = _head_entry(path, original)
            if entry is None:
                return None
            if not _clear_bootstrap_file(path, trash, original, entry, (digests or {}).get(original), (signatures or {}).get(original), original in (deleted or [])):
                return None
            if not _clear_bootstrap_file(path, trash, name, None, (digests or {}).get(name), (signatures or {}).get(name), name in (deleted or [])):
                return None
            cleared.append(name)
            continue
        if name == AGENTS_FILE:
            if not agents_only_rules(path):
                return None
        elif not bootstrap_path(name):
            return None
        entry = _head_entry(path, name)
        if not _clear_bootstrap_file(path, trash, name, entry, (digests or {}).get(name), (signatures or {}).get(name), name in (deleted or [])):
            return None
        cleared.append(name)
    if not _reset_index_to_head(path, index_before):
        return None
    return cleared


def detached_idle_seconds(path: Path) -> int | None:
    marker = path / ".git"
    if marker.is_symlink() or not marker.is_file():
        return None
    value = marker.read_text(encoding="utf-8").strip()
    if not value.startswith("gitdir: "):
        return None
    admin = Path(value[len("gitdir: "):])
    if not admin.is_absolute():
        admin = path / admin
    admin = admin.resolve()
    common = Path(git(path, "rev-parse", "--git-common-dir").strip())
    if not common.is_absolute():
        common = path / common
    if admin.parent.resolve() != (common.resolve() / "worktrees"):
        return None
    log = admin / "logs/HEAD"
    if log.is_symlink() or not log.is_file():
        return None
    stamps: list[int] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        fields = line.partition("\t")[0].split()
        if len(fields) >= 4 and fields[-2].isdigit():
            stamps.append(int(fields[-2]))
    return int(time.time()) - max(stamps) if stamps else None


PROTECTED_REASONS = {"main_checkout", "worktree_outside_scope", "t3_thread_unfinished", "process_cwd_inside", "worktree_locked"}
process_cwd_cache: list[Path] = []


def process_cwds(*, refresh: bool = False) -> list[Path]:
    if refresh or not process_cwd_cache:
        result = run(["lsof", "-d", "cwd", "-Fn"])
        if not result.stdout:
            raise SafetyError("process_cwd_unavailable")
        fresh = [Path(line[1:]) for line in result.stdout.splitlines() if line.startswith("n/")]
        process_cwd_cache[:] = fresh
        return fresh
    return process_cwd_cache


def cwd_held(path: Path) -> bool:
    try:
        return any(inside(holder, path) for holder in process_cwds(refresh=True))
    except SafetyError:
        return True


def branch_exists(repo: Path, branch: str | None) -> bool:
    return bool(branch) and run(["git", "-C", str(repo), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]).returncode == 0


def prunable(row: dict[str, Any], github: GitHub) -> bool:
    repo = Path(row["repo"])
    reasons = set(row["reasons"])
    return (
        row["gone"] and not row["locked"] and not row["main_checkout"]
        and not reasons & {"worktree_outside_scope", "t3_thread_unfinished", "repository_outside_code_root", "process_cwd_inside", "worktree_status_unknown"}
        and Path(row["path"]).parent.is_dir()
        and github.repo(repo) is not None
        and (row["remote_commit_present"] is True or branch_exists(repo, row["branch"]))
    )


def created_seconds_ago(path: Path) -> int | None:
    try:
        stat = (path / ".git").stat()
    except OSError:
        return None
    return int(time.time() - getattr(stat, "st_birthtime", stat.st_mtime))


def unpushed_commits(path: Path) -> int | None:
    try:
        return int(git(path, "rev-list", "--count", "HEAD", "--not", "--remotes").strip())
    except (SafetyError, ValueError):
        return None


def categorize(row: dict[str, Any]) -> str:
    if row.get("removed"):
        return "removed"
    if row["eligible"]:
        return "safe"
    reasons = set(row["reasons"])
    if row["prunable"]:
        return "prune"
    if reasons & PROTECTED_REASONS:
        return "protected"
    return "look"


class T3State:
    PAGE_LIMIT = 100
    MAX_PAGES = 1000
    worktree_cache: dict[str, tuple[str, str | None]] = {}

    SNAPSHOT_ATTEMPTS = 5
    SNAPSHOT_PAUSE_SECONDS = 1

    def __init__(self):
        for attempt in range(self.SNAPSHOT_ATTEMPTS):
            try:
                self._read_threads()
                first_safety = self._safety_view()
                first_pages = self.page_count
                self._read_threads()
                if self._safety_view() == first_safety:
                    self.page_count += first_pages
                    return
            except SafetyError as exc:
                if str(exc) != "t3_list_changed":
                    raise
            if attempt + 1 < self.SNAPSHOT_ATTEMPTS:
                time.sleep(self.SNAPSHOT_PAUSE_SECONDS * 2**attempt)
        raise SafetyError("t3_list_changed")

    def _safety_view(self) -> frozenset[tuple[str, str | None]]:
        return frozenset((thread_id, worktree) for thread_id, (_, worktree) in self.records.items())

    @staticmethod
    def _call(tool: str, args: dict[str, Any]) -> Any:
        result = run(["t3mcp", "call", tool, json.dumps(args)])
        if result.returncode != 0:
            raise SafetyError("t3_unavailable")
        try:
            return json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise SafetyError("t3_response_invalid") from exc

    def _read_threads(self) -> None:
        self.records: dict[str, tuple[str, str | None]] = {}
        self.paths: list[tuple[Path, str]] = []
        self.thread_count = 0
        self.page_count = 0
        listed: list[tuple[str, str]] = []
        cursor = 0
        total: int | None = None
        while self.page_count < self.MAX_PAGES:
            page = self._call("t3_thread_list", {"allProjects": True, "settled": False, "limit": self.PAGE_LIMIT, "cursor": cursor})
            rows = page.get("threads") if isinstance(page, dict) else None
            page_total = page.get("total") if isinstance(page, dict) else None
            if not isinstance(rows, list) or len(rows) > self.PAGE_LIMIT or type(page_total) is not int or page_total < 0:
                raise SafetyError("t3_list_invalid")
            if total is not None and page_total != total:
                raise SafetyError("t3_list_changed")
            total = page_total
            self.page_count += 1
            for thread in rows:
                thread_id = thread.get("threadId") if isinstance(thread, dict) else None
                if not isinstance(thread_id, str) or not thread_id or thread_id in {seen for seen, _ in listed}:
                    raise SafetyError("t3_list_duplicate_or_invalid_thread")
                updated_at = thread.get("updatedAt")
                if thread.get("settled") is not False or not isinstance(updated_at, str) or not updated_at:
                    raise SafetyError("t3_thread_invalid")
                listed.append((thread_id, updated_at))
            next_cursor = page.get("nextCursor")
            if next_cursor is None:
                if len(listed) != total:
                    raise SafetyError("t3_list_incomplete")
                break
            if not rows or type(next_cursor) is not int or next_cursor != cursor + len(rows) or len(listed) >= total:
                raise SafetyError("t3_list_incomplete")
            cursor = next_cursor
        else:
            raise SafetyError("t3_list_incomplete")
        for thread_id, updated_at in listed:
            cached = self.worktree_cache.get(thread_id)
            if cached is None or cached[0] != updated_at:
                read = self._call("t3_thread_read", {"threadId": thread_id, "limit": 1})
                thread = read.get("thread") if isinstance(read, dict) else None
                if not isinstance(thread, dict) or thread.get("threadId") != thread_id or "worktreePath" not in thread:
                    raise SafetyError("t3_thread_path_unverified")
                worktree = thread["worktreePath"]
                if worktree is not None and (not isinstance(worktree, str) or not worktree or "\0" in worktree or not Path(worktree).is_absolute()):
                    raise SafetyError("t3_thread_path_invalid")
                cached = self.worktree_cache[thread_id] = (updated_at, worktree and canonical(worktree))
            self.records[thread_id] = cached
            if cached[1]:
                self.paths.append((Path(cached[1]), thread_id))
        self.thread_count = len(listed)

    def users(self, path: Path) -> list[str]:
        return sorted({thread_id for thread_path, thread_id in self.paths if inside(thread_path, path)})

    def blockers(self, path: Path) -> list[str]:
        return ["t3_thread_unfinished"] if self.users(path) else []


class GitHub:
    def __init__(self):
        self.repos: dict[str, str | None] = {}
        self.commits: dict[tuple[str, str], bool] = {}
        self.pull_requests: dict[tuple[str, str, str], list[dict[str, Any]] | None] = {}
        self.default_branches: dict[str, str | None] = {}
        self.contained: dict[tuple[str, str, str], bool] = {}
        self.commit_pulls: dict[tuple[str, str], list[dict[str, Any]] | None] = {}

    def contains(self, repo: str, base: str, head: str, *, refresh: bool = False) -> bool:
        """True when GitHub says the head commit is contained in the base."""
        key = (repo, base, head)
        if key in self.contained and not refresh:
            return self.contained[key]
        try:
            result = run(["gh", "api", f"repos/{repo}/compare/{base}...{head}", "--jq", ".status"])
        except SafetyError:
            result = None
        status = result.stdout.strip() if result and result.returncode == 0 else ""
        self.contained[key] = status in {"behind", "identical"}
        return self.contained[key]

    def pulls_for_commit(self, repo: str, head: str, *, refresh: bool = False) -> list[dict[str, Any]] | None:
        """The pull requests that carry a commit, whatever the branch is called."""
        key = (repo, head)
        if key in self.commit_pulls and not refresh:
            return self.commit_pulls[key]
        try:
            result = run([
                "gh", "api", f"repos/{repo}/commits/{head}/pulls",
                "--jq", "[.[] | {number: .number, state: .state, merged: .merged_at, headSha: .head.sha}]",
            ])
        except SafetyError:
            result = None
        if result is None or result.returncode != 0:
            self.commit_pulls[key] = None
            return None
        try:
            rows = json.loads(result.stdout)
        except (ValueError, json.JSONDecodeError):
            self.commit_pulls[key] = None
            return None
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            self.commit_pulls[key] = None
            return None
        self.commit_pulls[key] = rows
        return rows

    def default_branch(self, repo: str | None, *, refresh: bool = False) -> str | None:
        """The one default branch of the repository, or None when unknown."""
        if not repo:
            return None
        if repo in self.default_branches and not refresh:
            return self.default_branches[repo]
        try:
            result = run([
                "gh", "repo", "view", repo, "--json", "defaultBranchRef",
                "--jq", ".defaultBranchRef.name",
            ])
        except SafetyError:
            result = None
        name = result.stdout.strip() if result and result.returncode == 0 else ""
        if not valid_branch_name(name):
            name = ""
        self.default_branches[repo] = name or None
        return self.default_branches[repo]

    def repo(self, root: Path, *, refresh: bool = False) -> str | None:
        key = canonical(root)
        if key in self.repos and not refresh:
            return self.repos[key]
        try:
            origin = run(["git", "-C", str(root), "remote", "get-url", "origin"])
        except SafetyError:
            origin = None
        matched = GITHUB_ORIGIN_RE.fullmatch(origin.stdout.strip()) if origin and origin.returncode == 0 else None
        if matched and re.fullmatch(r"[^/\s]+/[^/\s]+", matched.group(1)):
            self.repos[key] = matched.group(1)
            return self.repos[key]
        try:
            result = run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], cwd=root)
        except SafetyError:
            result = None
        value = result.stdout.strip() if result else ""
        if result is None or result.returncode != 0 or not re.fullmatch(r"[^/\s]+/[^/\s]+", value):
            self.repos[key] = None
        else:
            self.repos[key] = value
        return self.repos[key]

    def commit_present(self, repo: str, sha: str, *, refresh: bool = False) -> bool:
        key = (repo, sha.lower())
        if key in self.commits and not refresh:
            return self.commits[key]
        if not SHA_RE.fullmatch(sha):
            self.commits[key] = False
            return False
        try:
            result = run(["gh", "api", f"repos/{repo}/commits/{sha}", "--jq", ".sha"])
            self.commits[key] = result.returncode == 0 and result.stdout.strip().lower() == sha.lower()
        except SafetyError:
            self.commits[key] = False
        return self.commits[key]

    def prs(self, repo: str, branch: str, *, refresh: bool = False) -> list[dict[str, Any]] | None:
        owner = repo.split("/", 1)[0]
        key = (repo, owner, branch)
        if key in self.pull_requests and not refresh:
            return self.pull_requests[key]
        try:
            result = run([
                "gh", "pr", "list", "--repo", repo, "--head", branch,
                "--state", "all", "--limit", "1000", "--json", "number,state,headRefName,headRefOid",
            ])
        except SafetyError:
            result = None
        if result is None or result.returncode != 0:
            self.pull_requests[key] = None
        else:
            try:
                value = json.loads(result.stdout)
                if not isinstance(value, list) or len(value) >= 1000 or any(not isinstance(row, dict) for row in value):
                    raise ValueError
                self.pull_requests[key] = value
            except (ValueError, json.JSONDecodeError):
                self.pull_requests[key] = None
        return self.pull_requests[key]


def verify_pr(github: GitHub, repo: str | None, branch: str | None, head: str, *, refresh: bool = False) -> tuple[bool, str | None, str | None]:
    if not repo or not branch:
        return False, "github_repository_unknown", None
    prs = github.prs(repo, branch, refresh=refresh)
    if prs is None:
        return False, "github_pr_state_unavailable", None
    matching = [row for row in prs if row.get("headRefName") == branch]
    if any(str(row.get("state", "")).upper() == "OPEN" for row in matching):
        return False, "github_pr_open", None
    closed = [row for row in matching if str(row.get("state", "")).upper() in {"CLOSED", "MERGED"} and str(row.get("headRefOid", "")).lower() == head.lower()]
    if not closed:
        return False, "github_pr_not_closed_for_head", None
    row = closed[-1]
    return True, None, f"https://github.com/{repo}/pull/{row.get('number')}"


def published_on_default_branch(result: dict[str, Any], github: GitHub, repo_slug: str | None, *, refresh: bool = False) -> bool:
    """True when every commit of the worktree is already on the default branch.

    The ancestry is decided by GitHub, against the current tip of the default
    branch it reports. A local tracking ref can still hold the candidate
    after a force push, while the default branch does not contain it.
    """
    head = str(result.get("head") or "")
    if not SHA_RE.fullmatch(head):
        return False
    if result.get("remote_commit_present") is not True:
        return False
    if not repo_slug:
        return False
    default = github.default_branch(repo_slug, refresh=refresh)
    if not default:
        return False
    return github.contains(repo_slug, default, head, refresh=refresh)


def verify_pr_for_head(github: GitHub, repo_slug: str | None, repo_root: Path, head: str, *, refresh: bool = False) -> tuple[bool, str | None, str | None]:
    """True when a closed or merged pull request carries this exact head.

    A detached worktree has no branch of its own, so the branches that
    contain the head are looked up and each of them is checked.
    """
    if not repo_slug or not SHA_RE.fullmatch(head):
        return False, "github_repository_unknown", None
    try:
        listing = git(repo_root, "branch", "-r", "--contains", head, "--format=%(refname:short)").splitlines()
    except SafetyError:
        listing = []
    for line in listing:
        branch = line.strip().removeprefix("origin/")
        if not branch:
            continue
        ok, why, pr_url = verify_pr(github, repo_slug, branch, head, refresh=refresh)
        if ok:
            return True, None, pr_url
    # The branch of the pull request may be gone, so the pull requests of the
    # commit itself are asked for as well.
    for row in github.pulls_for_commit(repo_slug, head, refresh=refresh) or []:
        if str(row.get("headSha", "")).lower() != head.lower():
            continue
        if str(row.get("state", "")).upper() != "CLOSED":
            continue
        return True, None, f"https://github.com/{repo_slug}/pull/{row.get('number')}"
    return False, "github_pr_not_closed_for_head", None


def _trash_for(state_trash: Path, worktree: Path) -> Path:
    """The recovery storage to use for a worktree.

    It has to be on the same filesystem as the worktree, so that moving a
    file into it is a rename and not a copy across two volumes.
    """
    try:
        if state_trash.is_dir() and os.stat(state_trash).st_dev == os.stat(worktree).st_dev:
            return state_trash
    except OSError:
        pass
    try:
        return Path(tempfile.mkdtemp(prefix=".worktree-cleaner-", dir=worktree.parent))
    except OSError:
        return state_trash


def _claim_head_lock(path: Path) -> Path | None:
    """Claim the lock of the head of a worktree, or None when it is taken.

    A commit in the worktree has to update that head, so it cannot run
    while the lock is held. The removal therefore runs with the head it
    checked still in place.
    """
    try:
        listed = git(path, "rev-parse", "--git-path", "HEAD").strip()
    except SafetyError:
        return None
    head = Path(listed)
    if not head.is_absolute():
        head = path / head
    head = Path(os.path.abspath(head))
    lock = head.with_name(head.name + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        return None
    os.close(descriptor)
    return lock


def _head_matches(path: Path, expected: str) -> bool:
    """True when the worktree still points at the commit that was checked."""
    try:
        head = git(path, "rev-parse", "HEAD").strip()
    except SafetyError:
        return False
    return head.lower() == expected.lower()


def evaluate(repo_root: Path, record: dict[str, Any], code_root: Path, github: GitHub, t3_state: T3State, *, refresh: bool = False, refresh_cwds: bool = True) -> dict[str, Any]:
    path = Path(record["path"])
    result: dict[str, Any] = {
        "repo": str(repo_root), "path": str(path), "branch": record.get("branch"),
        "head": record.get("head"), "detached": bool(record.get("detached")),
        "main_checkout": canonical(path) == canonical(repo_root), "dirty": None,
        "uncommitted": None, "unpushed": None, "age_seconds": created_seconds_ago(path),
        "gone": not path.is_dir(), "locked": bool(record.get("locked")), "prunable": False,
        "remote_commit_present": None, "pull_request": None, "eligible": False, "reasons": [],
    }
    reasons = t3_state.blockers(path)
    result["t3_threads"] = t3_state.users(path)
    if not inside(repo_root, code_root):
        reasons.append("repository_outside_code_root")
    if result["main_checkout"] or record.get("bare"):
        reasons.append("main_checkout")
    if not any(inside(path, root) for root in (code_root / ".worktrees", repo_root / ".claude/worktrees", T3_WORKTREE_ROOT, Path("/private/tmp"), Path("/tmp"))):
        reasons.append("worktree_outside_scope")
    if any(reason != "t3_thread_unfinished" for reason in reasons):
        result["reasons"] = reasons
        return result
    if any(inside(holder, path) for holder in process_cwds(refresh=refresh and refresh_cwds)):
        reasons.append("process_cwd_inside")
    if record.get("locked"):
        reasons.append("worktree_locked")
    if record.get("prunable") or not path.is_dir():
        reasons.append("worktree_missing_or_prunable")
    if not SHA_RE.fullmatch(str(record.get("head") or "")):
        reasons.append("head_unknown")
    if path.is_dir():
        try:
            root = Path(git(path, "rev-parse", "--show-toplevel").strip())
            if canonical(root) != canonical(path):
                reasons.append("worktree_root_mismatch")
            records = status_for(path)
            bootstrap_changes, real_changes = classify_changes(path, records)
            result["bootstrap_changes"] = bootstrap_changes
            result["bootstrap_digests"] = {name: file_digest(path / name) for name in bootstrap_changes}
            result["deleted_at_scan"] = [name for code, name, original in records if original is None and "D" in code] + [original for code, name, original in records if original is not None]
            result["bootstrap_signatures"] = {name: _working_signature(path / name) for name in bootstrap_changes}
            result["index_digest"] = index_digest(path)
            result["dirty"] = bool(real_changes)
            result["uncommitted"] = len(real_changes)
            result["unpushed"] = unpushed_commits(path)
            if real_changes:
                reasons.append("worktree_dirty")
        except SafetyError:
            reasons.append("worktree_status_unknown")
    repo_slug = github.repo(repo_root, refresh=refresh)
    if not repo_slug:
        reasons.append("github_repository_unknown")
    elif SHA_RE.fullmatch(str(record.get("head") or "")):
        present = github.commit_present(repo_slug, record["head"], refresh=refresh)
        result["remote_commit_present"] = present
        if not present:
            reasons.append("remote_commit_unverified")
    if record.get("detached"):
        try:
            idle = detached_idle_seconds(path) if path.is_dir() else None
        except SafetyError:
            idle = None
        result["detached_idle_seconds"] = idle
        if published_on_default_branch(result, github, repo_slug, refresh=refresh):
            result["published_on_default_branch"] = True
            result["eligible_reason"] = "commits_on_the_default_branch"
        else:
            # Inactivity alone never authorises the removal of a detached
            # worktree: its head has to be published, either on the default
            # branch or through a closed or merged pull request.
            ok, why, pr_url = verify_pr_for_head(github, repo_slug, repo_root, str(record.get("head") or ""), refresh=refresh)
            if ok:
                result["pull_request"] = pr_url
                result["eligible_reason"] = "merged_or_closed_pull_request"
            else:
                reasons.append("detached_not_published")
    elif not result["main_checkout"]:
        ok, why, pr_url = verify_pr(github, repo_slug, record.get("branch"), str(record.get("head") or ""), refresh=refresh)
        result["pull_request"] = pr_url
        if not ok and why:
            if why == "github_pr_not_closed_for_head" and published_on_default_branch(result, github, repo_slug, refresh=refresh):
                result["published_on_default_branch"] = True
                result["eligible_reason"] = "commits_on_the_default_branch"
            else:
                reasons.append(why)
        else:
            result["eligible_reason"] = "merged_or_closed_pull_request"
    result["reasons"] = sorted(set(reasons))
    result["eligible"] = not result["reasons"]
    result["prunable"] = prunable(result, github)
    return result


def excluded_row(repo_root: Path, record: dict[str, Any], reason: str, t3_state: T3State) -> dict[str, Any]:
    path = Path(record["path"])
    row: dict[str, Any] = {
        "repo": str(repo_root), "path": str(path), "branch": record.get("branch"), "reason": reason,
        "gone": not path.is_dir(), "age_seconds": created_seconds_ago(path), "dirty": None,
        "uncommitted": None, "t3_threads": t3_state.users(path),
    }
    if not row["gone"]:
        try:
            records = status_for(path)
            _bootstrap, real = classify_changes(path, records)
            row["dirty"] = bool(real)
            row["uncommitted"] = len(real)
        except SafetyError:
            pass
    return row


def inventory(code_root: Path, github: GitHub, t3_state: T3State) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    excluded = 0
    process_cwds()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        excluded_futures = []
        row_futures = []
        for repo_root in discover_repositories(code_root):
            repo_slug = github.repo(repo_root)
            if excluded_repo(repo_root, repo_slug):
                excluded += 1
                reason = "SRW repository" if srw_repo(repo_root, repo_slug) else "Ascend repository" if ascend_repo(repo_root, repo_slug) else "Slash dbt or omni repository"
                excluded_futures.extend(pool.submit(excluded_row, repo_root, record, reason, t3_state) for record in worktrees(repo_root) if canonical(record["path"]) != canonical(repo_root))
                continue
            records = worktrees(repo_root)
            for record in records:
                row_futures.append(pool.submit(evaluate, repo_root, record, code_root, github, t3_state))
        rows = [future.result() for future in row_futures]
        excluded_rows = [future.result() for future in excluded_futures]
    return rows, excluded, excluded_rows


def report_day() -> str:
    return dt.datetime.now().astimezone().date().isoformat()


def secure_state_dir(path: Path) -> Path:
    path = path.expanduser()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise SafetyError("unsafe_state_directory")
    return path


def atomic_write(path: Path, value: str) -> None:
    fd, name = tempfile.mkstemp(prefix=".worktree-cleaner-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_daily_report(code_root: Path, rows: list[dict[str, Any]], summary: dict[str, Any], dry_run: bool) -> Path:
    day = report_day()
    flagged = [row for row in rows if not row["main_checkout"] and "worktree_outside_scope" not in row["reasons"] and (row.get("dirty") is not False or row.get("remote_commit_present") is not True)]
    lines = [
        f"# Dirty and unverified worktrees, {day}",
        "",
        f"Last scan: {dt.datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Mode: {'dry-run' if dry_run else 'apply'}",
        "",
        "## Counts",
        "",
        f"- Repositories scanned: {summary['repositories_scanned']}",
        f"- Worktrees scanned: {summary['worktrees_scanned']}",
        f"- Eligible: {summary['eligible']}",
        f"- Removed: {summary['removed']}",
        f"- Excluded repositories: {summary['excluded_repositories']}",
        "",
        "## Dirty or unverified worktrees",
        "",
    ]
    if not flagged:
        lines.append("No dirty worktrees or commits missing remote proof were found.")
    for row in flagged:
        state = "dirty" if row.get("dirty") is True else "clean" if row.get("dirty") is False else "status unverified"
        if row.get("remote_commit_present") is not True:
            state += ", remote commit unverified"
        lines.append(f"- `{row['path']}` ({row['branch'] or 'detached'}, {state})")
        if row.get("reasons"):
            lines.append(f"  Reasons: {', '.join(row['reasons'])}")
    lines.extend(["", "## T3-held worktrees", ""])
    for row in rows:
        if row.get("t3_threads"):
            lines.append(f"- `{row['path']}`: {', '.join(row['t3_threads'])}")
    report_dir = code_root / "coordinator" / "evidence"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"worktrees-kept-{day}.md"
    atomic_write(path, "\n".join(lines) + "\n")
    return path


def append_removal(state_root: Path, row: dict[str, Any], event: str, extra: dict[str, Any] | None = None) -> None:
    path = state_root.parent / "worktree-cleaner.log"
    if path.is_symlink():
        raise SafetyError("unsafe_removal_log")
    entry = {
        "event": event,
        "removed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo": row["repo"], "path": row["path"], "branch": row["branch"],
        "head": row["head"], "pull_request": row["pull_request"],
        "reason": "clean, remote commit verified, no live T3 thread, and the eligibility rule that authorised the removal",
        "eligible_reason": row.get("eligible_reason"),
        "bootstrap_changes": row.get("bootstrap_changes", []),
        "published_on_default_branch": bool(row.get("published_on_default_branch")),
        **(extra or {}),
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as output:
        output.write(json.dumps(entry, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())


@contextlib.contextmanager
def cleaner_lock(state_root: Path):
    lock_path = state_root / "cleaner.lock"
    if lock_path.is_symlink():
        raise SafetyError("unsafe_lock_file")
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SafetyError("cleaner_already_running") from exc
        yield


def scan(code_root: Path, state_root: Path, apply: bool, report: bool = True, prune: bool = False) -> dict[str, Any]:
    state_root = secure_state_dir(state_root)
    with cleaner_lock(state_root):
        initial_state = T3State()
        github = GitHub()
        rows, excluded, excluded_rows = inventory(code_root, github, initial_state)
        eligible = [row for row in rows if row["eligible"]]
        removed = 0
        if apply:
            def refreshed(candidate: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | SafetyError | None]:
                repo_root = Path(candidate["repo"])
                current = next((r for r in worktrees(repo_root) if canonical(r["path"]) == canonical(candidate["path"])), None)
                if current is None:
                    return None, None
                try:
                    return current, evaluate(repo_root, current, code_root, github, T3State(), refresh=True)
                except SafetyError as exc:
                    return current, exc

            with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
                checks = list(pool.map(refreshed, eligible))
            for candidate, (current, final) in zip(eligible, checks):
                repo_root = Path(candidate["repo"])
                if current is None:
                    candidate["eligible"] = False
                    candidate["reasons"] = ["worktree_registration_changed"]
                    continue
                if isinstance(final, SafetyError):
                    candidate["eligible"] = False
                    candidate["reasons"] = [str(final)]
                    continue
                if current.get("head") != candidate.get("head") or current.get("branch") != candidate.get("branch"):
                    final["eligible"] = False
                    final["reasons"] = sorted(set(final["reasons"] + ["worktree_changed_after_scan"]))
                if not final["eligible"]:
                    candidate.update(final)
                    continue
                try:
                    latest_head = git(Path(candidate["path"]), "rev-parse", "HEAD").strip()
                    latest_records = status_for(Path(candidate["path"]))
                    _bootstrap, latest_real = classify_changes(Path(candidate["path"]), latest_records)
                except SafetyError:
                    latest_head = ""
                    latest_records = []
                    latest_real = ["worktree_status_unknown"]
                if latest_head.lower() != str(candidate["head"]).lower() or latest_real:
                    candidate["eligible"] = False
                    candidate["reasons"] = ["worktree_changed_before_remove"]
                    continue
                append_removal(state_root, candidate, "removal_attempted")
                try:
                    latest_state = T3State()
                    candidate["t3_threads"] = latest_state.users(Path(candidate["path"]))
                    blockers = latest_state.blockers(Path(candidate["path"]))
                except SafetyError as exc:
                    blockers = [str(exc)]
                if blockers:
                    candidate["eligible"] = False
                    candidate["reasons"] = blockers
                    append_removal(state_root, candidate, "removal_blocked")
                    continue
                try:
                    latest_head = git(Path(candidate["path"]), "rev-parse", "HEAD").strip()
                    latest_records = status_for(Path(candidate["path"]))
                    _bootstrap, latest_real = classify_changes(Path(candidate["path"]), latest_records)
                except SafetyError:
                    latest_head = ""
                    latest_records = []
                    latest_real = ["worktree_status_unknown"]
                if latest_head.lower() != str(candidate["head"]).lower() or latest_real:
                    candidate["eligible"] = False
                    candidate["reasons"] = ["worktree_changed_before_remove"]
                    append_removal(state_root, candidate, "removal_blocked")
                    continue
                if cwd_held(Path(candidate["path"])):
                    append_removal(state_root, candidate, "removal_blocked")
                    candidate["eligible"] = False
                    candidate["reasons"] = ["process_cwd_inside"]
                    continue
                trash = state_root / "cleanup-trash"
                try:
                    trash.mkdir(mode=0o700, parents=True, exist_ok=True)
                except OSError:
                    trash = None
                if trash is not None:
                    trash = _trash_for(trash, Path(candidate["path"]))
                try:
                    cleared = clear_bootstrap_changes(Path(candidate["path"]), latest_records, trash, candidate.get("bootstrap_digests"), candidate.get("index_digest"), candidate.get("bootstrap_signatures"), candidate.get("deleted_at_scan")) if trash else None
                except (SafetyError, OSError):
                    cleared = None
                if cleared is None:
                    candidate["eligible"] = False
                    candidate["reasons"] = ["bootstrap_clear_failed"]
                    append_removal(state_root, candidate, "removal_blocked")
                    continue
                candidate["cleared_bootstrap_changes"] = cleared
                # The head is checked again after the cleanup, so a commit
                # made in between stops the removal: git would see a clean
                # worktree and remove it, and the new commit would be lost.
                lock = _claim_head_lock(Path(candidate["path"]))
                if lock is None:
                    candidate["eligible"] = False
                    candidate["reasons"] = ["worktree_head_locked"]
                    append_removal(state_root, candidate, "removal_blocked")
                    continue
                try:
                    if not _head_matches(Path(candidate["path"]), str(candidate["head"])):
                        candidate["eligible"] = False
                        candidate["reasons"] = ["worktree_head_changed_before_remove"]
                        append_removal(state_root, candidate, "removal_blocked")
                        continue
                    try:
                        result = run(["git", "-C", str(repo_root), "worktree", "remove", candidate["path"]], timeout=300)
                    except SafetyError:
                        result = None
                finally:
                    if lock.exists():
                        try:
                            lock.unlink()
                        except OSError:
                            pass
                if result is None:
                    append_removal(state_root, candidate, "removal_outcome_unknown")
                    candidate["eligible"] = False
                    candidate["reasons"] = ["worktree_remove_outcome_unknown"]
                    continue
                if result.returncode != 0 or Path(candidate["path"]).exists():
                    append_removal(state_root, candidate, "removal_failed")
                    candidate["eligible"] = False
                    candidate["reasons"] = ["worktree_remove_failed"]
                    continue
                append_removal(state_root, candidate, "removed")
                candidate["eligible"] = False
                candidate["removed"] = True
                removed += 1
        prune_results: list[dict[str, Any]] = []
        if apply and removed:
            for repo_root in sorted({str(row["repo"]) for row in rows if row.get("removed")}):
                try:
                    result = run(["git", "-C", repo_root, "worktree", "prune"], timeout=300)
                    prune_results.append({"repo": repo_root, "ok": result.returncode == 0, "error": None if result.returncode == 0 else result.stderr.strip()[:400]})
                except SafetyError as exc:
                    prune_results.append({"repo": repo_root, "ok": False, "error": str(exc)})
        for row in rows:
            row["category"] = categorize(row)
        pruned = 0
        if apply and prune:
            def prune_check(row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
                repo_root = Path(row["repo"])
                current = next((r for r in worktrees(repo_root) if canonical(r["path"]) == canonical(row["path"])), None)
                if current is None:
                    return None, None
                try:
                    return current, evaluate(repo_root, current, code_root, github, T3State(), refresh=True)
                except SafetyError:
                    return current, None

            prune_rows = [r for r in rows if r["category"] == "prune"]
            with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
                prune_checks = list(pool.map(prune_check, prune_rows))
            for row, (current, final) in zip(prune_rows, prune_checks):
                repo_root = Path(row["repo"])
                if current is None or final is None:
                    continue
                if not final["prunable"] or current.get("head") != row.get("head"):
                    continue
                append_removal(state_root, row, "prune_attempted")
                if run(["git", "-C", str(repo_root), "worktree", "remove", row["path"]]).returncode != 0:
                    append_removal(state_root, row, "prune_failed")
                    continue
                append_removal(state_root, row, "pruned")
                row["category"] = "removed"
                pruned += 1
        summary = {
            "mode": "apply" if apply else "dry-run",
            "repositories_scanned": len({row["repo"] for row in rows}),
            "worktrees_scanned": len(rows),
            "eligible": sum(1 for row in rows if row["eligible"]),
            "removed": removed,
            "pruned": pruned,
            "prune_results": prune_results,
            "categories": {name: sum(1 for row in rows if row["category"] == name and not row["main_checkout"]) for name in ("safe", "look", "protected", "prune", "removed")},
            "excluded_worktrees": len(excluded_rows),
            "excluded_rows": excluded_rows,
            "held": sum(1 for row in rows if not row["eligible"] and not row.get("removed")),
            "excluded_repositories": excluded,
            "held_reasons": {},
            "t3_threads_scanned": initial_state.thread_count,
            "t3_pages_scanned": initial_state.page_count,
        }
        summary["per_repo"] = {}
        for row in rows:
            if not row["main_checkout"]:
                counts = summary["per_repo"].setdefault(row["repo"], {"would_remove": 0, "kept_dirty": 0, "kept_unpushed": 0, "in_use": 0})
                counts["would_remove"] += int(row["eligible"])
                counts["kept_dirty"] += int(row["dirty"] is True)
                counts["kept_unpushed"] += int(row["remote_commit_present"] is False)
                counts["in_use"] += int(any(reason in row["reasons"] for reason in ("t3_thread_unfinished",)))
            for reason in row.get("reasons", []):
                summary["held_reasons"][reason] = summary["held_reasons"].get(reason, 0) + 1
        if report:
            summary["daily_report"] = str(write_daily_report(code_root, rows, summary, dry_run=not apply))
        summary["rows"] = rows
        return summary


def registrations(code_root: Path, github: GitHub) -> dict[str, tuple[Path, dict[str, Any]]]:
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    for repo_root in discover_repositories(code_root):
        if excluded_repo(repo_root, github.repo(repo_root)):
            continue
        for record in worktrees(repo_root):
            found.setdefault(canonical(record["path"]), (repo_root, record))
    return found


def pin_head(repo_root: Path, name: str, checkout: Path) -> tuple[str, str]:
    head = git(checkout, "rev-parse", "HEAD").strip()
    ref = f"refs/archive/worktrees/{re.sub(r'[^A-Za-z0-9._-]', '-', name)}-{head[:12]}"
    git(repo_root, "update-ref", ref, head)
    return head, ref


def look_target(code_root: Path, github: GitHub, repo_root: Path, raw: str, refresh_cwds: bool = True) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    current = next((r for r in worktrees(repo_root) if canonical(r["path"]) == canonical(raw)), None)
    if current is None:
        return None, {"path": raw, "repo": str(repo_root), "reasons": ["worktree_not_registered"]}
    path = Path(current["path"])
    row = evaluate(repo_root, current, code_root, github, T3State(), refresh=True, refresh_cwds=refresh_cwds)
    row["category"] = categorize(row)
    refusal = {"path": raw, "repo": str(repo_root), "branch": row["branch"]}
    if row["category"] != "look":
        return None, {**refusal, "reasons": row["reasons"] if row["category"] == "protected" else ["not_needs_a_look"]}
    if row["gone"]:
        return None, {**refusal, "reasons": ["worktree_missing_or_prunable"]}
    if path.is_symlink():
        return None, {**refusal, "reasons": ["worktree_is_symlink"]}
    return row, refusal


def archive_one(code_root: Path, state_root: Path, github: GitHub, repo_root: Path, raw: str, day_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    row, refusal = look_target(code_root, github, repo_root, raw)
    if row is None:
        return None, refusal
    path = Path(row["path"])
    destination = day_dir / repo_root.name / path.name
    if destination.exists() or destination.is_symlink():
        return None, {**refusal, "reasons": ["archive_target_exists"]}
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.stat().st_dev != path.stat().st_dev:
        return None, {**refusal, "reasons": ["archive_on_another_filesystem"]}
    row["head"], ref = pin_head(repo_root, path.name, path)
    row["archive_path"] = str(destination)
    row["archive_ref"] = ref
    details = {
        "reason": "archived from Needs a look, folder moved and commit pinned, nothing deleted",
        "archive_path": row["archive_path"], "archive_ref": ref,
        "uncommitted": row["uncommitted"], "unpushed": row["unpushed"],
    }
    append_removal(state_root, row, "archive_attempted", details)
    try:
        os.rename(path, destination)
    except OSError:
        append_removal(state_root, row, "archive_failed", details)
        return None, {**refusal, "reasons": ["archive_move_failed"]}
    moved_head, moved_ref = pin_head(repo_root, path.name, destination)
    if moved_head != row["head"]:
        row["head"], row["archive_ref"] = moved_head, moved_ref
        details["archive_ref"] = moved_ref
    stale = {canonical(item["path"]) for item in worktrees(repo_root) if item.get("prunable")}
    row["registration_pruned"] = stale == {canonical(path)}
    if row["registration_pruned"]:
        git(repo_root, "worktree", "prune")
    append_removal(state_root, row, "archived", details)
    return row, None


SAVE_LIMIT = 200 * 1024 * 1024
BULK_DIRS = {"node_modules", ".venv", "venv", "build", "dist", ".next", "target", "DerivedData", "__pycache__", "Pods", "vendor", ".git", ".turbo", ".cache", "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".gradle", ".expo"}
DELETE_REFUSED = {"worktree_status_unknown", "worktree_root_mismatch", "head_unknown"}


def git_bytes(path: Path, *args: str) -> bytes:
    """Run git and return the raw bytes, with no newline translation."""
    try:
        result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafetyError("git_save_failed") from exc
    if result.returncode != 0:
        raise SafetyError("git_save_failed")
    return result.stdout


def names(listing: bytes) -> list[str]:
    return [os.fsdecode(name) for name in listing.split(b"\0") if name]


def tracked_diff(path: Path, head: str) -> bytes:
    return git_bytes(path, "diff", "--binary", "--no-ext-diff", "--no-textconv", head)


def snapshot(path: Path) -> dict[str, Any]:
    head = git_bytes(path, "rev-parse", "HEAD").decode().strip()
    status = git_bytes(path, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    untracked = names(git_bytes(path, "ls-files", "--others", "--exclude-standard", "-z"))
    ignored = names(git_bytes(path, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory", "-z"))
    kept = [entry for entry in ignored if not BULK_DIRS & set(entry.rstrip("/").split("/"))]
    if any(entry.endswith("/") for entry in untracked) or any(entry.startswith(b"?? ") and entry.endswith(b"/") for entry in status.split(b"\0")):
        raise SafetyError("nested_repository_inside")
    files = saved_files(path, untracked, "untracked") + saved_files(path, kept, "ignored")
    try:
        stats = [(arc, os.lstat(source).st_size, os.lstat(source).st_mtime_ns) for arc, source in files]
    except OSError as exc:
        raise SafetyError("delete_save_unverified") from exc
    return {
        "head": head, "status": status, "untracked": untracked, "ignored": ignored, "kept": kept,
        "files": files, "stats": stats, "diff": hashlib.sha256(tracked_diff(path, head)).digest(),
    }


def saved_files(path: Path, entries: list[str], prefix: str) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for entry in entries:
        found = path / entry
        if not entry.endswith("/"):
            files.append((f"{prefix}/{entry}", found))
            continue
        if (found / ".git").exists():
            raise SafetyError("nested_repository_inside")
        for root, dirs, leaves in os.walk(found, followlinks=False):
            if ".git" in dirs or ".git" in leaves:
                raise SafetyError("nested_repository_inside")
            files.extend((f"{prefix}/{Path(root, leaf).relative_to(path)}", Path(root, leaf)) for leaf in leaves + [d for d in dirs if Path(root, d).is_symlink()])
    return files


def save_work(repo_root: Path, path: Path, row: dict[str, Any], tar_path: Path, before: dict[str, Any]) -> None:
    if (path / ".gitmodules").exists():
        raise SafetyError("submodules_inside")
    if any(line[:1] in (b"S", b"h") for line in git_bytes(path, "ls-files", "-v", "-z").split(b"\0")):
        raise SafetyError("hidden_tracked_changes")
    untracked, kept, files = before["untracked"], before["kept"], before["files"]
    skipped = [entry for entry in before["ignored"] if entry not in kept]
    sizes = {arc: size for arc, size, _ in before["stats"]}
    if sum(sizes.values()) > SAVE_LIMIT:
        raise SafetyError("save_too_large")
    patch = tracked_diff(path, row["head"])
    manifest = json.dumps({
        "repo": str(repo_root), "path": str(path), "branch": row["branch"], "head": row["head"],
        "archive_ref": row["archive_ref"], "uncommitted": row["uncommitted"], "unpushed": row["unpushed"],
        "untracked_files": untracked, "ignored_saved": kept, "ignored_skipped": skipped,
        "saved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }, sort_keys=True, indent=2).encode()
    partial = tar_path.with_name(tar_path.name + ".tmp")
    partial.unlink(missing_ok=True)
    try:
        with os.fdopen(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
            with tarfile.open(fileobj=output, mode="w:gz") as tar:
                for name, data in (("changes.patch", patch), ("manifest.json", manifest)):
                    info = tarfile.TarInfo(name)
                    info.size, info.mtime = len(data), int(time.time())
                    tar.addfile(info, io.BytesIO(data))
                for arc, source in files:
                    tar.add(source, arcname=arc, recursive=False)
            output.flush()
            os.fsync(output.fileno())
        with tarfile.open(partial, "r:gz") as tar:
            members = {member.name: member for member in tar.getmembers()}
        if {"changes.patch", "manifest.json", *sizes} - members.keys():
            raise SafetyError("delete_save_unverified")
        if any(members[arc].isreg() and members[arc].size != os.lstat(source).st_size for arc, source in files):
            raise SafetyError("delete_save_unverified")
        os.replace(partial, tar_path)
    except (tarfile.TarError, OSError) as exc:
        raise SafetyError("delete_save_unverified") from exc
    finally:
        partial.unlink(missing_ok=True)


def delete_one(code_root: Path, state_root: Path, github: GitHub, repo_root: Path, raw: str, day_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    row, refusal = look_target(code_root, github, repo_root, raw, refresh_cwds=False)
    if row is None:
        return None, refusal
    path = Path(row["path"])
    if DELETE_REFUSED & set(row["reasons"]) or row["uncommitted"] is None:
        return None, {**refusal, "reasons": ["worktree_status_unknown"]}
    row["head"], ref = pin_head(repo_root, path.name, path)
    tar_path = day_dir / repo_root.name / f"{path.name}-{row['head'][:12]}-{dt.datetime.now().strftime('%H%M%S')}.tar.gz"
    if tar_path.exists() or tar_path.is_symlink():
        return None, {**refusal, "reasons": ["delete_target_exists"]}
    tar_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    row["archive_ref"] = ref
    row["save_path"] = str(tar_path)
    details = {
        "reason": "deleted from Needs a look, commit pinned and uncommitted work saved to a file",
        "save_path": row["save_path"], "archive_ref": ref,
        "uncommitted": row["uncommitted"], "unpushed": row["unpushed"],
    }
    before = snapshot(path)
    if before["head"] != row["head"]:
        return None, {**refusal, "reasons": ["worktree_changed_before_remove"]}
    try:
        save_work(repo_root, path, row, tar_path, before)
        if snapshot(path) != before:
            raise SafetyError("worktree_changed_before_remove")
    except SafetyError as exc:
        tar_path.unlink(missing_ok=True)
        if str(exc) == "worktree_changed_before_remove":
            append_removal(state_root, row, "delete_blocked", details)
        raise
    try:
        append_removal(state_root, row, "delete_attempted", details)
        blockers = T3State().blockers(path)
        if blockers or cwd_held(path) or snapshot(path) != before:
            raise SafetyError(blockers[0] if blockers else "worktree_changed_before_remove")
    except (SafetyError, OSError) as exc:
        tar_path.unlink(missing_ok=True)
        append_removal(state_root, row, "delete_blocked", details)
        return None, {**refusal, "reasons": [str(exc)]}
    try:
        result = run(["git", "-C", str(repo_root), "worktree", "remove", "--force", str(path)], timeout=300)
    except SafetyError:
        append_removal(state_root, row, "delete_outcome_unknown", details)
        return None, {**refusal, "reasons": ["worktree_remove_outcome_unknown"]}
    if result.returncode != 0 or path.exists() or any(canonical(item["path"]) == canonical(path) for item in worktrees(repo_root)):
        append_removal(state_root, row, "delete_failed", details)
        if path.is_dir() and snapshot(path) == before:
            tar_path.unlink(missing_ok=True)
        return None, {**refusal, "reasons": ["delete_remove_failed"]}
    append_removal(state_root, row, "deleted", details)
    return row, None


def archive(code_root: Path, state_root: Path, paths: list[Path], delete: bool = False) -> dict[str, Any]:
    state_root = secure_state_dir(state_root)
    day_dir = ARCHIVE_ROOT / report_day()
    with cleaner_lock(state_root):
        github = GitHub()
        found = registrations(code_root, github)
        one = delete_one if delete else archive_one
        archived: list[dict[str, Any]] = []
        refused: list[dict[str, Any]] = []
        for raw in paths:
            entry = found.get(canonical(raw))
            if entry is None:
                refused.append({"path": os.fspath(raw), "reasons": ["worktree_not_registered"]})
                continue
            try:
                row, refusal = one(code_root, state_root, github, entry[0], os.fspath(raw), day_dir)
            except (SafetyError, OSError) as exc:
                row, refusal = None, {"path": os.fspath(raw), "repo": str(entry[0]), "reasons": [str(exc)]}
            if row:
                archived.append(row)
            if refusal:
                refused.append(refusal)
        return {"mode": "delete" if delete else "archive", "archive_dir": str(day_dir), "deleted" if delete else "archived": archived, "refused": refused}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely review and remove eligible Git worktrees under repositories in ~/Code.")
    parser.add_argument("--code-root", type=Path, default=DEFAULT_CODE_ROOT)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="remove only worktrees that pass every safety check")
    mode.add_argument("--dry-run", action="store_false", dest="apply", help="report counts without removing worktrees")
    mode.add_argument("--archive", nargs="+", type=Path, metavar="PATH", help="move Needs-a-look worktrees to the archive, pin their commit, keep their branch")
    mode.add_argument("--delete", nargs="+", type=Path, metavar="PATH", help="remove Needs-a-look worktrees, pin their commit, and save uncommitted work to a small file in the archive")
    parser.add_argument("--prune", action="store_true", help="with --apply, also drop registrations whose folder is gone and that pass every prune check")
    parser.add_argument("--no-report", action="store_true", help="skip writing the daily kept-worktrees report")
    parser.set_defaults(apply=False)
    args = parser.parse_args(argv)
    try:
        if args.archive:
            print(json.dumps(archive(args.code_root.expanduser(), args.state_root.expanduser(), args.archive), sort_keys=True))
            return 0
        if args.delete:
            print(json.dumps(archive(args.code_root.expanduser(), args.state_root.expanduser(), args.delete, delete=True), sort_keys=True))
            return 0
        result = scan(args.code_root.expanduser(), args.state_root.expanduser(), args.apply, not args.no_report, args.prune)
    except SafetyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
