"""Read task bundles from the herdr-projects board data directory."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_BOARD_TASKS = Path.home() / ".herdr-projects" / "data" / "tasks"

MAX_DIFF_BYTES = 180_000


def read_task(task_id: str, tasks_root: Path | None = None) -> dict[str, Any]:
    repo, num = task_id.split("/", 1)
    root = tasks_root or DEFAULT_BOARD_TASKS
    path = root / repo / num / "task.json"
    return json.loads(path.read_text(encoding="utf-8"))


def read_closing_note(task_id: str, tasks_root: Path | None = None) -> str:
    repo, num = task_id.split("/", 1)
    root = tasks_root or DEFAULT_BOARD_TASKS
    path = root / repo / num / "closing-note.md"
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    alt = root / repo / num / "closing.md"
    if alt.is_file():
        return alt.read_text(encoding="utf-8", errors="replace")
    return ""


def task_repo_root(task: dict[str, Any]) -> Path | None:
    raw = task.get("root") or task.get("repoRoot")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    return path if path.is_dir() else None


def _cap_patch(patch: str, *, max_bytes: int) -> str:
    if len(patch.encode("utf-8", errors="replace")) > max_bytes:
        return patch[: max_bytes - 40] + "\n\n... [diff truncated at freeze cap] ...\n"
    return patch


def git_diff_base_to_head(
    repo_root: Path,
    base: str,
    head: str,
    *,
    max_bytes: int = MAX_DIFF_BYTES,
) -> tuple[str, str]:
    """Return (stat line, patch) for the reviewed change base..head."""
    if not head or not base or not repo_root.is_dir():
        return "", ""
    env = {"GIT_TERMINAL_PROMPT": "0"}
    stat_proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--stat",
            f"{base}..{head}",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )
    stat = (stat_proc.stdout or "").strip()
    diff_proc = subprocess.run(
        ["git", "-C", str(repo_root), "diff", f"{base}..{head}"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env=env,
    )
    patch = (diff_proc.stdout or "") + (diff_proc.stderr or "")
    return stat, _cap_patch(patch, max_bytes=max_bytes)


def git_diff_at_head(
    repo_root: Path, head: str, *, max_bytes: int = MAX_DIFF_BYTES
) -> tuple[str, str]:
    """Return (stat line, patch text) for a single commit (legacy helper)."""
    if not head or not repo_root.is_dir():
        return "", ""
    env = {"GIT_TERMINAL_PROMPT": "0"}
    stat_proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", "--stat", "--format=", head],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )
    stat = (stat_proc.stdout or "").strip()
    diff_proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", "--format=", head],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env=env,
    )
    patch = (diff_proc.stdout or "") + (diff_proc.stderr or "")
    return stat, _cap_patch(patch, max_bytes=max_bytes)


def iter_tasks_with_reviews(tasks_root: Path | None = None) -> list[dict[str, Any]]:
    root = tasks_root or DEFAULT_BOARD_TASKS
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/*/task.json")):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if task.get("reviews"):
            out.append(task)
    return out
