from __future__ import annotations

import json
import math
import os
import re
import socket
import subprocess
import sys
import time
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


BOARD_HOME = Path.home() / ".herdr-projects"
BOARD_TASKS = BOARD_HOME / "data" / "tasks"
BOARD_CMD = str(BOARD_HOME / "data" / "bin" / "herdr-projects")
HERDR_CMD = "/opt/homebrew/bin/herdr"
SYSCTL_CMD = "/usr/sbin/sysctl"
PS_CMD = "/bin/ps"
MAX_JSON_BYTES = 1_000_000
MAX_COMMAND_BYTES = 1_000_000
COMMAND_TIMEOUT = 4
TASK_DIR = re.compile(r"^(\d+)([a-e])?$", re.IGNORECASE)


def _command(args: list[str], label: str, timeout: float = COMMAND_TIMEOUT, env: dict[str, str] | None = None) -> tuple[Any, str | None]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env, check=False)
    except subprocess.TimeoutExpired:
        return None, f"{label} timed out"
    except OSError:
        return None, f"{label} could not start"
    if result.returncode:
        return None, f"{label} failed (exit {result.returncode})"
    if len(result.stdout.encode("utf-8", errors="replace")) > MAX_COMMAND_BYTES:
        return None, f"{label} output exceeded the size limit"
    return result.stdout, None


def _uint(value: Any, *, positive: bool = False, maximum: int = (1 << 63) - 1) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        number = int(value.strip())
    else:
        return None
    if number < (1 if positive else 0) or number > maximum:
        return None
    return number


def _sysctl(key: str, errors: list[str]) -> int | None:
    output, error = _command([SYSCTL_CMD, "-n", key], f"sysctl {key}")
    if error:
        errors.append(error)
        return None
    value = _uint(output.strip(), positive=True)
    if value is None:
        errors.append(f"sysctl {key} returned an invalid value")
    return value


