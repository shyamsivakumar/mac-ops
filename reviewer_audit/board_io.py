"""Read task bundles from the herdr-projects board data directory."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_BOARD_TASKS = Path.home() / ".herdr-projects" / "data" / "tasks"
HERDR_PROJECTS = Path.home() / ".local/bin/herdr-projects"

MAX_DIFF_BYTES = 180_000

# Fallback when herdr-projects is unavailable (matches mac-ops repo entry 2026-10-28).
DEFAULT_REVIEWER_INSTRUCTIONS = (
    "Finish every review in under 10 minutes. Review the diff, the task description "
    "and the agent's saved proof (closing note, receipts, logs, screenshots). "
    "Do not rerun release gates, full test suites, builds or replays that the agent "
    "or the board check already ran with a receipt; judge from the receipt. "
    "Ship-and-score policy: fail a review only for hard stops (does not build or start, "
    "crashes, breaks health, or breaks money or data safety) or when the change does not "
    "do what the task asked at all. List every other finding as a follow-up with its "
    "severity; it does not send the work back. Blocking findings must name the exact "
    "requirement from the task description they break and give a reproduction (a command, "
    "a replay or a file and line) that fails now; a finding without both is a follow-up, "
    "never a block."
)


def read_reviewer_instructions(*, repo: str = "mac-ops") -> str:
    """Load reviewer.instructions from herdr-projects show --repo."""
    if not HERDR_PROJECTS.is_file():
        return DEFAULT_REVIEWER_INSTRUCTIONS
    proc = subprocess.run(
        [str(HERDR_PROJECTS), "show", "--repo", repo],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    text = proc.stdout or ""
    marker = "Finish every review"
    for line in text.splitlines():
        if "reviewer.instructions" not in line:
            continue
        idx = line.find(marker)
        if idx >= 0:
            return line[idx:].strip()
    return DEFAULT_REVIEWER_INSTRUCTIONS


def read_task(task_id: str, tasks_root: Path | None = None) -> dict[str, Any]:
    repo, num = task_id.split("/", 1)
    root = tasks_root or DEFAULT_BOARD_TASKS
    path = root / repo / num / "task.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


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
