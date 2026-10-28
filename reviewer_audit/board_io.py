"""Read task bundles from the herdr-projects board data directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_BOARD_TASKS = Path.home() / ".herdr-projects" / "data" / "tasks"


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
