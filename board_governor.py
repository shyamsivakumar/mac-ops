#!/usr/bin/env python3
"""Publish safe heavy-work capacity and report board admission."""
import argparse
import dataclasses
import fcntl
import json
import math
import os
import re
import stat
from pathlib import Path
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import agent_heavy_wait_pause
import board_resources
import board_restart

STATE_DIR = Path.home() / ".local" / "state" / "mac-ops"
BOARD = Path.home() / ".herdr-projects" / "data" / "bin" / "herdr-projects"
DEFAULTS = SCRIPT_DIR / "board_governor.json"
CONFIG = DEFAULTS
STATE = STATE_DIR / "board-governor.state.json"
CAPACITY = STATE_DIR / "capacity.json"
CAPACITY_STATE = STATE_DIR / "capacity-state.json"
STATUS = STATE_DIR / "controller-status.json"
HOST_HEADROOM_KEY = "min_headroom_bytes_by_host"
MAX_HOST_HEADROOM_BYTES = 64 * 1024 ** 3
AGENT_HEAVY_PAUSE_STATE = STATE_DIR / "agent-heavy-wait-pause.json"
LOG = STATE_DIR / "controller.jsonl"
LOCK = STATE_DIR / "controller.lock"
CONTROLLER_INTERVAL_SECONDS = 5.0
CPU_SMOOTHING_SAMPLES = 3
CAPACITY_MAX_AGE_SECONDS = 30.0
HEAVY_GROWTH_HOLD_SECONDS = 60.0
HEAVY_MAX_SAMPLE_GAP_SECONDS = CONTROLLER_INTERVAL_SECONDS * 2
HEAVY_SLOT_MEMORY_BYTES = 6 * 1024 ** 3
HEAVY_SLOT_CPU_CORES = 1.0
HEAVY_SLOT_MEMORY_FLOOR_BYTES = 2 * 1024 ** 3
HEAVY_MEMORY_RESERVE_BYTES = 6 * 1024 ** 3
HEAVY_MEMORY_RESERVE_FRACTION = 0.2
HEAVY_CPU_RESERVE_FRACTION = 0.2
HEAVY_COMPRESSOR_MAX_GROWTH_BYTES_PER_SECOND = 1024 ** 2
HEAVY_RSS_COST_MARGIN = 1.5
BOARD_GROWTH_HOLD_SECONDS = 60.0
BOARD_AGENT_MEMORY_CAP_BYTES = 2 * 1024 ** 3
BOARD_AGENT_MEMORY_BYTES = BOARD_AGENT_MEMORY_CAP_BYTES
BOARD_AGENT_CPU_CORES = 0.8


def _rss_percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile / 100.0
    low = int(__import__('math').floor(rank))
    high = int(__import__('math').ceil(rank))
    if low == high:
        return ordered[low]
    weight = rank - low
    return int(ordered[low] * (1.0 - weight) + ordered[high] * weight)


def _board_agent_memory_budget_bytes(agent_census, cfg, *, active):
    cap = BOARD_AGENT_MEMORY_CAP_BYTES
    if type(active) is not int or active < 0:
        raise ValueError("Board active count is invalid")
    if active == 0:
        return cap, None, "planning_cap"
    if (not isinstance(agent_census, dict) or agent_census.get("schema") != 1
            or not agent_census.get("complete")):
        return cap, None, "planning_cap"
    rss_bytes = agent_census.get("rss_bytes")
    if (not isinstance(rss_bytes, list) or len(rss_bytes) < active
            or any(type(value) is not int or value <= 0 for value in rss_bytes)):
        return cap, None, "planning_cap"
    p90 = _rss_percentile(rss_bytes, 90)
    if p90 is None or p90 <= 0:
        return cap, None, "planning_cap"
    budget = int(math.ceil(p90 * cfg["cost_margin"]))
    return min(cap, max(budget, p90)), p90, "measured_p90"


def command(args, *, timeout=4):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout).stdout


