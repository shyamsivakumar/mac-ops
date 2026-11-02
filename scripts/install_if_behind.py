#!/usr/bin/env python3
"""Compare the installed source commit with origin/main and install when behind."""

import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install as installer


def default_checkout(home=None):
    home = Path(home or Path.home())
    for key in ("MAC_OPS_CHECKOUT", "HERDR_PROJECTS_REPO"):
        candidate = os.environ.get(key, "").strip()
        if candidate and (Path(candidate) / ".git").is_dir():
            return Path(candidate).resolve()
    return (home / "Code" / "mac-ops").resolve()


def run_cmd(argv, *, cwd=None, timeout=30, allowed=(0,)):
    result = subprocess.run(
        [str(item) for item in argv],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode not in allowed:
        stderr = (result.stderr or result.stdout or "").strip()
        first = stderr.splitlines()[0][:200] if stderr else f"exit {result.returncode}"
        raise RuntimeError(
            f"{argv[0]} {argv[1] if len(argv) > 1 else ''} failed ({result.returncode}): {first}"
        )
    return result.stdout


@contextlib.contextmanager
def install_lock(state_dir):
    state_dir = Path(state_dir)
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = state_dir / "install-if-behind.lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(lock_path), flags, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise RuntimeError("Install lock file is unsafe: " + str(lock_path))
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def compute_digest_at_ref(checkout, ref="HEAD"):
    checkout = Path(checkout)
    digest = hashlib.sha256()
    if ref == "WORKTREE":
        for name in installer.FILES:
            digest.update(name.encode() + (checkout / name).read_bytes())
        return digest.hexdigest()[:20]
    batch_input = "".join(f"{ref}:{name}\n" for name in installer.FILES).encode("utf-8")
    proc = subprocess.run(
        ["git", "-C", str(checkout), "cat-file", "--batch"],
        input=batch_input,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Unable to read release files at {ref}")
    stream = memoryview(proc.stdout)
    pos = 0
    for name in installer.FILES:
        newline = proc.stdout.find(b"\n", pos)
        if newline < 0:
            raise RuntimeError(f"Malformed git cat-file header for {name} at {ref}")
        header = bytes(stream[pos:newline]).decode("utf-8", errors="replace").split()
        if len(header) < 3 or header[1] != "blob":
            raise RuntimeError(f"Missing blob {name} at {ref}: {' '.join(header)}")
        size = int(header[2])
        start = newline + 1
        end = start + size
        digest.update(name.encode() + bytes(stream[start:end]))
        pos = end + 1
    return digest.hexdigest()[:20]


def read_installation_status(checkout, state_dir):
    checkout = Path(checkout)
    state_dir = Path(state_dir).resolve()
    default_state = (Path.home() / ".local/state/mac-ops").resolve()
    receipt_path = state_dir / "installation.json"
    status_lines = []
    install_sh = checkout / "install.sh"
    if state_dir == default_state and install_sh.is_file():
        raw = run_cmd([install_sh, "status"], cwd=checkout, timeout=20)
        status_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    receipt = None
    legacy_live = []
    if status_lines and status_lines[0].startswith("{"):
        try:
            receipt = json.loads(status_lines[0])
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "install.sh status returned invalid receipt JSON"
            ) from exc
        if len(status_lines) > 1 and status_lines[1].startswith("{"):
            with contextlib.suppress(json.JSONDecodeError):
                legacy_live = json.loads(status_lines[1]).get("legacy_live") or []
    elif receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("installation.json is unreadable or invalid") from exc
    if not isinstance(receipt, dict):
        return {
            "installed": False,
            "source_commit": None,
            "release": None,
            "release_name": None,
            "installed_at": None,
            "legacy_live": legacy_live,
            "receipt": None,
        }
    source_commit = receipt.get("source_commit")
    release = receipt.get("release")
    release_name = Path(release).name if isinstance(release, str) and release else None
    return {
        "installed": bool(source_commit and release),
        "source_commit": source_commit if isinstance(source_commit, str) else None,
        "release": release if isinstance(release, str) else None,
        "release_name": release_name,
        "installed_at": receipt.get("installed_at"),
        "legacy_live": legacy_live,
        "receipt": receipt,
    }


def _git_is_ancestor(checkout, older, newer):
    proc = subprocess.run(
        ["git", "-C", str(checkout), "merge-base", "--is-ancestor", older, newer],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError("git merge-base failed: " + proc.stderr.strip())
    return proc.returncode == 0


def _git_commit_exists(checkout, sha):
    if not isinstance(sha, str) or not sha.strip():
        return False
    proc = subprocess.run(
        ["git", "-C", str(checkout), "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return proc.returncode == 0


def classify_commits(checkout, source_commit, head_commit, target_commit):
    checkout = Path(checkout)
    head_can_ff = head_commit == target_commit or _git_is_ancestor(
        checkout, head_commit, target_commit
    )
    if not source_commit:
        return {
            "relation": "not_installed",
            "behind": True,
            "behind_count": None,
            "commits": [],
            "head_can_ff": head_can_ff,
        }
    if source_commit == target_commit:
        return {
            "relation": "up_to_date",
            "behind": False,
            "behind_count": 0,
            "commits": [],
            "head_can_ff": head_can_ff,
        }
    if not _git_commit_exists(checkout, source_commit):
        return {
            "relation": "unknown_commit",
            "behind": False,
            "behind_count": None,
            "commits": [],
            "head_can_ff": head_can_ff,
        }
    if _git_is_ancestor(checkout, source_commit, target_commit):
        count_raw = run_cmd(
            [
                "git",
                "-C",
                str(checkout),
                "rev-list",
                "--count",
                f"{source_commit}..{target_commit}",
            ],
            timeout=15,
        ).strip()
        log_raw = run_cmd(
            [
                "git",
                "-C",
                str(checkout),
                "log",
                "--oneline",
                f"{source_commit}..{target_commit}",
            ],
            timeout=15,
        )
        commits = [line.strip() for line in log_raw.splitlines() if line.strip()]
        return {
            "relation": "behind",
            "behind": True,
            "behind_count": int(count_raw),
            "commits": commits,
            "head_can_ff": head_can_ff,
        }
    if _git_is_ancestor(checkout, target_commit, source_commit):
        return {
            "relation": "ahead",
            "behind": False,
            "behind_count": 0,
            "commits": [],
            "head_can_ff": head_can_ff,
        }
    return {
        "relation": "diverged",
        "behind": False,
        "behind_count": None,
        "commits": [],
        "head_can_ff": head_can_ff,
    }


def check_gate(heavy_bin, state_dir, *, max_queued=3, max_status_age=30.0, now=None):
    state_dir = Path(state_dir)
    now = time.time() if now is None else float(now)
    reasons = []
    queued_jobs = None
    running_jobs = None
    global_limit = None
    queued_summaries = []

    if Path(heavy_bin).is_file():
        try:
            heavy_raw = run_cmd([str(heavy_bin), "status"], timeout=15)
            heavy_data = json.loads(heavy_raw)
            jobs = heavy_data.get("jobs")
            queued_list = heavy_data.get("queue")
            if not isinstance(jobs, list) or not isinstance(queued_list, list):
                raise TypeError("heavy status jobs or queue field is missing")
            global_limit = heavy_data.get("global_limit")
            running_list = [
                j for j in jobs if isinstance(j, dict) and j.get("state") == "running"
            ]
            queued_jobs = len(queued_list)
            running_jobs = len(running_list)
            for item in queued_list:
                queued_summaries.append(
                    {
                        "role": item.get("role"),
                        "task_id": item.get("task_id"),
                        "command": item.get("command"),
                    }
                )
            if queued_jobs > max_queued:
                reasons.append(f"heavy_queue={queued_jobs}>{max_queued}")
        except (
            RuntimeError,
            OSError,
            ValueError,
            TypeError,
            subprocess.SubprocessError,
        ) as exc:
            reasons.append(f"heavy_status_unavailable={str(exc).splitlines()[0][:120]}")
    else:
        reasons.append("heavy_bin_missing")

    status_path = state_dir / "controller-status.json"
    board_host_veto = None
    heavy_host_veto = None
    board_current = None
    board_target = None
    board_reason = None
    heavy_reason = None
    heavy_target = None
    updated_at = None
    status_age = None

    if not status_path.is_file():
        reasons.append("controller_status_missing")
    else:
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if not isinstance(status, dict):
                raise TypeError("controller-status.json is not an object")
            updated_at = status.get("updated_at")
            if (
                isinstance(updated_at, (int, float))
                and not isinstance(updated_at, bool)
                and math.isfinite(float(updated_at))
            ):
                status_age = max(0.0, now - float(updated_at))
                if status_age > max_status_age:
                    reasons.append(
                        f"controller_status_stale={round(status_age, 1)}s>{max_status_age}s"
                    )
            else:
                reasons.append("controller_status_missing_updated_at")
            board_block = (
                status.get("board") if isinstance(status.get("board"), dict) else {}
            )
            board_decision = (
                board_block.get("decision")
                if isinstance(board_block.get("decision"), dict)
                else {}
            )
            heavy_decision = (
                status.get("heavy_decision")
                if isinstance(status.get("heavy_decision"), dict)
                else {}
            )
            board_current = board_block.get("current", board_decision.get("current"))
            board_target = board_decision.get("target")
            board_reason = board_decision.get("reason")
            board_host_veto = board_decision.get("host_veto")
            heavy_host_veto = heavy_decision.get("host_veto")
            heavy_reason = heavy_decision.get("reason")
            heavy_target = heavy_decision.get("target")
            if board_host_veto:
                reasons.append(f"board_host_veto={board_host_veto}")
            if heavy_host_veto:
                reasons.append(f"heavy_host_veto={heavy_host_veto}")
        except (OSError, ValueError, TypeError) as exc:
            reasons.append(
                f"controller_status_invalid={str(exc).splitlines()[0][:120]}"
            )

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "queued_jobs": queued_jobs,
        "running_jobs": running_jobs,
        "max_queued": max_queued,
        "global_limit": global_limit,
        "queued_summaries": queued_summaries,
        "board_current": board_current,
        "board_target": board_target,
        "board_reason": board_reason,
        "board_host_veto": board_host_veto,
        "heavy_host_veto": heavy_host_veto,
        "heavy_reason": heavy_reason,
        "heavy_target": heavy_target,
        "controller_updated_at": updated_at,
        "controller_status_age_seconds": round(status_age, 3)
        if status_age is not None
        else None,
    }


CENSUS_PROCESS_EXIT = "foreground process exited during collection"


def census_error_is_process_exit(err):
    if not isinstance(err, str):
        return False
    _prefix, separator, detail = err.rpartition(": ")
    text = detail if separator else err
    return text == CENSUS_PROCESS_EXIT


def evaluate_controller_ticks(
    rows,
    *,
    target_release,
    install_started_at,
    min_ticks=1,
):
    target_release_str = str(Path(target_release).resolve()) if target_release else ""
    matching = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        updated_at = row.get("updated_at")
        if not isinstance(updated_at, (int, float)) or isinstance(updated_at, bool):
            continue
        if float(updated_at) < float(install_started_at):
            continue
        runtime = row.get("runtime")
        if isinstance(runtime, str) and target_release_str:
            with contextlib.suppress(OSError):
                if str(Path(runtime).resolve()) != target_release_str:
                    continue
        elif target_release_str:
            continue
        matching.append(row)

    board_decisions = 0
    heavy_decisions = 0
    fatal_errors = []
    census_churn = []
    unexplained_zero_board_slots = []
    board_targets = []
    board_currents = []

    for row in matching:
        board_block = row.get("board") if isinstance(row.get("board"), dict) else {}
        board_dec = (
            board_block.get("decision")
            if isinstance(board_block.get("decision"), dict)
            else None
        )
        heavy_dec = (
            row.get("heavy_decision")
            if isinstance(row.get("heavy_decision"), dict)
            else None
        )
        if board_dec is not None:
            board_decisions += 1
            target = board_dec.get("target")
            current = board_block.get("current", board_dec.get("current"))
            active = board_dec.get("active") or 0
            host_veto = board_dec.get("host_veto")
            reason = board_dec.get("reason")
            if isinstance(target, int) and not isinstance(target, bool):
                board_targets.append(target)
            if isinstance(current, int) and not isinstance(current, bool):
                board_currents.append(current)
            if target == 0 and host_veto is None:
                unexplained_zero_board_slots.append(
                    {
                        "updated_at": row.get("updated_at"),
                        "current": current,
                        "target": target,
                        "active": active,
                        "reason": reason,
                    }
                )
        if heavy_dec is not None:
            heavy_decisions += 1

        for key in (
            "board_error",
            "capacity_error",
            "critical_curtailment_error",
            "board_restart_error",
        ):
            if row.get(key):
                fatal_errors.append(f"{key}: {row[key]}")

        if row.get("heavy_error"):
            fatal_errors.append(f"heavy_error: {row['heavy_error']}")

        agent_census = row.get("board_agent_census")
        if isinstance(agent_census, dict):
            census_errors = agent_census.get("errors") or []
            for err in census_errors:
                message = f"board_agent_census: {err}"
                if census_error_is_process_exit(err):
                    census_churn.append(message)
                else:
                    fatal_errors.append(message)
        pause_status = row.get("agent_heavy_wait_pause")
        if isinstance(pause_status, dict):
            if pause_status.get("error"):
                fatal_errors.append(f"agent_heavy_wait_pause: {pause_status['error']}")
            for key in ("resume", "boot_resume"):
                resume = pause_status.get(key)
                if isinstance(resume, dict) and (
                    resume.get("error") or resume.get("failed")
                ):
                    fatal_errors.append(f"agent_heavy_wait_pause {key}: {resume}")
            if pause_status.get("resume_pending_count"):
                fatal_errors.append("agent_heavy_wait_pause has pending resumes")

    reasons = []
    if len(matching) < min_ticks:
        reasons.append(f"insufficient_controller_ticks ({len(matching)} < {min_ticks})")
    if min_ticks > 0 and board_decisions == 0:
        reasons.append("no_board_decisions_logged")
    if min_ticks > 0 and heavy_decisions == 0:
        reasons.append("no_heavy_decisions_logged")
    if fatal_errors:
        reasons.append(fatal_errors[0])
    if unexplained_zero_board_slots:
        reasons.append("board_slots_dropped_to_zero_without_veto")

    span_seconds = 0.0
    if len(matching) >= 2:
        span_seconds = round(
            float(matching[-1]["updated_at"]) - float(matching[0]["updated_at"]), 2
        )

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "tick_count": len(matching),
        "min_ticks": min_ticks,
        "span_seconds": span_seconds,
        "board_decisions": board_decisions,
        "heavy_decisions": heavy_decisions,
        "fatal_errors": fatal_errors,
        "census_churn": census_churn,
        "unexplained_zero_board_slots": unexplained_zero_board_slots,
        "last_tick_at": max((row["updated_at"] for row in matching), default=None),
        "min_board_target": min(board_targets) if board_targets else None,
        "min_board_current": min(board_currents) if board_currents else None,
    }


def read_controller_rows(state_dir, *, since=0.0):
    state_dir = Path(state_dir)
    rows = []
    for name in ("controller.previous.jsonl", "controller.jsonl"):
        path = state_dir / name
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                with contextlib.suppress(json.JSONDecodeError):
                    item = json.loads(line)
                    if (
                        isinstance(item, dict)
                        and float(item.get("updated_at") or 0.0) >= since
                    ):
                        rows.append(item)
    return rows


OBSERVATION_MARKER_NAME = "observation-pending.json"


def observation_marker_path(state_dir):
    return Path(state_dir) / OBSERVATION_MARKER_NAME


def read_observation_marker(state_dir):
    path = observation_marker_path(state_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    source_commit = data.get("source_commit")
    if not isinstance(source_commit, str) or not source_commit:
        return None
    return data


def write_observation_marker(
    state_dir,
    *,
    source_commit,
    started_at,
    previous_receipt=None,
    release=None,
):
    state_dir = Path(state_dir)
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {
        "source_commit": source_commit,
        "started_at": float(started_at),
    }
    if release is not None:
        payload["release"] = release
    if previous_receipt is not None:
        payload["previous_receipt"] = previous_receipt
    installer.atomic(
        observation_marker_path(state_dir),
        json.dumps(payload, sort_keys=True).encode("utf-8"),
        0o600,
    )


def clear_observation_marker(state_dir):
    with contextlib.suppress(FileNotFoundError):
        observation_marker_path(state_dir).unlink()


def observation_marker_applies_to_receipt(marker, status):
    if not marker or not status or not status.get("installed"):
        return False
    source_commit = status.get("source_commit")
    if not source_commit or marker.get("source_commit") != source_commit:
        return False
    marker_release = marker.get("release")
    return not (
        marker_release
        and status.get("release")
        and marker_release != status.get("release")
    )


def marker_previous_receipt(marker):
    if not marker:
        return None
    previous = marker.get("previous_receipt")
    if not isinstance(previous, dict):
        return None
    if not previous.get("release") or not previous.get("source_commit"):
        return None
    return previous


def rebind_observation_marker_to_receipt(state_dir, marker, status):
    """Keep recovery previous_receipt when marker target != installed receipt."""
    if not marker or not status or not status.get("installed"):
        return None
    source_commit = status.get("source_commit")
    if not source_commit:
        return None
    write_observation_marker(
        state_dir,
        source_commit=source_commit,
        started_at=float(
            marker.get("started_at") or status.get("installed_at") or time.time()
        ),
        previous_receipt=marker_previous_receipt(marker),
        release=status.get("release"),
    )
    return read_observation_marker(state_dir)


def observe_controller(
    state_dir,
    *,
    target_release,
    install_started_at,
    observe_seconds=180.0,
    poll_interval=5.0,
):
    observe_seconds = max(0.0, float(observe_seconds))
    min_ticks = 0 if observe_seconds == 0 else max(1, int(observe_seconds // 15) or 1)
    started = time.time()
    deadline = started + observe_seconds
    while True:
        rows = read_controller_rows(state_dir, since=install_started_at)
        summary = evaluate_controller_ticks(
            rows,
            target_release=target_release,
            install_started_at=install_started_at,
            min_ticks=min_ticks,
        )
        now = time.time()
        last_tick_at = summary["last_tick_at"]
        fresh = last_tick_at is not None and now - float(last_tick_at) <= 15
        if summary["fatal_errors"] or summary["unexplained_zero_board_slots"]:
            summary["reasons"] = [
                reason
                for reason in summary["reasons"]
                if not str(reason).startswith("insufficient_controller_ticks")
            ]
            summary["passed"] = len(summary["reasons"]) == 0
            return summary
        if summary["tick_count"] >= min_ticks and fresh and summary["passed"]:
            return summary
        if now >= deadline:
            if observe_seconds and not fresh:
                summary["passed"] = False
                summary["reasons"].append("controller_status_stale_at_end")
            return summary
        time.sleep(min(max(0.1, float(poll_interval)), max(0.1, deadline - now)))


def rollback_to_release(
    home, checkout, previous_receipt, *, state_dir=None, no_start=False
):
    home = Path(home)
    checkout = Path(checkout)
    if not isinstance(previous_receipt, dict):
        raise TypeError("No previous installation receipt is available for rollback")
    prev_release = previous_receipt.get("release")
    prev_commit = previous_receipt.get("source_commit")
    if not prev_release or not prev_commit:
        raise RuntimeError(
            "Previous installation receipt is missing release or source_commit"
        )
    p = installer.paths(home, checkout)
    if state_dir is not None:
        p["state"] = Path(state_dir)
    installer.activate_release(
        p, checkout, Path(prev_release), prev_commit, no_start=no_start
    )
    return read_installation_status(checkout, p["state"])


def evaluate_decision(
    *,
    fetch_ok,
    relation,
    head_can_ff,
    checkout_clean,
    on_main_branch,
    gate_passed,
):
    if not on_main_branch:
        return "error", "checkout_not_on_main"
    if not checkout_clean:
        return "error", "checkout_dirty"
    if not fetch_ok:
        return "error", "git_fetch_failed"
    if relation == "up_to_date" and head_can_ff:
        return "up_to_date", "source_commit_matches_origin_main"
    if relation in ("ahead", "diverged", "unknown_commit") or not head_can_ff:
        return "error", f"cannot_fast_forward_{relation}"
    if relation in ("behind", "not_installed"):
        if not gate_passed:
            return "deferred", "gate_blocked"
        return "install", "behind_and_gate_clear"
    return "error", f"unexpected_relation_{relation}"


def format_closing_note(result):
    decision = result.get("decision")
    src = (result.get("installed_source_commit") or "none")[:7]
    target = (result.get("origin_main_commit") or "unknown")[:7]
    release_name = result.get("release_name") or "unknown"
    behind_count = result.get("behind_count")
    gate = result.get("gate") or {}
    obs = result.get("observation") or {}

    if decision == "up_to_date":
        first_line = (
            f"Up to date: mac-ops installed source_commit {src} matches origin/main {target} "
            f"(release {release_name})."
        )
    elif decision == "deferred":
        reasons = ", ".join(gate.get("reasons") or ["gate blocked"])
        behind_phrase = (
            f"{behind_count} commit(s) behind" if behind_count is not None else "behind"
        )
        first_line = (
            f"Deferred mac-ops install of origin/main {target} (installed {src}, {behind_phrase}): "
            f"{reasons}; the next firing will retry."
        )
    elif decision == "installed":
        prev_src = (result.get("previous_source_commit") or "none")[:7]
        ticks = obs.get("tick_count", 0)
        first_line = (
            f"Installed mac-ops origin/main {target} over {prev_src} (release {release_name}); "
            f"verified {ticks} controller tick(s) with no regression."
        )
    elif decision == "rolled_back":
        prev_src = (result.get("previous_source_commit") or "none")[:7]
        reason = "; ".join(obs.get("reasons") or [result.get("reason") or "regression"])
        first_line = (
            f"Rolled back mac-ops {target} to previous commit {prev_src} after post-install "
            f"verification failed ({reason})."
        )
    elif decision == "dry_run_would_install":
        first_line = f"Dry run: mac-ops installed {src} is behind origin/main {target} and passed the install gate."
    else:
        first_line = (
            f"Failed mac-ops install check (installed {src}, origin/main {target}): "
            f"{result.get('reason') or 'error'}."
        )

    lines = [
        first_line,
        "",
        "## Proof",
        "",
        f"- Decision: `{decision}` (`{result.get('reason')}`)",
        f"- Installed `source_commit`: `{result.get('installed_source_commit')}`",
        f"- `origin/main` commit: `{result.get('origin_main_commit')}`",
        f"- Checkout `HEAD`: `{result.get('head_commit')}`",
        f"- Installed release: `{result.get('installed_release')}`",
        f"- Commits behind `origin/main`: `{behind_count}`",
    ]
    commits = result.get("commits") or []
    if commits:
        lines.append("- Uninstalled commits on `origin/main`:")
        for item in commits:
            lines.append(f"  - `{item}`")
    if gate:
        lines.append(
            f"- Gate: passed=`{gate.get('passed')}`, queued_jobs=`{gate.get('queued_jobs')}` "
            f"(max `{gate.get('max_queued')}`), board_host_veto=`{gate.get('board_host_veto')}`, "
            f"heavy_host_veto=`{gate.get('heavy_host_veto')}`, board_slots=`{gate.get('board_current')}->{gate.get('board_target')}`"
        )
    if obs:
        lines.append(
            f"- Controller observation: passed=`{obs.get('passed')}`, ticks=`{obs.get('tick_count')}`, "
            f"span=`{obs.get('span_seconds')}s`, board_decisions=`{obs.get('board_decisions')}`, "
            f"heavy_decisions=`{obs.get('heavy_decisions')}`, min_board_slots=`{obs.get('min_board_current')}`"
        )
    return "\n".join(lines) + "\n"


def write_closing_note(path, result):
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    installer.atomic(target, format_closing_note(result).encode("utf-8"), 0o644)


def run_install_if_behind(
    *,
    checkout=None,
    home=None,
    state_dir=None,
    heavy_bin=None,
    max_queued=3,
    max_status_age=30.0,
    observe_seconds=180.0,
    poll_interval=5.0,
    no_fetch=False,
    dry_run=False,
    no_start=False,
    closing_note=None,
):
    home = Path(home or Path.home()).resolve()
    checkout = Path(checkout or default_checkout(home)).resolve()
    p = installer.paths(home, checkout)
    state_dir = Path(state_dir or p["state"]).resolve()
    heavy_bin = Path(heavy_bin or p["bin"]).resolve()

    with install_lock(state_dir) as acquired:
        if not acquired:
            result = {
                "decision": "deferred",
                "reason": "install_lock_held",
                "installed": False,
                "behind": None,
                "behind_count": None,
                "installed_source_commit": None,
                "origin_main_commit": None,
                "head_commit": None,
                "installed_release": None,
                "release_name": None,
            }
            write_closing_note(closing_note, result)
            return result

        if not (checkout / ".git").is_dir():
            result = {
                "decision": "error",
                "reason": "not_a_main_checkout",
                "installed": False,
            }
            write_closing_note(closing_note, result)
            return result

        branch = run_cmd(
            ["git", "-C", str(checkout), "branch", "--show-current"], timeout=15
        ).strip()
        dirty = run_cmd(
            [
                "git",
                "-C",
                str(checkout),
                "status",
                "--porcelain",
                "--untracked-files=no",
            ],
            timeout=15,
        ).strip()
        on_main = branch == "main"
        checkout_clean = dirty == ""

        fetch_ok = True
        fetch_error = None
        if not no_fetch:
            try:
                run_cmd(
                    ["git", "-C", str(checkout), "fetch", "origin", "main"], timeout=45
                )
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                fetch_ok = False
                fetch_error = str(exc)

        status_before = read_installation_status(checkout, state_dir)
        head_commit = run_cmd(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], timeout=15
        ).strip()
        target_commit = run_cmd(
            ["git", "-C", str(checkout), "rev-parse", "origin/main"], timeout=15
        ).strip()

        if status_before["receipt"] and not status_before["installed"]:
            raise RuntimeError(
                "Installation receipt is missing source_commit or release"
            )
        ancestry = classify_commits(
            checkout,
            status_before["source_commit"],
            head_commit,
            target_commit,
        )

        target_digest = compute_digest_at_ref(checkout, target_commit)
        same_digest = status_before["release_name"] == target_digest

        gate = check_gate(
            heavy_bin,
            state_dir,
            max_queued=max_queued,
            max_status_age=max_status_age,
        )
        gate_passed = gate["passed"]

        action, reason = evaluate_decision(
            fetch_ok=fetch_ok,
            relation=ancestry["relation"],
            head_can_ff=ancestry["head_can_ff"],
            checkout_clean=checkout_clean,
            on_main_branch=on_main,
            gate_passed=gate_passed,
        )

        base_result = {
            "installed_source_commit": status_before["source_commit"],
            "previous_source_commit": status_before["source_commit"],
            "origin_main_commit": target_commit,
            "head_commit": head_commit,
            "installed_release": status_before["release"],
            "release_name": status_before["release_name"],
            "target_release_digest": target_digest,
            "same_runtime_digest": same_digest,
            "relation": ancestry["relation"],
            "behind": ancestry["behind"],
            "behind_count": ancestry["behind_count"],
            "commits": ancestry["commits"],
            "gate": gate,
            "fetch_error": fetch_error,
        }

        pending_marker = read_observation_marker(state_dir)
        marker_for_receipt = observation_marker_applies_to_receipt(
            pending_marker, status_before
        )
        if pending_marker and not marker_for_receipt:
            # Interrupted supersede can leave marker.source_commit ahead of the
            # still-installed receipt. Re-bind so previous_receipt is not lost.
            rebound = rebind_observation_marker_to_receipt(
                state_dir, pending_marker, status_before
            )
            if rebound and observation_marker_applies_to_receipt(
                rebound, status_before
            ):
                pending_marker = rebound
                marker_for_receipt = True
            else:
                clear_observation_marker(state_dir)
                pending_marker = None
                marker_for_receipt = False
        resume_unverified = marker_for_receipt and action == "up_to_date"

        if action == "up_to_date" and not resume_unverified:
            result = {
                **base_result,
                "decision": "up_to_date",
                "reason": reason,
                "installed": False,
                "head_commit": head_commit,
            }
            write_closing_note(closing_note, result)
            return result

        if action in ("deferred", "error"):
            result = {
                **base_result,
                "decision": action,
                "reason": ", ".join(gate["reasons"])
                if action == "deferred" and gate["reasons"]
                else reason,
                "installed": False,
            }
            write_closing_note(closing_note, result)
            return result

        if dry_run:
            result = {
                **base_result,
                "decision": "dry_run_would_install"
                if not resume_unverified
                else "error",
                "reason": reason
                if not resume_unverified
                else "unverified_receipt_observation_pending",
                "installed": False,
            }
            write_closing_note(closing_note, result)
            return result

        if not resume_unverified:
            recheck = check_gate(
                heavy_bin,
                state_dir,
                max_queued=max_queued,
                max_status_age=max_status_age,
            )
            if not recheck["passed"]:
                result = {
                    **base_result,
                    "gate": recheck,
                    "decision": "deferred",
                    "reason": ", ".join(recheck["reasons"]),
                    "installed": False,
                }
                write_closing_note(closing_note, result)
                return result

            if head_commit != target_commit:
                run_cmd(
                    ["git", "-C", str(checkout), "merge", "--ff-only", target_commit],
                    timeout=30,
                )
                head_commit = run_cmd(
                    ["git", "-C", str(checkout), "rev-parse", "HEAD"], timeout=15
                ).strip()
                if head_commit != target_commit:
                    raise RuntimeError(
                        "Fast-forward merge did not reach target origin/main commit"
                    )

        p_install = installer.paths(home, checkout)
        p_install["state"] = state_dir
        if not no_start and (
            home != Path.home().resolve()
            or state_dir != (Path.home() / ".local/state/mac-ops").resolve()
        ):
            raise RuntimeError(
                "Live installation requires the real home and state directory"
            )
        if no_start and (
            home == Path.home().resolve()
            or state_dir != (home / ".local/state/mac-ops").resolve()
            or p_install["legacy"].exists()
        ):
            raise RuntimeError(
                "No-start installation requires an isolated home without legacy state"
            )

        status_after = status_before
        if marker_for_receipt:
            # Keep the last verified recovery receipt when superseding unverified B
            # with newer C (do not chain previous_receipt to unverified B).
            previous_receipt = marker_previous_receipt(pending_marker)
        else:
            previous_receipt = status_before["receipt"]
        if resume_unverified:
            install_started_at = float(
                pending_marker.get("started_at")
                or status_before.get("installed_at")
                or time.time()
            )
            target_release = status_before["release"]
            try:
                observation = observe_controller(
                    state_dir,
                    target_release=target_release,
                    install_started_at=install_started_at,
                    observe_seconds=observe_seconds,
                    poll_interval=poll_interval,
                )
            except (
                RuntimeError,
                OSError,
                ValueError,
                TypeError,
                subprocess.SubprocessError,
            ) as exc:
                observation = {"passed": False, "reasons": [str(exc)]}
        else:
            if status_before["receipt"]:
                installer.validate_release(p_install, status_before["release"])
            if installer.require_main_checkout(checkout) != target_commit:
                raise RuntimeError("Checkout changed before installation")
            install_started_at = time.time()
            if marker_for_receipt:
                # Keep marker on unverified B until receipt names C.
                write_observation_marker(
                    state_dir,
                    source_commit=status_before["source_commit"],
                    started_at=install_started_at,
                    previous_receipt=previous_receipt,
                    release=status_before.get("release"),
                )
            else:
                write_observation_marker(
                    state_dir,
                    source_commit=target_commit,
                    started_at=install_started_at,
                    previous_receipt=previous_receipt,
                )
            try:
                if no_start:
                    installer.install(
                        p_install,
                        checkout,
                        migrate=False,
                        no_start=True,
                        source_commit=target_commit,
                    )
                else:
                    command = [checkout / "install.sh"]
                    if p_install["legacy"].exists():
                        command.append("--migrate")
                    run_cmd(command, cwd=checkout, timeout=120)
                status_after = read_installation_status(checkout, state_dir)
                if status_after["source_commit"] != target_commit:
                    raise RuntimeError(
                        "Post-install receipt source_commit does not match target origin/main"
                    )
                write_observation_marker(
                    state_dir,
                    source_commit=target_commit,
                    started_at=install_started_at,
                    previous_receipt=previous_receipt,
                    release=status_after["release"],
                )
                observation = observe_controller(
                    state_dir,
                    target_release=status_after["release"],
                    install_started_at=install_started_at,
                    observe_seconds=observe_seconds,
                    poll_interval=poll_interval,
                )
            except (
                RuntimeError,
                OSError,
                ValueError,
                TypeError,
                subprocess.SubprocessError,
            ) as exc:
                observation = {"passed": False, "reasons": [str(exc)]}
                try:
                    status_after = read_installation_status(checkout, state_dir)
                except (
                    RuntimeError,
                    OSError,
                    ValueError,
                    TypeError,
                    subprocess.SubprocessError,
                ):
                    pass

        if not observation["passed"]:
            restored = None
            rollback_error = None
            if previous_receipt:
                try:
                    restored = rollback_to_release(
                        home,
                        checkout,
                        previous_receipt,
                        state_dir=state_dir,
                        no_start=no_start,
                    )
                except (
                    RuntimeError,
                    OSError,
                    ValueError,
                    TypeError,
                    subprocess.SubprocessError,
                ) as exc:
                    rollback_error = str(exc)
            if restored:
                clear_observation_marker(state_dir)
            result = {
                **base_result,
                "decision": "rolled_back" if restored else "error",
                "reason": "; ".join(observation["reasons"]),
                "installed": False,
                "head_commit": head_commit,
                "installed_source_commit": restored["source_commit"]
                if restored
                else status_after["source_commit"],
                "installed_release": restored["release"]
                if restored
                else status_after["release"],
                "release_name": restored["release_name"]
                if restored
                else status_after["release_name"],
                "observation": observation,
                "rollback_error": rollback_error,
            }
            write_closing_note(closing_note, result)
            return result

        clear_observation_marker(state_dir)
        result = {
            **base_result,
            "decision": "installed",
            "reason": "installed_and_verified",
            "installed": True,
            "head_commit": head_commit,
            "installed_source_commit": status_after["source_commit"],
            "installed_release": status_after["release"],
            "release_name": status_after["release_name"],
            "observation": observation,
        }
        write_closing_note(closing_note, result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkout",
        type=Path,
        help="Path to main mac-ops checkout (default: ~/Code/mac-ops)",
    )
    parser.add_argument("--home", type=Path, help="Home directory override for testing")
    parser.add_argument(
        "--state-dir",
        type=Path,
        help="State directory override (default: ~/.local/state/mac-ops)",
    )
    parser.add_argument(
        "--heavy-bin",
        type=Path,
        help="Path to heavy wrapper (default: ~/.local/bin/heavy)",
    )
    parser.add_argument(
        "--max-queued",
        type=int,
        default=3,
        help="Defer when heavy queue exceeds this count",
    )
    parser.add_argument(
        "--max-status-age",
        type=float,
        default=30.0,
        help="Max controller status age in seconds",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compare and check gate without installing",
    )
    parser.add_argument(
        "--closing-note",
        type=Path,
        help="Write a board-safe closing note with plain-text line 1",
    )
    parser.add_argument(
        "--strict-defer-exit", action="store_true", help="Exit 75 when deferred"
    )
    args = parser.parse_args(argv)

    result = run_install_if_behind(
        checkout=args.checkout,
        home=args.home,
        state_dir=args.state_dir,
        heavy_bin=args.heavy_bin,
        max_queued=args.max_queued,
        max_status_age=args.max_status_age,
        dry_run=args.dry_run,
        closing_note=args.closing_note,
    )
    print(format_closing_note(result).splitlines()[0], flush=True)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    if result["decision"] in ("error", "rolled_back"):
        return 2
    if result["decision"] == "deferred" and args.strict_defer_exit:
        return 75
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"install_if_behind: {exc}", file=sys.stderr)
        sys.exit(1)