def _parse_vm_stat(text: str, errors: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for name, pattern in {
        "page_size": r"page size of\s+(\d+)\s+bytes",
        "free": r"Pages free:\s*([\d,]+)\.?",
        "inactive": r"Pages inactive:\s*([\d,]+)\.?",
        "speculative": r"Pages speculative:\s*([\d,]+)\.?",
        "compressor": r"Pages occupied by compressor:\s*([\d,]+)\.?",
        "compressed_logical": r"Pages stored in compressor:\s*([\d,]+)\.?",
        "swapins": r"Swapins:\s*([\d,]+)\.?",
        "swapouts": r"Swapouts:\s*([\d,]+)\.?",
    }.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        if len(matches) != 1:
            errors.append(f"vm_stat is missing or has duplicate {name}")
            parsed[name] = None
            continue
        raw = matches[0].replace(",", "")
        value = _uint(raw, positive=name == "page_size")
        if value is None:
            errors.append(f"vm_stat returned an invalid {name}")
        parsed[name] = value
    return parsed


def _swap_used(text: str, errors: list[str]) -> int | None:
    matches = re.findall(r"\bused\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?)(?:i?B)?\b", text, re.IGNORECASE)
    if len(matches) != 1:
        errors.append("sysctl vm.swapusage returned an invalid used value")
        return None
    try:
        amount = Decimal(matches[0][0])
        unit = matches[0][1].upper()
        multiplier = Decimal(1024) ** {"": 0, "K": 1, "M": 2, "G": 3, "T": 4}[unit]
        result = int(amount * multiplier)
    except (InvalidOperation, OverflowError):
        result = -1
    if result < 0 or result > (1 << 63) - 1:
        errors.append("sysctl vm.swapusage returned an out-of-range used value")
        return None
    return result


def _admission() -> dict[str, Any]:
    output, error = _command([BOARD_CMD, "admission", "--json"], "board admission snapshot")
    if error:
        raise RuntimeError(error)
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("board admission returned invalid JSON") from exc
    if not isinstance(data, dict) or type(data.get("schema")) is not int or data["schema"] != 1:
        raise RuntimeError("board admission schema is unsupported")
    if _uint(data.get("limit")) is None:
        raise RuntimeError("board admission limit is invalid")
    seen: set[str] = set()
    for group in ("active", "waiting"):
        rows = data.get(group)
        if not isinstance(rows, list):
            raise RuntimeError(f"board admission {group} list is missing")
        for row in rows:
            if not isinstance(row, dict):
                raise RuntimeError("board admission task entry is invalid")
            task_id = row.get("id")
            if not isinstance(task_id, str) or task_id in seen:
                raise RuntimeError("board admission task identity is invalid or duplicated")
            parts = task_id.split("/")
            if len(parts) != 2 or parts[0] in ("", ".", "..") or ":" in parts[0] or not TASK_DIR.fullmatch(parts[1]):
                raise RuntimeError("board admission task identity is not local")
            if not isinstance(row.get("stage"), str) or not row["stage"]:
                raise RuntimeError("board admission task stage is missing")
            if group == "waiting" and row.get("state") not in ("yielded", "queued"):
                raise RuntimeError("board admission waiting state is invalid")
            seen.add(task_id)
    absent_sockets: dict[str, bool] = {}
    data["active"] = [row for row in data["active"] if not _agent_is_gone(row["id"], absent_sockets)]
    return data


def _socket_absent(path: str, cache: dict[str, bool]) -> bool:
    if path not in cache:
        with socket.socket(socket.AF_UNIX) as probe:
            probe.settimeout(1)
            try:
                probe.connect(path)
                cache[path] = False
            except (FileNotFoundError, ConnectionRefusedError):
                cache[path] = True
            except OSError:
                cache[path] = False
    return cache[path]


def _agent_is_gone(task_id: str, absent_sockets: dict[str, bool]) -> bool:
    try:
        task_file = BOARD_TASKS / task_id / "task.json"
        if task_file.stat().st_size > MAX_JSON_BYTES:
            return False
        task = json.loads(task_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(task, dict):
        return False
    if task.get("archivedAt") or task.get("stage") == "done":
        return True
    try:
        _, socket_path = _pane(task)
    except (KeyError, TypeError):
        return False
    return isinstance(socket_path, str) and bool(socket_path) and _socket_absent(socket_path, absent_sockets)


def board_admission_snapshot() -> dict[str, Any]:
    return _admission()


def board_agent_rss_census(admission: dict[str, Any] | None = None) -> dict[str, Any]:
    if admission is not None and not isinstance(admission, dict):
        raise ValueError("board admission snapshot is invalid")
    admission = admission if admission is not None else board_admission_snapshot()
    active = admission.get("active")
    if not isinstance(active, list):
        raise ValueError("board admission active list is missing")
    if not active:
        return {"schema": 1, "agents": [], "rss_bytes": [], "complete": True, "errors": []}
    errors: list[str] = []
    tasks = _read_slot_tasks(active)
    agents = _collect_agents(tasks, errors)
    rss_bytes: list[int] = []
    for row in agents:
        value = row.get("rss_bytes")
        if type(value) is int and value > 0:
            rss_bytes.append(value)
    complete = len(rss_bytes) == len(active) and not errors
    return {"schema": 1, "agents": agents, "rss_bytes": rss_bytes, "complete": complete, "errors": errors}


def compressor_snapshot() -> dict[str, float]:
    output, error = _command(["/usr/bin/vm_stat"], "vm_stat compressor counter")
    if error:
        raise RuntimeError(error)
    errors: list[str] = []
    vm = _parse_vm_stat(output, errors)
    page_size = vm.get("page_size")
    compressor_pages = vm.get("compressor")
    if errors or page_size is None or compressor_pages is None:
        raise RuntimeError("vm_stat compressor counter is incomplete")
    return {
        "compressor_bytes": page_size * compressor_pages,
        "sampled_monotonic": time.monotonic(),
    }


def _read_slot_tasks(active: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    active = _admission()["active"] if active is None else active
    if not active:
        return []
    if not BOARD_TASKS.is_dir():
        raise RuntimeError("task directory is unavailable")
    root = BOARD_TASKS.resolve(strict=True)
    slots: list[dict[str, Any]] = []
    for row in active:
        task_id = row["id"]
        task_dir = BOARD_TASKS / task_id
        try:
            if not task_dir.resolve(strict=True).is_relative_to(root):
                raise RuntimeError("task path escaped the task directory")
            task_file = task_dir / "task.json"
            if task_file.stat().st_size > MAX_JSON_BYTES:
                raise RuntimeError("task metadata exceeded the size limit")
            task = json.loads(task_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"task metadata is unreadable for {task_id}") from exc
        if not isinstance(task, dict) or task.get("id") != task_id:
            raise RuntimeError(f"task metadata identity is invalid for {task_id}")
        if task.get("stage") != row["stage"]:
            raise RuntimeError(f"task activity changed during collection for {task_id}")
        slots.append({"id": task_id, "stage": row["stage"], "link": task.get("link")})
    return slots


def local_limit() -> int | None:
    path = BOARD_TASKS.parent.parent / "settings" / "config.json"
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        nested = data.get("board", {})
        values = [data["board.agents"]] if "board.agents" in data else []
        if isinstance(nested, dict) and "agents" in nested:
            values.append(nested["agents"])
        return _uint(values[0]) if len(values) == 1 else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def local_slot_tasks() -> list[dict[str, Any]]:
    no_slot = {"todo", "progress", "queued", "stopped", "nosummary", "asks", "approval",
               "reviewneeds", "plan", "failed", "done", "attempts", "pick", "tried", "after"}
    if not BOARD_TASKS.is_dir():
        raise RuntimeError("task directory is unavailable")
    slots: list[dict[str, Any]] = []
    try:
        for repo in BOARD_TASKS.iterdir():
            if not repo.is_dir() or repo.is_symlink():
                continue
            for folder in repo.iterdir():
                if not TASK_DIR.fullmatch(folder.name) or not folder.is_dir():
                    continue
                file = folder / "task.json"
                if folder.is_symlink() or file.stat().st_size > MAX_JSON_BYTES:
                    raise RuntimeError("unsafe or oversized task metadata")
                task = json.loads(file.read_text(encoding="utf-8"))
                task_id = repo.name + "/" + folder.name
                if not isinstance(task, dict) or task.get("id") != task_id:
                    raise RuntimeError("task metadata identity is invalid")
                if task.get("archivedAt") or task.get("stage") in no_slot:
                    continue
                slots.append({"id": task_id, "stage": task.get("stage"), "link": task.get("link")})
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError("local task census is incomplete") from exc
    return slots


def running_count(warnings: list[str] | None = None) -> int:
    try:
        return len(_admission()["active"])
    except RuntimeError as exc:
        if warnings is not None:
            warnings.append(str(exc) + "; using local slot upper bound")
        return len(local_slot_tasks())


def _heavy_module() -> Any:
    module_dir = str(Path(__file__).resolve().parent)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    try:
        import heavy
    except ImportError as exc:
        raise RuntimeError("heavy helper is unavailable beside the controller") from exc
    return heavy


def _validate_identity(identity: Any, label: str, heavy: Any) -> str:
    if not isinstance(identity, dict):
        raise RuntimeError(f"heavy registry {label} identity is missing")
    pid = identity.get("pid")
    uid = identity.get("uid")
    start = identity.get("start")
    boot_id = identity.get("boot_id")
    if type(pid) is not int or pid <= 0 or type(uid) is not int or uid != os.getuid():
        raise RuntimeError(f"heavy registry {label} identity is invalid")
    if not isinstance(start, str) or not start:
        raise RuntimeError(f"heavy registry {label} start identity is invalid")
    try:
        heavy._start_epoch(start)
    except Exception as exc:
        raise RuntimeError(f"heavy registry {label} start identity is invalid") from exc
    if not isinstance(boot_id, str) or not re.fullmatch(r"[1-9][0-9]*", boot_id):
        raise RuntimeError(f"heavy registry {label} boot identity is invalid")
    if "pgid" in identity and (type(identity["pgid"]) is not int or identity["pgid"] <= 0):
        raise RuntimeError(f"heavy registry {label} process group is invalid")
    return boot_id


class _HeavyCensusRace(RuntimeError):
    pass


def _active_group_rss(heavy: Any, processes: dict[int, Any], pgids: set[int]) -> list[int]:
    if not pgids:
        return []
    output, error = _command([PS_CMD, "-axo", "pid=,pgid=,rss=,lstart="], "heavy RSS snapshot")
    if error:
        raise RuntimeError(error)
    totals = {pgid: 0 for pgid in pgids}
    matched = set()
    for line in output.splitlines():
        match = re.match(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(.+?)\s*$", line)
        if not match:
            raise RuntimeError("heavy RSS snapshot is malformed")
        pid, pgid, rss_kib = (int(match.group(index)) for index in range(1, 4))
        info = processes.get(pid)
        if info is None:
            if pgid in pgids:
                raise _HeavyCensusRace("heavy RSS process identity is unavailable")
            continue
        try:
            ps_epoch = heavy._start_epoch(match.group(4).strip())
        except Exception as exc:
            raise RuntimeError("heavy RSS process start identity is invalid") from exc
        if info.pgid != pgid or int(info.start_epoch) != int(ps_epoch):
            if pgid in pgids or info.pgid in pgids:
                raise _HeavyCensusRace("heavy RSS process identity changed during sampling")
            continue
        if pgid in pgids:
            totals[pgid] += rss_kib * 1024
            matched.add(pid)
    for pid, info in processes.items():
        if info.uid == os.getuid() and info.pgid in pgids and pid not in matched:
            raise _HeavyCensusRace("heavy RSS process census is incomplete")
    if any(total <= 0 for total in totals.values()):
        raise _HeavyCensusRace("heavy workload RSS is unavailable")
    return sorted(totals.values())


def _active_heavy_census() -> dict[str, Any]:
    heavy = _heavy_module()
    state_root = Path.home() / ".local" / "state" / "mac-ops"
    registry_path = state_root / heavy.REGISTRY_NAME
    if not registry_path.is_dir() or registry_path.is_symlink():
        raise RuntimeError("heavy registry is unavailable")
    boot_id = heavy.kernel_boot_identity()
    if not isinstance(boot_id, str) or not re.fullmatch(r"[1-9][0-9]*", boot_id):
        raise RuntimeError("kernel boot identity is invalid")
    processes = heavy.process_table()
    registry = heavy.Registry(registry_path)
    try:
        with registry.lock(exclusive=False):
            records = registry.records()
    except Exception as exc:
        raise RuntimeError("heavy registry records are unavailable or corrupt") from exc

    active = 0
    active_workload_pgids = set()
    for record in records:
        state = record.get("state")
        if not isinstance(state, str) or not state:
            raise RuntimeError("heavy registry state is invalid")
        supervisor_boot = _validate_identity(record.get("supervisor"), "supervisor", heavy)
        workload = record.get("workload")
        workload_boot = None
        if workload is not None:
            workload_boot = _validate_identity(workload, "workload", heavy)
            if workload_boot != supervisor_boot:
                raise RuntimeError("heavy registry workload boot identity differs")
        try:
            alive, supervisor_alive = heavy._record_live(record, processes)
        except Exception as exc:
            raise RuntimeError("heavy registry process identity could not be checked") from exc
        if supervisor_boot != boot_id:
            continue
        if state not in ("complete", "removed") or alive or supervisor_alive:
            active += 1
            if alive and isinstance(workload, dict):
                pgid = workload.get("pgid")
                if type(pgid) is not int or pgid <= 0:
                    raise RuntimeError("active heavy workload process group is invalid")
                active_workload_pgids.add(pgid)

    try:
        legacy = heavy.legacy_slot_count(processes)
    except Exception as exc:
        raise RuntimeError("legacy heavy slot census is unavailable or corrupt") from exc
    if type(legacy) is not int or legacy < 0:
        raise RuntimeError("legacy heavy slot census is invalid")
    job_rss_bytes = _active_group_rss(heavy, processes, active_workload_pgids)
    return {
        "boot_id": boot_id,
        "registry_active": active,
        "legacy_active": legacy,
        "active": active + legacy,
        "job_rss_bytes": job_rss_bytes,
    }


def active_heavy_census() -> dict[str, Any]:
    for attempt in range(3):
        try:
            return _active_heavy_census()
        except _HeavyCensusRace:
            if attempt == 2:
                raise
    raise AssertionError("heavy census retries exhausted")


def _pane(task: dict[str, Any]) -> tuple[Any, Any]:
    link = task.get("link")
    if not isinstance(link, dict):
        return None, None
    if task["stage"] == "reviewing":
        reviewer = link.get("reviewer")
        if isinstance(reviewer, dict):
            return reviewer.get("pane"), reviewer.get("socket") or link.get("socket")
        if isinstance(reviewer, str):
            return reviewer, link.get("socket")
        return None, None
    return link.get("pane"), link.get("socket")


def _process_snapshot(errors: list[str]) -> dict[int, dict[str, Any]] | None:
    output, error = _command([PS_CMD, "-axo", "pid=,ppid=,pgid=,rss=,%cpu="], "ps process snapshot")
    if error:
        errors.append(error)
        return None
    processes: dict[int, dict[str, Any]] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 5:
            errors.append("ps returned a malformed process row")
            return None
        pid, ppid, pgid, rss = (_uint(value, positive=index in (0, 2), maximum=(1 << 31) - 1 if index < 3 else (1 << 63) - 1) for index, value in enumerate(fields[:4]))
        try:
            cpu = float(fields[4])
        except ValueError:
            cpu = float("nan")
        if pid is None or ppid is None or pgid is None or rss is None or not math.isfinite(cpu) or cpu < 0:
            errors.append("ps returned an invalid process measurement")
            return None
        processes[pid] = {"ppid": ppid, "pgid": pgid, "rss": rss, "cpu": cpu}
    if not processes:
        errors.append("ps returned no process rows")
        return None
    return processes


def _selected_processes(processes: dict[int, dict[str, Any]], process_info: dict[str, Any]) -> tuple[set[int] | None, str | None]:
    children = defaultdict(list)
    groups = defaultdict(list)
    for pid, record in processes.items():
        children[record["ppid"]].append(pid)
        groups[record["pgid"]].append(pid)
    foreground = process_info.get("foreground_processes")
    if not isinstance(foreground, list):
        return None, "foreground process list is missing"
    foreground_pids = set()
    for item in foreground:
        if not isinstance(item, dict):
            return None, "foreground process entry is invalid"
        foreground_pid = _uint(item.get("pid"), positive=True, maximum=(1 << 31) - 1)
        if foreground_pid is None:
            return None, "foreground process pid is invalid"
        foreground_pids.add(foreground_pid)
    missing = foreground_pids.difference(processes)
    shell_pid = _uint(process_info.get("shell_pid"), positive=True, maximum=(1 << 31) - 1)
    if shell_pid is None or shell_pid not in processes:
        return None, "pane shell process is missing"
    pgid = _uint(process_info.get("foreground_process_group_id"), positive=True, maximum=(1 << 31) - 1)
    if pgid is None and not foreground_pids:
        return None, "foreground process group is missing"
    seeds = set(foreground_pids)
    if pgid is not None:
        seeds.update(groups.get(pgid, []))
    seeds.update(children.get(shell_pid, []))
    selected = set()
    pending = deque(seeds)
    expanded_groups = set()
    while pending:
        pid = pending.popleft()
        if pid in selected or pid not in processes:
            continue
        selected.add(pid)
        pending.extend(children.get(pid, []))
        group = processes[pid]["pgid"]
        if group not in expanded_groups:
            expanded_groups.add(group)
            pending.extend(groups.get(group, []))
    if missing:
        return None, "foreground process exited during collection"
    if not selected:
        return None, "pane has no measurable agent processes"
    return selected, None


def _collect_agents(tasks: list[dict[str, Any]], errors: list[str]) -> list[dict[str, Any]]:
    if not tasks:
        return []
    processes = _process_snapshot(errors)
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for task in tasks:
        row: dict[str, Any] = {"id": task["id"], "rss_bytes": None, "cpu_cores": None, "pids": [], "pgids": []}
        pane, socket_path = _pane(task)
        if not isinstance(pane, str) or not pane.strip() or not isinstance(socket_path, str) or not socket_path.strip():
            errors.append(f"task {task['id']} has no pane/socket link for stage {task['stage']}")
            rows.append(row)
            continue
        env = {key: value for key, value in os.environ.items() if not key.startswith("HERDR_")}
        env["HERDR_SOCKET_PATH"] = socket_path
        output, error = _command([HERDR_CMD, "pane", "process-info", "--pane", pane], f"pane process info for {task['id']}", env=env)
        if error:
            errors.append(error)
            rows.append(row)
            continue
        try:
            data = json.loads(output)
            info = data.get("result", {}).get("process_info") if isinstance(data, dict) else None
        except (json.JSONDecodeError, AttributeError):
            info = None
        if not isinstance(info, dict):
            errors.append(f"pane process info is invalid for {task['id']}")
            rows.append(row)
            continue
        if processes is None:
            rows.append(row)
            continue
        selected, reason = _selected_processes(processes, info)
        if reason or selected is None:
            errors.append(f"{task['id']}: {reason}")
            rows.append(row)
            continue
        shared = selected.intersection(seen)
        if shared:
            errors.append(f"task {task['id']} shares processes with another pane")
            rows.append(row)
            continue
        seen.update(selected)
        row["pids"] = sorted(selected)
        row["pgids"] = sorted({processes[pid]["pgid"] for pid in selected})
        row["rss_bytes"] = sum(processes[pid]["rss"] for pid in selected) * 1024
        row["cpu_cores"] = round(sum(processes[pid]["cpu"] for pid in selected) / 100.0, 4)
        row["process_info"] = info
        rows.append(row)
    return rows


def collect(include_board: bool = True) -> dict[str, Any]:
    if type(include_board) is not bool:
        raise ValueError("include_board must be a boolean")
    errors: list[str] = []
    result: dict[str, Any] = {
        "sampling_time": time.time(), "sampled_at": time.time(),
        "sample_duration_seconds": None, "board_response_seconds": None,
        "disk_wait_ratio": None, "disk_wait_processes": None, "total_bytes": None, "cores": None, "page_size": None,
        "free_percent": None, "pressure": None, "load1": None, "load5": None,
        "available_bytes": None, "compressor_bytes": None, "compressed_logical_bytes": None,
        "swap_used_bytes": None, "swapins": None, "swapouts": None, "running": None,
        "agents": [], "waiting": None, "waiting_ids": [], "board_limit": None,
        "running_source": "unavailable", "complete": False, "errors": errors,
    }
    result["total_bytes"] = _sysctl("hw.memsize", errors)
    result["cores"] = _sysctl("hw.ncpu", errors)
    result["page_size"] = _sysctl("hw.pagesize", errors)
    pressure = _sysctl("kern.memorystatus_vm_pressure_level", errors)
    if pressure not in (1, 2, 4):
        if pressure is not None:
            errors.append("memory pressure level is outside the expected values")
        pressure = None
    result["pressure"] = pressure
    free_text, error = _command(["/usr/bin/memory_pressure", "-Q"], "memory_pressure")
    if error:
        errors.append(error)
    else:
        matches = re.findall(r"System-wide memory free percentage:\s*(\d{1,3})%", free_text, re.IGNORECASE)
        if len(matches) == 1 and int(matches[0]) <= 100:
            result["free_percent"] = int(matches[0])
        else:
            errors.append("memory_pressure returned an invalid free percentage")
    vm_text, error = _command(["/usr/bin/vm_stat"], "vm_stat")
    vm: dict[str, Any] | None = None
    if error:
        errors.append(error)
    else:
        vm = _parse_vm_stat(vm_text, errors)
        if result["page_size"] is not None and vm["page_size"] is not None and result["page_size"] != vm["page_size"]:
            errors.append("vm_stat page size does not match sysctl")
            vm["page_size"] = None
        if result["page_size"] is None:
            result["page_size"] = vm["page_size"]
    if vm and result["page_size"] is not None:
        result["compressor_bytes"] = None if vm["compressor"] is None else vm["compressor"] * result["page_size"]
        result["compressed_logical_bytes"] = None if vm["compressed_logical"] is None else vm["compressed_logical"] * result["page_size"]
        result["swapins"] = vm["swapins"]
        result["swapouts"] = vm["swapouts"]
        if result["total_bytes"] is not None and result["free_percent"] is not None and all(vm[key] is not None for key in ("free", "inactive", "speculative")):
            pressure_available = result["total_bytes"] * result["free_percent"] // 100
            vm_available = (vm["free"] + vm["inactive"] + vm["speculative"]) * result["page_size"]
            result["available_bytes"] = min(pressure_available, vm_available)
    swap_text, error = _command([SYSCTL_CMD, "-n", "vm.swapusage"], "sysctl vm.swapusage")
    if error:
        errors.append(error)
    else:
        result["swap_used_bytes"] = _swap_used(swap_text, errors)
    try:
        loads = os.getloadavg()
        if len(loads) < 2 or not all(math.isfinite(value) and value >= 0 for value in loads[:2]):
            raise ValueError
        result["load1"], result["load5"] = loads[0], loads[1]
    except (OSError, ValueError):
        errors.append("load averages are unavailable or invalid")
    states, error = _command([PS_CMD, "-axo", "stat="], "ps disk-wait snapshot")
    if error:
        errors.append(error)
    else:
        rows = [row.strip() for row in states.splitlines() if row.strip()]
        if not rows or any(not re.fullmatch(r"[A-Za-z+<>=-]+", row) for row in rows):
            rejected = [row for row in rows if not re.fullmatch(r"[A-Za-z+<>=-]+", row)]
            errors.append("ps returned invalid process states: " + repr(rejected[:3]))
        else:
            blocked = sum(row.startswith(("U", "D")) for row in rows)
            result["disk_wait_processes"] = blocked
            if result["cores"]:
                result["disk_wait_ratio"] = blocked / result["cores"]
    if not include_board:
        result["sample_duration_seconds"] = time.time() - result["sampled_at"]
        result["complete"] = not errors
        return result
    return collect_board(result)


def collect_board(result: dict[str, Any], include_agents: bool = True) -> dict[str, Any]:
    if type(include_agents) is not bool:
        raise ValueError("include_agents must be a boolean")
    errors = result["errors"]
    try:
        board_started = time.monotonic()
        admission = _admission()
        result["board_response_seconds"] = time.monotonic() - board_started
        result["running"] = len(admission["active"])
        result["running_source"] = "board_admission"
        result["board_limit"] = admission["limit"]
        result["waiting"] = len(admission["waiting"])
        result["waiting_ids"] = [row["id"] for row in admission["waiting"]]
        if include_agents:
            tasks = _read_slot_tasks(admission["active"])
            result["agents"] = _collect_agents(tasks, errors)
        else:
            errors.append("agent census skipped during critical pressure")
    except RuntimeError as exc:
        errors.append(f"task enumeration failed: {exc}")
        result["board_limit"] = local_limit()
        try:
            tasks = local_slot_tasks()
            result["running"] = len(tasks)
            result["running_source"] = "local_upper_bound"
        except RuntimeError as fallback:
            errors.append(str(fallback))
    result["sample_duration_seconds"] = time.time() - result["sampled_at"]
    result["complete"] = not errors
    return result


if __name__ == "__main__":
    json.dump(collect(), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