def number(value, name, low=0, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < low or (high is not None and value > high):
        raise ValueError(f"{name} outside supported range")
    return value


def config(path):
    values = json.loads(path.read_text())
    defaults = json.loads(DEFAULTS.read_text())
    if isinstance(values, dict):
        values.setdefault("agent_heavy_wait_pause", False)
        values.setdefault("agent_restart", True)
        values.setdefault(HOST_HEADROOM_KEY, {})
    if not isinstance(values, dict) or set(values) != set(defaults):
        raise ValueError("Config must contain exactly the documented reserve, signal, and sample-age fields")
    for key, value in values.items():
        if key not in ("agent_heavy_wait_pause", "agent_restart", HOST_HEADROOM_KEY):
            number(value, key)
    if type(values["agent_heavy_wait_pause"]) is not bool:
        raise ValueError("agent_heavy_wait_pause must be true or false")
    if type(values["agent_restart"]) is not bool:
        raise ValueError("agent_restart must be true or false")
    for key in ("memory_reserve_fraction", "cpu_reserve_fraction"):
        number(values[key], key, 0, 1)
    number(values["cost_margin"], "cost_margin", 1)
    number(values["warning_load_fraction"], "warning_load_fraction", 0.001, 1)
    number(values["critical_load_multiplier"], "critical_load_multiplier", 1)
    if values["critical_load_multiplier"] <= values["warning_load_fraction"]:
        raise ValueError("critical_load_multiplier must exceed warning_load_fraction")
    for key in ("growth_hold_seconds", "max_sample_gap_seconds", "max_sample_age_seconds"):
        number(values[key], key, 1)
    for key in ("swapout_bytes_per_second", "swap_growth_bytes_per_second",
                "compressor_growth_bytes_per_second"):
        number(values[key], key, 0)
    number(values["disk_wait_ratio_threshold"], "disk_wait_ratio_threshold", 0)
    number(values["board_response_seconds_threshold"], "board_response_seconds_threshold", 0.001)
    hosts = values[HOST_HEADROOM_KEY]
    if not isinstance(hosts, dict):
        raise ValueError("min_headroom_bytes_by_host must map host names to headroom bytes")
    normalized = {}
    for name, headroom in hosts.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("min_headroom_bytes_by_host names a host")
        if isinstance(headroom, bool) or not isinstance(headroom, int):
            raise ValueError("min_headroom_bytes must be an integer")
        number(headroom, "min_headroom_bytes", 1, MAX_HOST_HEADROOM_BYTES)
        key = name.strip().lower()
        if key in normalized:
            raise ValueError("min_headroom_bytes_by_host names one host twice")
        normalized[key] = headroom
    return values


def atomic_json(path, value):
    path = Path(path)
    if path.parent != STATE_DIR:
        raise ValueError("Controller state must stay under ~/.local/state/mac-ops")
    _ensure_state_dir(create=True)
    uid = os.getuid()
    try:
        info = os.lstat(str(path))
    except FileNotFoundError:
        info = None
    if info is not None and (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_mode & 0o077):
        raise ValueError("Controller state file is unsafe")
    temp = path.parent / ("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(temp), flags, 0o600)
    try:
        raw = (json.dumps(value, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("Controller state write made no progress")
            view = view[written:]
        os.fsync(fd)
    except Exception:
        os.close(fd)
        try:
            os.unlink(str(temp))
        except OSError:
            pass
        raise
    else:
        os.close(fd)
    os.replace(str(temp), str(path))
    dir_fd = os.open(str(path.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def decision(reading, previous, cfg, current, now):
    memory_floor = 2 * 1024 ** 3
    cpu_floor = 0.8
    reading = reading if isinstance(reading, dict) else {}
    previous = previous if isinstance(previous, dict) else {}

    def finite(value, low=0, high=None):
        try:
            return (not isinstance(value, bool) and isinstance(value, (int, float))
                    and math.isfinite(value) and value >= low and (high is None or value <= high))
        except OverflowError:
            return False

    def count(value):
        return finite(value) and int(value) == value

    current_valid = count(current)
    current_value = int(current) if current_valid else 0
    now_valid = finite(now)
    now_value = float(now) if now_valid else 0.0

    pressure = reading.get("pressure")
    pressure_known = not isinstance(pressure, bool) and pressure in (1, 2, 4)
    cores_raw = reading.get("cores")
    cores_known = finite(cores_raw, 0.000001)
    cores = float(cores_raw) if cores_known else None
    loads = [reading.get(key) for key in ("load1", "load5")]
    valid_loads = [float(value) for value in loads if finite(value)]
    load = max(valid_loads) if valid_loads else None
    critical_pressure = pressure_known and pressure == 4
    critical_load = cores is not None and any(value >= cfg["critical_load_multiplier"] * cores
                                               for value in valid_loads)
    critical = critical_pressure or critical_load
    running_raw = reading.get("running")
    running_valid = count(running_raw)
    running = int(running_raw) if running_valid else None

    previous_machine = previous.get("machine")
    machine_shape_valid = (isinstance(previous_machine, list) and len(previous_machine) == 2
                           and finite(previous_machine[0], 0.000001)
                           and finite(previous_machine[1], 0.000001))
    total_raw = reading.get("total_bytes")
    total_known = finite(total_raw, 0.000001)
    total_bytes = float(total_raw) if total_known else None
    same_machine = (machine_shape_valid and cores is not None and total_bytes is not None
                    and previous_machine == [cores, total_bytes])
    prior_memory_cost = previous.get("memory_cost")
    prior_cpu_cost = previous.get("cpu_cost")
    memory_cost = max(memory_floor, float(prior_memory_cost)) if same_machine and finite(prior_memory_cost) else memory_floor
    cpu_cost = max(cpu_floor, float(prior_cpu_cost)) if same_machine and finite(prior_cpu_cost) else cpu_floor
    state = {}
    if cores is not None and total_bytes is not None:
        state["machine"] = [cores, total_bytes]
    state["memory_cost"] = memory_cost
    state["cpu_cost"] = cpu_cost

    compressor_rate = None
    swap_used_rate = None

    def result(target, reason, fit=None, memory_headroom=None, cpu_headroom=None,
               swap_rate=None, ceiling=None, vetoes=None, start_allowed=False, force=False):
        if not start_allowed:
            target = min(target, running) if running_valid else 0
        required = force or (running_valid and target < running)
        return state, {"current": current_value, "running": running, "target": int(target),
                       "fit": fit, "reason": reason, "memory_cost_bytes": memory_cost,
                       "cpu_cost_cores": cpu_cost, "memory_headroom_bytes": memory_headroom,
                       "cpu_headroom_cores": cpu_headroom, "swapout_bytes_per_second": swap_rate,
                       "compressor_growth_bytes_per_second": compressor_rate,
                       "swap_growth_bytes_per_second": swap_used_rate,
                       "ceiling": ceiling, "vetoes": list(vetoes or []),
                       "start_allowed": bool(start_allowed), "enforcement_required": bool(required)}

    if critical:
        vetoes = []
        if critical_pressure:
            vetoes.append("critical_pressure")
        if critical_load:
            vetoes.append("critical_load")
        return result(0, "critical", fit=0, ceiling=0, vetoes=vetoes, force=True)

    vetoes = []
    if not current_valid:
        vetoes.append("invalid_current")
    if not now_valid:
        vetoes.append("invalid_now")

    free_percent = reading.get("free_percent")
    if not finite(free_percent, 0, 100):
        free_bytes = reading.get("available_bytes")
        free_percent = 100 * free_bytes / total_bytes if total_bytes and finite(free_bytes, 0, total_bytes) else None
    warning_pressure = (pressure_known and pressure == 2
                        and (free_percent is None or free_percent <= 30))
    warning_load = (cores is not None and any(value >= cfg["warning_load_fraction"] * cores
                                               for value in valid_loads))
    if warning_pressure:
        vetoes.append("warning_pressure")
    if warning_load:
        vetoes.append("warning_load")

    available_raw = reading.get("available_bytes")
    available_known = finite(available_raw)
    available = float(available_raw) if available_known else None
    reserve = None
    if total_bytes is not None:
        reserve = max(cfg["memory_reserve_bytes"], total_bytes * cfg["memory_reserve_fraction"])
    memory_headroom = max(0.0, available - reserve) if available is not None and reserve is not None else None
    core_reserve = cores * (1 - cfg["cpu_reserve_fraction"]) if cores is not None else None
    cpu_headroom = max(0.0, core_reserve - load) if core_reserve is not None and load is not None else None
    memory_violation = (available is not None and reserve is not None and available < reserve)
    if memory_violation:
        vetoes.append("memory_reserve")

    sample_time_raw = reading.get("sampled_at")
    duration_raw = reading.get("sample_duration_seconds")
    sample_time_known = finite(sample_time_raw)
    duration_known = finite(duration_raw)
    sample_time = float(sample_time_raw) if sample_time_known else None
    duration = float(duration_raw) if duration_known else None
    age = now_value - sample_time if now_valid and sample_time is not None else None
    fresh = (age is not None and 0 <= age <= cfg["max_sample_age_seconds"]
             and duration is not None and duration <= cfg["max_sample_age_seconds"])
    if age is not None and age > cfg["max_sample_age_seconds"]:
        vetoes.append("stale_sample")
    if age is not None and age < 0:
        vetoes.append("future_sample")

    errors = reading.get("errors")
    errors_valid = isinstance(errors, list) and not errors
    if not errors_valid:
        vetoes.append("sample_errors")

    swapouts_raw = reading.get("swapouts")
    page_size_raw = reading.get("page_size")
    compressor_raw = reading.get("compressor_bytes")
    swap_used_raw = reading.get("swap_used_bytes")
    board_response_raw = reading.get("board_response_seconds")
    disk_wait_raw = reading.get("disk_wait_ratio")
    swapouts_known = count(swapouts_raw)
    page_size_known = count(page_size_raw) and page_size_raw > 0
    compressor_known = finite(compressor_raw)
    swap_used_known = finite(swap_used_raw)
    board_response_known = finite(board_response_raw)
    if not board_response_known:
        vetoes.append("unknown_board_latency")
    disk_wait_known = finite(disk_wait_raw)
    if not disk_wait_known:
        vetoes.append("unknown_disk_wait")

    agents_raw = reading.get("agents")
    agents_valid = isinstance(agents_raw, list) and running_valid and len(agents_raw) == running
    agent_costs = []
    if agents_valid:
        for agent in agents_raw:
            if not isinstance(agent, dict) or not finite(agent.get("rss_bytes")) or not finite(agent.get("cpu_cores")):
                agents_valid = False
                break
            agent_costs.append((float(agent["rss_bytes"]), float(agent["cpu_cores"])))
    declared_complete = reading.get("complete") is True
    if declared_complete and agents_valid and errors_valid and cores is not None and total_bytes is not None and agent_costs:
        memory_cost = max(memory_cost, memory_floor,
                          max(item[0] for item in agent_costs) * cfg["cost_margin"])
        cpu_cost = max(cpu_cost, cpu_floor,
                       max(item[1] for item in agent_costs) * cfg["cost_margin"])
        state["memory_cost"] = memory_cost
        state["cpu_cost"] = cpu_cost

    required_sample = (current_valid and now_valid and running_valid and pressure_known and cores is not None
                       and len(valid_loads) == 2 and total_bytes is not None and available is not None
                       and sample_time is not None and duration is not None and fresh and errors_valid
                       and swapouts_known and page_size_known and compressor_known and swap_used_known
                       and board_response_known and disk_wait_known and agents_valid)
    complete = declared_complete and required_sample
    if not declared_complete:
        vetoes.append("incomplete_sample")
    elif not required_sample:
        vetoes.append("unknown_input")

    ceiling = None
    if cores is not None and total_bytes is not None:
        memory_ceiling = math.floor(max(0.0, total_bytes - reserve) / memory_cost)
        cpu_ceiling = math.floor(max(0.0, core_reserve) / cpu_cost)
        ceiling = max(0, min(memory_ceiling, cpu_ceiling))

    contiguous = False
    swap_rate = None
    compressor_rate = None
    swap_used_rate = None
    counters_reset = False
    previous_time = previous.get("sampled_at")
    previous_swapouts = previous.get("swapouts")
    previous_page_size = previous.get("page_size")
    previous_compressor = previous.get("compressor_bytes")
    previous_swap_used = previous.get("swap_used_bytes")
    previous_sample_valid = previous.get("sample_valid") is True
    if fresh and previous_sample_valid and same_machine and finite(previous_time):
        gap = sample_time - float(previous_time)
        contiguous = 0 < gap <= cfg["max_sample_gap_seconds"]
        if contiguous:
            if swapouts_known and page_size_known and count(previous_swapouts) and previous_page_size == page_size_raw:
                if swapouts_raw < previous_swapouts:
                    counters_reset = True
                else:
                    swap_rate = (swapouts_raw - previous_swapouts) * page_size_raw / gap
            elif swapouts_known and page_size_known:
                counters_reset = True
            if compressor_known and finite(previous_compressor):
                compressor_rate = max(0, compressor_raw - previous_compressor) / gap
            if swap_used_known and finite(previous_swap_used):
                swap_used_rate = max(0, swap_used_raw - previous_swap_used) / gap
    if counters_reset:
        vetoes.append("counter_reset")
    if contiguous:
        if swap_rate is not None and swap_rate > cfg["swapout_bytes_per_second"]:
            vetoes.append("swapout_growth")
        if compressor_rate is not None and compressor_rate > cfg["compressor_growth_bytes_per_second"]:
            vetoes.append("compressor_growth")
        if swap_used_rate is not None and swap_used_rate > cfg["swap_growth_bytes_per_second"]:
            vetoes.append("swap_usage_growth")

    disk_wait_bad = (disk_wait_raw is not None and disk_wait_known
                     and disk_wait_raw >= cfg["disk_wait_ratio_threshold"])
    board_latency_bad = (board_response_known
                         and board_response_raw >= cfg["board_response_seconds_threshold"])
    if disk_wait_bad:
        vetoes.append("disk_wait")
    if board_latency_bad:
        vetoes.append("board_latency")

    bad_signal = (warning_pressure or warning_load or memory_violation or disk_wait_bad
                  or board_latency_bad or "swapout_growth" in vetoes
                  or "compressor_growth" in vetoes or "swap_usage_growth" in vetoes)
    if ceiling is not None and current_value > ceiling:
        vetoes.append("capacity_ceiling")
        bad_signal = True

    def save_baseline(healthy_since=None, healthy_samples=0):
        state["sample_valid"] = True
        state["sampled_at"] = sample_time
        state["swapouts"] = swapouts_raw
        state["page_size"] = page_size_raw
        state["compressor_bytes"] = compressor_raw
        state["swap_used_bytes"] = swap_used_raw
        if healthy_since is not None:
            state["healthy_since"] = healthy_since
            state["healthy_samples"] = healthy_samples

    if bad_signal:
        target = min(current_value // 2, ceiling) if ceiling is not None else current_value // 2
        return result(target, "aimd_decrease", fit=ceiling, memory_headroom=memory_headroom,
                      cpu_headroom=cpu_headroom, swap_rate=swap_rate, ceiling=ceiling,
                      vetoes=vetoes)

    if not complete:
        target = min(current_value, running) if running_valid else 0
        if ceiling is not None:
            target = min(target, ceiling)
        return result(target, "close_unknown_starts", fit=ceiling, memory_headroom=memory_headroom,
                      cpu_headroom=cpu_headroom, swap_rate=swap_rate, ceiling=ceiling,
                      vetoes=vetoes)

    if counters_reset:
        save_baseline()
        return result(min(current_value, ceiling) if ceiling is not None else current_value,
                      "hold_counter_reset", fit=ceiling, memory_headroom=memory_headroom,
                      cpu_headroom=cpu_headroom, swap_rate=None, ceiling=ceiling, vetoes=vetoes)

    prior_healthy_since = previous.get("healthy_since")
    prior_healthy_samples = previous.get("healthy_samples")
    healthy_since = None
    healthy_samples = 0
    if contiguous:
        if finite(prior_healthy_since) and count(prior_healthy_samples):
            healthy_since = float(prior_healthy_since)
            healthy_samples = int(prior_healthy_samples) + 1
        elif swap_rate is not None:
            healthy_since = sample_time
            healthy_samples = 1

    target = current_value
    reason = "hold_capacity"
    candidate = current_value + 1
    pending = max(0, candidate - running) if running_valid else None
    next_cpu_ok = (pending is not None and load is not None and core_reserve is not None
                   and load + pending * cpu_cost <= core_reserve)
    next_memory_ok = (pending is not None and available is not None and reserve is not None
                      and available >= reserve + pending * memory_cost)
    current_pending = max(0, current_value - running) if running_valid else None
    current_cpu_ok = (current_pending is not None and load is not None and core_reserve is not None
                      and load + current_pending * cpu_cost <= core_reserve)
    current_memory_ok = (current_pending is not None and available is not None and reserve is not None
                         and available >= reserve + current_pending * memory_cost)
    current_has_pending = current_pending is not None and current_pending > 0
    if current_has_pending and (not current_cpu_ok or not current_memory_ok):
        if not current_cpu_ok:
            vetoes.append("start_cpu_capacity")
        if not current_memory_ok:
            vetoes.append("start_memory_capacity")
        target = min(current_value // 2, ceiling) if ceiling is not None else current_value // 2
        return result(target, "aimd_capacity_decrease", fit=ceiling, memory_headroom=memory_headroom,
                      cpu_headroom=cpu_headroom, swap_rate=swap_rate, ceiling=ceiling,
                      vetoes=vetoes)

    if not next_cpu_ok or not next_memory_ok:
        healthy_since = None
        healthy_samples = 0

    if ceiling is not None and current_value < ceiling:
        if (healthy_since is not None and healthy_samples >= 2
                and sample_time - healthy_since >= cfg["growth_hold_seconds"]):
            if next_cpu_ok and next_memory_ok and candidate <= ceiling:
                target = candidate
                reason = "persistent_headroom"
                healthy_since = None
                healthy_samples = 0
            else:
                if not next_cpu_ok:
                    vetoes.append("growth_cpu_capacity")
                if not next_memory_ok:
                    vetoes.append("growth_memory_capacity")
                reason = "growth_capacity_veto"
        else:
            reason = "await_healthy_window"
    elif ceiling is not None and current_value >= ceiling:
        reason = "at_ceiling"

    save_baseline(healthy_since, healthy_samples)
    pending_after = max(0, target - running) if running_valid else None
    start_allowed = (complete and not bad_signal and pending_after is not None and pending_after > 0
                     and load is not None and core_reserve is not None
                     and load + pending_after * cpu_cost <= core_reserve
                     and available is not None and reserve is not None
                     and available >= reserve + pending_after * memory_cost)
    return result(target, reason, fit=ceiling, memory_headroom=memory_headroom,
                  cpu_headroom=cpu_headroom, swap_rate=swap_rate, ceiling=ceiling,
                  vetoes=vetoes, start_allowed=start_allowed)



def simulate(path, cfg):
    fixture = json.loads(path.read_text())
    for scenario in fixture["scenarios"]:
        current = scenario["current"]
        state = scenario.get("state", {})
        for sample in scenario["samples"]:
            reading = {**fixture["readings"], "sampled_at": sample["time"], **sample["readings"]}
            state, result = decision(reading, state, cfg, current, sample["time"])
            print(json.dumps({"mode": "simulation", "scenario": scenario["name"],
                              "time": sample["time"], "readings": reading, "decision": result}, allow_nan=False))
            if result["target"] != sample["expected_target"]:
                raise ValueError(f"Unexpected target in {scenario['name']}")
            if "expected_reason" in sample and result["reason"] != sample["expected_reason"]:
                raise ValueError(f"Unexpected reason in {scenario['name']}: {result['reason']}")
            for field in ("start_allowed", "enforcement_required", "swapout_bytes_per_second",
                          "compressor_growth_bytes_per_second", "swap_growth_bytes_per_second"):
                if "expected_" + field in sample and result[field] != sample["expected_" + field]:
                    raise ValueError(f"Unexpected {field} in {scenario['name']}")
            if not set(sample.get("expected_vetoes", [])).issubset(result["vetoes"]):
                raise ValueError(f"Missing pressure veto in {scenario['name']}")
            current = result["target"]


def replay_log(path, cfg):
    checked = 0
    for line in path.read_text().splitlines():
        row = json.loads(line)
        reading = row.get("readings", {})
        load = reading.get("load1")
        cores = reading.get("cores")
        if not isinstance(load, (int, float)) or not isinstance(cores, (int, float)) or cores <= 0 or load < 2 * cores:
            continue
        current = row.get("current")
        if current is None:
            current = (row.get("decision") or {}).get("current")
        if current is None:
            raise ValueError("Captured emergency row has no admission limit")
        _, result = decision(reading, {}, cfg, current, row["time"])
        if result["target"] != 0 or (current > 0 and result["target"] >= current):
            raise ValueError("Captured emergency reading did not close admission")
        checked += 1
        print(json.dumps({"mode": "historical-replay", "time": row["time"],
                          "load1": load, "cores": cores, "decision": result}, allow_nan=False))
    if not checked:
        raise ValueError("No captured emergency readings found")
    print(json.dumps({"mode": "historical-replay-summary", "emergency_rows": checked, "passed": True}))


def _ensure_directory(path, *, create, private):
    uid = os.getuid()
    try:
        info = os.lstat(str(path))
    except FileNotFoundError:
        if not create:
            raise
        os.mkdir(str(path), 0o700 if private else 0o755)
        info = os.lstat(str(path))
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != uid or info.st_mode & 0o022
            or (private and info.st_mode & 0o077)):
        raise ValueError("Controller state directory is unsafe")


def _ensure_state_dir(*, create):
    home = Path.home()
    if not home.is_absolute() or os.path.realpath(str(home)) != str(home):
        raise ValueError("Home directory is not canonical")
    _ensure_directory(home / ".local", create=create, private=False)
    _ensure_directory(home / ".local" / "state", create=create, private=True)
    _ensure_directory(STATE_DIR, create=create, private=True)
    return STATE_DIR


def _read_private_json(path, *, allow_missing=False, max_bytes=1_000_000):
    path = Path(path)
    try:
        info = os.lstat(str(path))
    except FileNotFoundError:
        if allow_missing:
            return None
        raise
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise ValueError("Controller state file is unsafe")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags)
    with os.fdopen(fd, "rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Controller state file is too large")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Controller state file is malformed") from exc
    if not isinstance(value, dict):
        raise ValueError("Controller state file must contain a JSON object")
    return value


def _heavy_module():
    return board_resources._heavy_module()


def _agent_heavy_wait_pause_tick(helper, boot_id, agent_census, admission_active, *, critical_pressure=False):
    state = _read_private_json(AGENT_HEAVY_PAUSE_STATE, allow_missing=True)
    deps = helper.SupervisorDeps()
    try:
        new_state, summary = agent_heavy_wait_pause.tick(
            heavy_mod=helper,
            boot_id=boot_id,
            agent_census=agent_census,
            admission_active=admission_active,
            state=state,
            critical_pressure=critical_pressure,
        )
    except Exception as exc:
        cleared, resume_info = agent_heavy_wait_pause.resume_all(
            state,
            heavy_mod=helper,
            boot_id=boot_id,
            deps=deps,
            reason="tick-error",
        )
        atomic_json(AGENT_HEAVY_PAUSE_STATE, cleared)
        summary = {"action": "error-resume", "error": type(exc).__name__, "resume": resume_info}
        new_state = cleared
    else:
        atomic_json(AGENT_HEAVY_PAUSE_STATE, new_state)
    return summary


def _resume_agents_on_controller_start(helper):
    boot_id = helper.kernel_boot_identity()
    state = _read_private_json(AGENT_HEAVY_PAUSE_STATE, allow_missing=True)
    deps = helper.SupervisorDeps()
    cleared, resume_info = agent_heavy_wait_pause.resume_all(
        state,
        heavy_mod=helper,
        boot_id=boot_id,
        deps=deps,
        reason="controller-start",
    )
    atomic_json(AGENT_HEAVY_PAUSE_STATE, cleared)
    return resume_info


def _capacity_current(boot_id, now_wall):
    value = _read_private_json(CAPACITY, allow_missing=True, max_bytes=4096)
    if value is None:
        return 0
    if set(value) != {"heavy_slots", "updated_at", "boot_id"}:
        raise ValueError("Capacity contract fields are invalid")
    slots = value.get("heavy_slots")
    stamp = value.get("updated_at")
    reported_boot = value.get("boot_id")
    if type(slots) is not int or slots < 0:
        raise ValueError("Capacity contract slot count is invalid")
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(float(stamp)):
        raise ValueError("Capacity contract timestamp is invalid")
    if not isinstance(reported_boot, str) or not reported_boot:
        raise ValueError("Capacity contract boot identity is invalid")
    age = now_wall - float(stamp)
    if reported_boot != boot_id or age < 0 or age > CAPACITY_MAX_AGE_SECONDS:
        return 0
    return slots


def _capacity_state(boot_id):
    value = _read_private_json(CAPACITY_STATE, allow_missing=True)
    if value is None:
        return {}
    if value.get("schema") != 1 or value.get("boot_id") != boot_id:
        return {}
    slots = value.get("heavy_slots")
    if type(slots) is not int or slots < 0:
        return {}
    return value


def _adaptive_capacity_decision(helper, sample, census, compressor, previous, current, boot_id, now_mono):
    cores = sample.physical_cores
    physical = sample.physical_bytes
    if type(cores) is not int or cores <= 0 or type(physical) is not int or physical <= 0:
        raise ValueError("Host CPU or memory capacity is invalid")
    active = census.get("active")
    if type(active) is not int or active < 0:
        raise ValueError("Heavy active census is invalid")
    compressor_bytes = compressor.get("compressor_bytes")
    compressor_time = compressor.get("sampled_monotonic")
    if type(compressor_bytes) is not int or compressor_bytes < 0:
        raise ValueError("Compressor counter is invalid")
    if (isinstance(compressor_time, bool) or not isinstance(compressor_time, (int, float))
            or not math.isfinite(float(compressor_time))):
        raise ValueError("Compressor sample time is invalid")
    ceiling = min(cores, physical // HEAVY_SLOT_MEMORY_BYTES)
    host_reason = helper.admission_block_reason(
        sample,
        now=now_mono,
        active_count=0,
        task_already_active=False,
        slot_limit=max(1, ceiling),
    )
    state = {
        "schema": 1,
        "boot_id": boot_id,
        "heavy_slots": 0,
        "healthy_since_monotonic": None,
        "last_sample_monotonic": now_mono,
        "machine": [cores, physical],
        "compressor_bytes": compressor_bytes,
        "compressor_sampled_monotonic": float(compressor_time),
    }
    previous_machine = previous.get("machine")
    previous_compressor = previous.get("compressor_bytes")
    previous_compressor_time = previous.get("compressor_sampled_monotonic")
    compressor_growth = None
    compressor_baseline_reason = "compressor_baseline"
    if (previous_machine == [cores, physical]
            and type(previous_compressor) is int and previous_compressor >= 0
            and isinstance(previous_compressor_time, (int, float))
            and not isinstance(previous_compressor_time, bool)
            and math.isfinite(float(previous_compressor_time))):
        compressor_gap = float(compressor_time) - float(previous_compressor_time)
        if 0 < compressor_gap <= HEAVY_MAX_SAMPLE_GAP_SECONDS:
            compressor_growth = max(0, compressor_bytes - previous_compressor) / compressor_gap
            compressor_baseline_reason = None
        else:
            compressor_baseline_reason = "compressor_sample_gap"
    previous_growth_samples = previous.get("compressor_growth_samples", 0)
    if (previous.get("boot_id") != boot_id or compressor_growth is None
            or type(previous_growth_samples) is not int or previous_growth_samples < 0):
        previous_growth_samples = 0
    growth_samples = (min(3, previous_growth_samples + 1)
                      if compressor_growth is not None
                      and compressor_growth > HEAVY_COMPRESSOR_MAX_GROWTH_BYTES_PER_SECOND else 0)
    state["compressor_growth_samples"] = growth_samples
    detail = {
        "current": current,
        "active": active,
        "registry_active": census["registry_active"],
        "legacy_active": census["legacy_active"],
        "ceiling": ceiling,
        "reason": "hold_capacity",
        "host_veto": host_reason,
        "compressor_growth_bytes_per_second": compressor_growth,
        "compressor_veto": compressor_baseline_reason,
    }
    if ceiling == 0:
        detail.update(target=0, reason="machine_below_minimum_capacity")
        return state, detail
    if host_reason is not None:
        detail.update(target=0, reason=host_reason)
        return state, detail
    if growth_samples >= 3 and sample.free_percent <= helper.WARNING_FREE_PERCENT:
        target = min(current, active, ceiling)
        state["heavy_slots"] = target
        detail.update(target=target, reason="compressor_growth", compressor_veto="compressor_growth")
        return state, detail
    if compressor_growth is None:
        target = min(current, active, ceiling)
        detail.update(target=target, reason=compressor_baseline_reason or "compressor_baseline")
        state["heavy_slots"] = target
        return state, detail

    measured_rss = census.get("job_rss_bytes")
    if (not isinstance(measured_rss, list)
            or any(type(value) is not int or value <= 0 for value in measured_rss)):
        measured_rss = []
    memory_cost = (max(HEAVY_SLOT_MEMORY_FLOOR_BYTES,
                       max(measured_rss) * HEAVY_RSS_COST_MARGIN)
                   if measured_rss else None)
    previous_cost = previous.get("heavy_memory_cost_bytes")
    if (previous_machine == [cores, physical]
            and isinstance(previous_cost, (int, float)) and not isinstance(previous_cost, bool)
            and math.isfinite(float(previous_cost)) and previous_cost > 0):
        memory_cost = max(memory_cost or HEAVY_SLOT_MEMORY_FLOOR_BYTES,
                          HEAVY_SLOT_MEMORY_FLOOR_BYTES, float(previous_cost))
    if memory_cost is None:
        memory_cost = HEAVY_SLOT_MEMORY_FLOOR_BYTES
    state["heavy_memory_cost_bytes"] = memory_cost
    detail["memory_cost_bytes"] = memory_cost
    if (active > 0 and not measured_rss) or census.get("legacy_active", 0) > 0:
        target = min(current, active, ceiling)
        detail.update(target=target, reason="await_measured_job_rss")
        state["heavy_slots"] = target
        return state, detail

    busy_cores = sample.cpu_busy_pct / 100 * cores
    cpu_available = max(0.0, cores * (1 - HEAVY_CPU_RESERVE_FRACTION) - busy_cores)
    memory_reserve = max(HEAVY_MEMORY_RESERVE_BYTES, physical * HEAVY_MEMORY_RESERVE_FRACTION)
    memory_available = max(0, sample.headroom_bytes - memory_reserve)
    fit = min(
        ceiling,
        active + math.floor(memory_available / memory_cost),
        active + math.floor(cpu_available / HEAVY_SLOT_CPU_CORES),
    )
    detail["fit"] = fit
    current = min(current, ceiling)
    current_pending = max(0, current - active)
    current_fits = (current_pending * memory_cost <= memory_available
                    and current_pending * HEAVY_SLOT_CPU_CORES <= cpu_available)
    if current > fit or not current_fits:
        target = min(current // 2, fit)
        detail.update(target=target, reason="capacity_decrease")
        state["heavy_slots"] = target
        return state, detail

    previous_boot = previous.get("boot_id")
    last_sample = previous.get("last_sample_monotonic")
    healthy_since = previous.get("healthy_since_monotonic")
    contiguous = (
        previous_boot == boot_id
        and isinstance(last_sample, (int, float)) and not isinstance(last_sample, bool)
        and math.isfinite(float(last_sample))
        and 0 < now_mono - float(last_sample) <= HEAVY_MAX_SAMPLE_GAP_SECONDS
    )
    if (not contiguous or not isinstance(healthy_since, (int, float))
            or isinstance(healthy_since, bool) or not math.isfinite(float(healthy_since))):
        healthy_since = now_mono
    candidate = current + 1
    pending = max(0, candidate - active)
    candidate_fits = (candidate <= ceiling
                      and pending * memory_cost <= memory_available
                      and pending * HEAVY_SLOT_CPU_CORES <= cpu_available)
    target = current
    if candidate <= ceiling and candidate_fits:
        if now_mono - float(healthy_since) >= HEAVY_GROWTH_HOLD_SECONDS:
            target = candidate
            healthy_since = now_mono
            detail["reason"] = "healthy_growth"
        else:
            detail["reason"] = "await_healthy_window"
    elif candidate <= ceiling:
        healthy_since = None
        detail["reason"] = "await_capacity_headroom"
    else:
        healthy_since = None
        detail["reason"] = "at_ceiling"
    state.update(heavy_slots=target, healthy_since_monotonic=healthy_since)
    detail["target"] = target
    return state, detail



def _capacity_decision(helper, sample, census, compressor, previous, current, boot_id, now_mono):
    state, detail = _adaptive_capacity_decision(
        helper, sample, census, compressor, previous, current, boot_id, now_mono)
    floor = min(2, detail["ceiling"])
    critical = _critical_pressure(helper, sample)
    valid = helper._sample_invalid_reason(sample, now_mono) is None
    proposed = detail["target"]
    target = (0 if critical else max(floor, proposed) if valid
              else min(current, floor, detail["ceiling"]))
    detail.update(floor=floor, critical=critical, adaptive_target=proposed, target=target)
    if critical:
        detail["reason"] = "critical_pressure"
        state["healthy_since_monotonic"] = None
    elif not valid:
        detail["reason"] = "hold_missing_or_stale_reading"
        state["healthy_since_monotonic"] = None
    elif proposed < floor:
        detail["adaptive_reason"] = detail["reason"]
        detail["reason"] = "baseline_floor" if current < floor else "baseline_floor_hold"
    state["heavy_slots"] = target
    return state, detail


def _sample_payload(sample):
    return {
        "pressure_level": sample.pressure_level,
        "cpu_busy_pct": sample.cpu_busy_pct,
        "memory_used_pct": sample.memory_used_pct,
        "headroom_bytes": sample.headroom_bytes,
        "physical_bytes": sample.physical_bytes,
        "load_per_core": sample.load_per_core,
        "captured_monotonic": sample.captured_monotonic,
        "free_percent": sample.free_percent,
        "swap_growth_bytes_per_second": sample.swap_growth_bytes_per_second,
        "swapout_bytes_per_second": sample.swapout_bytes_per_second,
        "physical_cores": sample.physical_cores,
    }


_last_cpu_busy = None


def _cpu_busy_for_board_veto(helper, sample, cfg, now_mono):
    global _last_cpu_busy
    if helper._finite_nonnegative(sample.cpu_busy_pct):
        _last_cpu_busy = (float(sample.cpu_busy_pct), float(sample.captured_monotonic))
        return float(sample.cpu_busy_pct), None
    if _last_cpu_busy is not None:
        pct, captured = _last_cpu_busy
        age = now_mono - captured
        if helper._finite_nonnegative(pct) and 0 <= age <= cfg["max_sample_age_seconds"]:
            return float(pct), None
    return None, "cpu_busy_pct missing"


def _board_active_ids(admission):
    active = admission.get("active")
    if not isinstance(active, list):
        raise ValueError("Board active task census is unavailable")
    ids = []
    for row in active:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ValueError("Board active task identity is invalid")
        ids.append(row["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("Board active task identities are duplicated")
    return sorted(ids)


def _board_control_tick(helper, sample, heavy_decision, cfg, boot_id, agent_census=None):
    admission_started = time.monotonic()
    admission = board_resources.board_admission_snapshot()
    admission_elapsed = time.monotonic() - admission_started
    current = admission.get("limit")
    if type(current) is not int or current < 0:
        raise ValueError("Board admission limit is invalid")
    active_ids = _board_active_ids(admission)
    active = len(active_ids)
    now_mono = helper.monotonic()
    sample_age = None
    sample_is_fresh = False
    host_veto = "host_sample_unavailable"
    cpu_busy_note = None
    cpu_for_veto = None
    if sample is not None:
        sample_age = now_mono - sample.captured_monotonic
        sample_is_fresh = (0 <= sample_age <= getattr(helper, "SAMPLE_MAX_AGE", 4.5))
        cpu_for_veto, cpu_busy_note = _cpu_busy_for_board_veto(helper, sample, cfg, now_mono)
        if cpu_for_veto is None:
            cpu_for_veto = 0.0
        veto_sample = sample if cpu_for_veto == sample.cpu_busy_pct else dataclasses.replace(
            sample, cpu_busy_pct=cpu_for_veto)
        host_veto = helper.admission_block_reason(
            veto_sample,
            now=now_mono,
            active_count=0,
            task_already_active=False,
            slot_limit=1,
        )
    compressor_rate = None
    compressor_veto = "compressor_baseline"
    if isinstance(heavy_decision, dict):
        compressor_rate = heavy_decision.get("compressor_growth_bytes_per_second")
        compressor_veto = heavy_decision.get("compressor_veto")
    if (compressor_rate is not None
            and isinstance(compressor_rate, (int, float))
            and not isinstance(compressor_rate, bool)
            and compressor_rate > HEAVY_COMPRESSOR_MAX_GROWTH_BYTES_PER_SECOND):
        host_veto = "compressor_growth"
    elif compressor_veto is not None:
        host_veto = host_veto or str(compressor_veto)

    critical_pressure = bool(sample_is_fresh and sample is not None and (
        _critical_pressure(helper, sample)
        or (cpu_busy_note is None and _critical_pressure(helper, veto_sample))))
    if agent_census is None and sample_is_fresh and sample is not None and not critical_pressure:
        try:
            agent_census = board_resources.board_agent_rss_census(admission)
        except (OSError, RuntimeError, ValueError, TypeError):
            agent_census = None
    agent_memory_budget, agent_rss_p90, agent_memory_source = _board_agent_memory_budget_bytes(
        agent_census, cfg, active=active)

    memory_reserve = None
    cpu_headroom = None
    memory_headroom = None
    ceiling = None
    candidate_fits = False
    if sample is not None:
        cores = sample.physical_cores
        physical = sample.physical_bytes
        if type(cores) is int and cores > 0 and type(physical) is int and physical > 0:
            memory_reserve = max(cfg["memory_reserve_bytes"], physical * cfg["memory_reserve_fraction"])
            ceiling = max(0, min(math.floor(max(0, physical - memory_reserve) / agent_memory_budget),
                                 math.floor(cores * (1 - cfg["cpu_reserve_fraction"]) / BOARD_AGENT_CPU_CORES)))
            memory_headroom = max(0, sample.headroom_bytes - memory_reserve)
            cpu_headroom = max(0.0, cores * (1 - cfg["cpu_reserve_fraction"])
                               - cpu_for_veto / 100 * cores)
            if host_veto is None:
                candidate_fits = (memory_headroom >= agent_memory_budget
                                  and cpu_headroom >= BOARD_AGENT_CPU_CORES)

    previous_error = None
    try:
        previous = _read_private_json(STATE, allow_missing=True)
    except (OSError, ValueError, TypeError) as exc:
        previous = None
        previous_error = type(exc).__name__ + ": " + str(exc).splitlines()[0][:160]
    previous = previous or {}
    previous_ids = previous.get("active_ids") if previous.get("schema") == 2 else None
    previous_ids_valid = isinstance(previous_ids, list) and all(isinstance(item, str) for item in previous_ids)
    previous_sample = previous.get("last_sample_monotonic")
    previous_healthy_since = previous.get("healthy_since_monotonic")
    contiguous = bool(sample is not None
                      and previous.get("schema") == 2
                      and previous.get("boot_id") == boot_id
                      and previous.get("machine") == [sample.physical_cores, sample.physical_bytes])
    contiguous = bool(contiguous and previous_ids_valid
                      and isinstance(previous_sample, (int, float)) and not isinstance(previous_sample, bool)
                      and math.isfinite(float(previous_sample))
                      and 0 < now_mono - float(previous_sample) <= HEAVY_MAX_SAMPLE_GAP_SECONDS)
    removed_ids = set(previous_ids or []) - set(active_ids)
    task_finished = bool(removed_ids)
    prior_warning_episode = (previous.get("warning_episode") is True
                             and previous.get("schema") == 2
                             and previous.get("boot_id") == boot_id)
    warning_pressure = bool(sample_is_fresh and sample is not None and not critical_pressure and (
        sample.pressure_level == 2
        or (helper._finite_nonnegative(sample.cpu_busy_pct) and sample.cpu_busy_pct >= helper.WARNING_CPU_PCT)
        or (compressor_rate is not None and compressor_rate > HEAVY_COMPRESSOR_MAX_GROWTH_BYTES_PER_SECOND)
        or host_veto in ("swap-growth", "memory-headroom", "memory-pressure-warning-low-free")
    ))
    safe = (sample is not None and host_veto is None and candidate_fits
            and previous_error is None
            and admission_elapsed < cfg["board_response_seconds_threshold"])
    healthy_since = None
    if safe and not task_finished:
        if (contiguous and isinstance(previous_healthy_since, (int, float))
                and not isinstance(previous_healthy_since, bool)
                and math.isfinite(float(previous_healthy_since))):
            healthy_since = float(previous_healthy_since)
        else:
            healthy_since = now_mono

    valid_noncritical = bool(sample_is_fresh and sample is not None
                             and helper._sample_invalid_reason(sample, now_mono) is None
                             and not critical_pressure and ceiling is not None)
    floor = min(ceiling, max(6, active + 1)) if ceiling is not None else None
    floor_ready = (valid_noncritical
                   and admission_elapsed < cfg["board_response_seconds_threshold"])
    floor_raise_fits = False
    growth_host_vetoes = (
        "compressor_growth", "swap-growth", "memory-headroom", "memory-pressure-warning-low-free",
    )
    if (floor_ready and floor is not None
            and memory_headroom is not None and cpu_headroom is not None
            and host_veto not in growth_host_vetoes):
        pending_floor = max(1, floor - active)
        floor_raise_fits = (memory_headroom >= pending_floor * agent_memory_budget
                            and cpu_headroom >= pending_floor * BOARD_AGENT_CPU_CORES)
    target = current
    reason = "hold_capacity"
    warning_episode = prior_warning_episode
    if critical_pressure:
        target = 0
        reason = "critical_pressure_or_load"
        healthy_since = None
        warning_episode = True
    elif floor_ready and current < floor and floor_raise_fits:
        target = floor
        reason = "board_baseline_floor"
        healthy_since = None
        warning_episode = warning_pressure
    elif warning_pressure:
        warning_cut = min(current if prior_warning_episode else current // 2, active)
        warning_floor = floor if (floor_ready and floor_raise_fits) else active
        target = max(warning_floor if floor_ready else 0, warning_cut)
        reason = "warning_pressure_hold" if prior_warning_episode else "warning_pressure_cut"
        healthy_since = None
        warning_episode = True
    elif task_finished or not safe:
        target = min(current, max(active, floor if (floor_ready and floor_raise_fits) else 0))
        reason = ("task_finished_reset_window" if task_finished else
                  host_veto or "one_agent_capacity_unavailable")
        healthy_since = None
    else:
        warning_episode = False
        candidate = current + 1
        pending = max(1, candidate - active)
        growth_fits = (ceiling is not None and candidate <= ceiling
                       and memory_headroom is not None and cpu_headroom is not None
                       and memory_headroom >= pending * agent_memory_budget
                       and cpu_headroom >= pending * BOARD_AGENT_CPU_CORES)
        if not growth_fits:
            reason = "await_capacity_headroom"
            healthy_since = None
        elif healthy_since is not None and now_mono - healthy_since >= BOARD_GROWTH_HOLD_SECONDS:
            target = candidate
            reason = "healthy_growth_one"
            healthy_since = None
        else:
            reason = "await_healthy_window"

    catchup_limit = min(active, floor) if floor_ready and host_veto is None else None
    if catchup_limit is not None and target < catchup_limit:
        target = catchup_limit
        reason = "active_catchup"
        healthy_since = None
    if ceiling is not None and target > ceiling:
        target = ceiling
        reason = "hardware_ceiling_cut"
        healthy_since = None
    floor_raise = bool(floor_ready and current < floor and target == floor)
    if (target > current and not floor_raise and target != current + 1
            and not (catchup_limit is not None and target <= catchup_limit)):
        target = max(current, catchup_limit) if catchup_limit is not None else current
        reason = "growth_step_rejected"
        healthy_since = None
    catchup_raise = bool(catchup_limit is not None and current < target <= catchup_limit)
    result = {
        "current": current,
        "active": active,
        "target": target,
        "reason": reason,
        "floor": floor,
        "floor_ready": floor_ready,
        "floor_raise_fits": floor_raise_fits,
        "host_veto": host_veto,
        "sample_age_seconds": sample_age,
        "board_response_seconds": admission_elapsed,
        "healthy_since_monotonic": healthy_since,
        "memory_reserve_bytes": memory_reserve,
        "agent_memory_budget_bytes": agent_memory_budget,
        "agent_memory_budget_source": agent_memory_source,
        "agent_rss_p90_bytes": agent_rss_p90,
        "memory_headroom_bytes": memory_headroom,
        "ceiling": ceiling,
        "agent_cpu_budget_cores": BOARD_AGENT_CPU_CORES,
        "cpu_headroom_cores": cpu_headroom,
        "cpu_busy_note": cpu_busy_note,
        "active_ids": active_ids,
        "removed_ids": sorted(removed_ids),
        "growth_hold_seconds": BOARD_GROWTH_HOLD_SECONDS,
        "warning_episode": warning_episode,
        "start_allowed": bool((floor_raise or safe or catchup_raise) and target > current),
    }
    state = {
        "schema": 2,
        "boot_id": boot_id,
        "machine": [sample.physical_cores, sample.physical_bytes] if sample is not None else None,
        "active_ids": active_ids,
        "last_sample_monotonic": now_mono,
        "healthy_since_monotonic": healthy_since,
        "warning_episode": warning_episode,
    }
    if target != current:
        recheck_started = time.monotonic()
        latest = board_resources.board_admission_snapshot()
        recheck_elapsed = time.monotonic() - recheck_started
        latest_current = latest.get("limit")
        latest_ids = _board_active_ids(latest)
        if latest_current != current:
            result.update(target=current, reason="board_limit_changed_during_sample", start_allowed=False)
            state["healthy_since_monotonic"] = None
        elif target > current:
            latest_age = helper.monotonic() - sample.captured_monotonic if sample is not None else math.inf
            if (latest_ids != active_ids or not (floor_raise_fits if floor_raise else catchup_raise or safe)
                    or latest_age < 0 or latest_age > getattr(helper, "SAMPLE_MAX_AGE", 4.5)
                    or admission_elapsed + recheck_elapsed >= cfg["board_response_seconds_threshold"]):
                result.update(target=current, reason="growth_sample_expired", start_allowed=False)
                state["healthy_since_monotonic"] = None
            elif not floor_raise and not catchup_raise and target != current + 1:
                result.update(target=current, reason="growth_step_rejected", start_allowed=False)
                state["healthy_since_monotonic"] = None
        else:
            target = min(target, current)
            result["target"] = target
        if result["target"] != current:
            command([str(BOARD), "set", "board.agents", str(result["target"])])
            atomic_json(STATE, state)
            verified = board_resources.board_admission_snapshot()
            if verified.get("limit") != result["target"]:
                raise ValueError("Board admission readback differs from the requested value")
    atomic_json(STATE, state)
    return {"control": "enabled", "current": current, "decision": result}


def controller_status():
    try:
        _ensure_state_dir(create=False)
        value = _read_private_json(STATUS, allow_missing=True)
        if value is None:
            return {"schema": 1, "status": "not_started"}
        capacity = _read_private_json(CAPACITY, allow_missing=True, max_bytes=4096)
        value["capacity"] = capacity
        return value
    except (OSError, ValueError, TypeError) as exc:
        return {"schema": 1, "status": "unavailable", "error": str(exc).splitlines()[0][:180]}


_cpu_history = []


def _smoothed_cpu_sample(helper, sample):
    if not helper._finite_nonnegative(sample.cpu_busy_pct):
        return sample
    _cpu_history.append(sample.cpu_busy_pct)
    del _cpu_history[:-CPU_SMOOTHING_SAMPLES]
    return dataclasses.replace(sample, cpu_busy_pct=sum(_cpu_history) / len(_cpu_history))


def _critical_pressure(helper, sample):
    return helper.critical_pressure(sample) or (
        helper._finite_nonnegative(sample.cpu_busy_pct) and sample.cpu_busy_pct >= helper.MAX_CPU_PCT)


_last_restart_tick = 0.0


def _board_restart_tick():
    global _last_restart_tick
    now = time.monotonic()
    if now - _last_restart_tick < board_restart.MIN_INTERVAL_SECONDS:
        return {"action": "not_due"}
    _last_restart_tick = now
    return board_restart.tick()


_orphan_simulators_seen = set()


def _reap_orphan_simulators(helper):
    global _orphan_simulators_seen
    orphans = {device["udid"] for device in helper.orphaned_ci_simulators()}
    survivors = sorted(orphans & _orphan_simulators_seen)
    _orphan_simulators_seen = orphans
    return helper.reap_orphaned_ci_simulators(survivors) if survivors else []


def controller_tick(*, board_control=True, cfg=None):
    _ensure_state_dir(create=True)
    helper = _heavy_module()
    entry = {"schema": 1, "mode": "controller", "board_control": bool(board_control),
             "runtime": str(SCRIPT_DIR)}
    try:
        reaped = helper.reap_dead_jobs()
        if reaped:
            entry["dead_jobs_reaped"] = reaped
    except Exception as exc:
        entry["reap_error"] = type(exc).__name__ + ": " + (str(exc).splitlines() or [""])[0][:180]
    try:
        shut_down = _reap_orphan_simulators(helper)
        if shut_down:
            entry["orphan_simulators_shutdown"] = shut_down
    except Exception as exc:
        entry["simulator_error"] = type(exc).__name__ + ": " + (str(exc).splitlines() or [""])[0][:180]
    boot_id = None
    sample = None
    census = None
    compressor = None
    heavy_decision = None
    capacity_state = {"schema": 1, "heavy_slots": 0, "healthy_since_monotonic": None}
    try:
        boot_id = helper.kernel_boot_identity()
        if not isinstance(boot_id, str) or not re.fullmatch(r"[1-9][0-9]*", boot_id):
            raise ValueError("Kernel boot identity is invalid")
        sample = _smoothed_cpu_sample(helper, helper.sample_with_emergency())
        compressor = board_resources.compressor_snapshot()
        census = board_resources.active_heavy_census()
        entry["active_count"] = census["active"]
        entry["census"] = census
        if census.get("boot_id") != boot_id:
            raise ValueError("Heavy census boot identity changed during sampling")
        now_wall = time.time()
        now_mono = helper.monotonic()
        current = _capacity_current(boot_id, now_wall)
        previous = _capacity_state(boot_id)
        previous["boot_id"] = boot_id if previous else None
        capacity_state, heavy_decision = _capacity_decision(
            helper, sample, census, compressor, previous, current, boot_id, now_mono)
        payload = {"heavy_slots": heavy_decision["target"], "updated_at": now_wall, "boot_id": boot_id}
        entry.update(capacity=payload, heavy_decision=heavy_decision, host=_sample_payload(sample),
                     compressor=compressor, census=census, active_count=census["active"])
    except Exception as exc:
        entry["heavy_error"] = type(exc).__name__ + ": " + str(exc).splitlines()[0][:180]
        partial = getattr(exc, "partial_sample", None)
        if sample is None and isinstance(partial, helper.Sample):
            sample = partial
        if sample is not None:
            entry["host"] = _sample_payload(sample)
        try:
            if boot_id is None:
                boot_id = helper.kernel_boot_identity()
            if not isinstance(boot_id, str) or not re.fullmatch(r"[1-9][0-9]*", boot_id):
                raise ValueError("Kernel boot identity is invalid")
            now_wall = time.time()
            now_mono = helper.monotonic()
            critical = sample is not None and _critical_pressure(helper, sample)
            prior_capacity = _capacity_current(boot_id, now_wall)
            sample_usable = sample is not None and helper._sample_invalid_reason(sample, now_mono) is None
            fallback_slots = 0 if critical else 2 if sample_usable else min(prior_capacity, 2)
            capacity_state = {"schema": 1, "boot_id": boot_id, "heavy_slots": fallback_slots,
                              "healthy_since_monotonic": None, "last_sample_monotonic": now_mono}
            payload = {"heavy_slots": fallback_slots, "updated_at": now_wall, "boot_id": boot_id}
            entry["capacity"] = payload
            entry["active_count"] = census["active"] if census is not None else None
        except Exception as boot_error:
            entry["capacity_error"] = type(boot_error).__name__ + ": " + str(boot_error).splitlines()[0][:180]
            payload = None
    if payload is not None:
        atomic_json(CAPACITY, payload)
        atomic_json(CAPACITY_STATE, capacity_state)
        if sample is not None and _critical_pressure(helper, sample):
            try:
                entry["critical_curtailment"] = {"requested": helper.request_critical_pauses()}
            except Exception as exc:
                entry["critical_curtailment_error"] = type(exc).__name__ + ": " + str(exc).splitlines()[0][:180]

    agent_census = None
    admission_active = []

    if board_control:
        try:
            if cfg is None:
                raise ValueError("Board policy configuration is unavailable")
            if sample is not None and not _critical_pressure(helper, sample):
                try:
                    admission = board_resources.board_admission_snapshot()
                    admission_active = admission.get("active") or []
                    agent_census = board_resources.board_agent_rss_census(admission)
                except (OSError, RuntimeError, ValueError, TypeError):
                    agent_census = None
                    admission_active = []
            if agent_census is not None:
                entry["board_agent_census"] = agent_census
            entry["board"] = _board_control_tick(
                helper, sample, heavy_decision, cfg, boot_id, agent_census=agent_census,
            )
        except Exception as exc:
            entry["board_error"] = type(exc).__name__ + ": " + str(exc).splitlines()[0][:180]
    else:
        try:
            admission = board_resources.board_admission_snapshot()
            entry["board"] = {
                "control": "disabled",
                "limit": admission["limit"],
                "active": len(admission["active"]),
                "waiting": len(admission["waiting"]),
                "pane_census": "skipped",
                "growth": "disabled_by_flag",
            }
        except Exception as exc:
            entry["board_error"] = type(exc).__name__ + ": " + str(exc).splitlines()[0][:180]

    pause_admission = list(admission_active)
    critical_for_pause = bool(sample is not None and _critical_pressure(helper, sample))
    if board_control and cfg is not None and cfg["agent_restart"]:
        try:
            entry["board_restart"] = _board_restart_tick()
        except Exception as exc:
            entry["board_restart_error"] = type(exc).__name__ + ": " + str(exc).splitlines()[0][:180]
    if boot_id is not None and not (cfg is not None and cfg["agent_heavy_wait_pause"]):
        entry["agent_heavy_wait_pause"] = {"action": "disabled"}
    elif boot_id is not None:
        try:
            admission = board_resources.board_admission_snapshot()
            pause_admission = admission.get("active") or []
            try:
                pause_census = board_resources.board_agent_rss_census(admission)
            except (OSError, RuntimeError, ValueError, TypeError):
                pause_census = None
            entry["agent_heavy_wait_pause"] = _agent_heavy_wait_pause_tick(
                helper,
                boot_id,
                pause_census,
                pause_admission,
                critical_pressure=critical_for_pause,
            )
        except Exception as exc:
            try:
                resume_info = _resume_agents_on_controller_start(helper)
            except Exception as resume_exc:
                resume_info = {"error": type(resume_exc).__name__}
            entry["agent_heavy_wait_pause"] = {
                "action": "fatal-resume",
                "error": type(exc).__name__,
                "resume": resume_info,
            }

    entry["updated_at"] = time.time()
    append_log(entry)
    atomic_json(STATUS, entry)
    return entry


def append_log(entry):
    _ensure_state_dir(create=True)
    try:
        info = os.lstat(str(LOG))
    except FileNotFoundError:
        info = None
    if info is not None and (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                             or info.st_mode & 0o077):
        raise ValueError("Controller log is unsafe")
    if info is not None and info.st_size > 10 * 1024 * 1024:
        LOG.replace(LOG.with_suffix(".previous.jsonl"))
    flags = os.O_CREAT | os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(LOG), flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Controller log is unsafe")
        view = memoryview((json.dumps(entry, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8"))
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("Controller log write made no progress")
            view = view[written:]
    finally:
        os.close(fd)


@contextmanager
def controller_lock():
    _ensure_state_dir(create=True)
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(LOCK), flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Controller lock is unsafe")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def run_controller(*, once=False, board_control=True, cfg=None):
    with controller_lock() as acquired:
        if not acquired:
            print(json.dumps({"schema": 1, "status": "already_running", "lock": str(LOCK)}))
            return 0
        helper = _heavy_module()
        try:
            start_resume = _resume_agents_on_controller_start(helper)
            print(json.dumps({"schema": 1, "status": "controller_start",
                              "agent_heavy_wait_resume": start_resume},
                             allow_nan=False, separators=(",", ":")), flush=True)
        except Exception as exc:
            print(type(exc).__name__ + ": " + str(exc).splitlines()[0][:240], file=sys.stderr, flush=True)
        while True:
            started = time.monotonic()
            try:
                entry = controller_tick(board_control=board_control, cfg=cfg)
                print(json.dumps(entry, allow_nan=False, separators=(",", ":")), flush=True)
            except Exception as exc:
                print(type(exc).__name__ + ": " + str(exc).splitlines()[0][:240], file=sys.stderr, flush=True)
            if once:
                return 0
            time.sleep(max(0.0, CONTROLLER_INTERVAL_SECONDS - (time.monotonic() - started)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "once", "status", "simulate", "replay-log"])
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--fixture", type=Path, help="Simulation JSON or captured JSONL log")
    parser.add_argument("--no-board-control", action="store_true",
                        help="Disable board limit changes while continuing host capacity publication")
    args = parser.parse_args(argv)
    if args.no_board_control and args.action not in ("run", "once"):
        parser.error("--no-board-control applies only to run and once")
    if args.action == "status":
        print(json.dumps(controller_status(), allow_nan=False, separators=(",", ":")))
        return 0
    if args.action in ("run", "once"):
        try:
            cfg = config(args.config)
        except (OSError, ValueError, TypeError) as exc:
            cfg = None
            if not args.no_board_control:
                print("Board control unavailable: " + str(exc).splitlines()[0][:180], file=sys.stderr)
        return run_controller(once=args.action == "once", board_control=not args.no_board_control, cfg=cfg)
    cfg = config(args.config)
    if args.fixture is None:
        parser.error(args.action + " requires --fixture")
    if args.action == "simulate":
        simulate(args.fixture, cfg)
    else:
        replay_log(args.fixture, cfg)
    return 0



if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, OverflowError, RuntimeError, subprocess.SubprocessError) as error:
        print(type(error).__name__ + ": " + str(error).splitlines()[0][:240], file=sys.stderr)
        sys.exit(1)
