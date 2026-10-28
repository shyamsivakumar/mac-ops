#!/usr/bin/env python3
"""Explore bounded capacity inputs against the real decision function."""
import argparse
import ast
import itertools
import dataclasses
import heavy
import json
from types import SimpleNamespace
from pathlib import Path
import runpy

GIB = 1024 ** 3
ROOT = Path(__file__).resolve().parent


def base_reading(now=1000):
    return {"cores": 14, "total_bytes": 48 * GIB, "available_bytes": 32 * GIB,
            "free_percent": 66, "pressure": 1, "load1": 4, "load5": 4,
            "running": 2, "agents": [{"rss_bytes": GIB, "cpu_cores": 0.2}] * 2,
            "sampled_at": now, "sample_duration_seconds": 0.1, "complete": True,
            "errors": [], "swapouts": 100, "page_size": 16384,
            "compressor_bytes": GIB, "swap_used_bytes": 0,
            "board_response_seconds": 0.01, "disk_wait_ratio": 0}


def explore(decision, cfg):
    checked = 0
    for current, cores, memory, load, pressure in itertools.product(
            range(17), (2, 14, 32), (12, 48, 128), (0, 0.5, 0.8, 1.5, 9, 26), (1, 2, 4)):
        reading = {**base_reading(), "cores": cores, "total_bytes": memory * GIB,
                   "available_bytes": memory * GIB * 0.65, "load1": load * cores,
                   "load5": load * cores, "pressure": pressure}
        _, result = decision(reading, {}, cfg, current, 1000)
        assert type(result["target"]) is int and result["target"] >= 0
        assert result["target"] <= current + 1
        if pressure == 4 or load >= cfg["warning_load_fraction"]:
            assert result["target"] <= current, (reading, result)
        if result["ceiling"] is not None:
            assert result["target"] <= result["ceiling"]
        checked += 1
    for field in base_reading():
        for invalid in (None, "unknown", True, float("nan")):
            reading = base_reading()
            reading[field] = invalid
            try:
                _, result = decision(reading, {}, cfg, 8, 1000)
            except (TypeError, ValueError, KeyError):
                continue
            assert result["target"] <= 8, (field, invalid, result)
            checked += 1
    previous = {}
    current = 2
    grew = 0
    for now in range(1000, 1401, 5):
        previous, result = decision(base_reading(now), previous, cfg, current, now)
        assert result["target"] <= current + 1
        grew += result["target"] > current
        current = result["target"]
        checked += 1
    assert grew > 0, "Healthy sequence never grew"
    reading = base_reading(1005)
    state, _ = decision(base_reading(), {}, cfg, 4, 1000)
    for field, delta in (("compressor_bytes", 10 * GIB), ("swap_used_bytes", GIB), ("swapouts", 1000000)):
        changed = {**reading, field: reading[field] + delta}
        _, result = decision(changed, state, cfg, 4, 1005)
        assert result["target"] <= 4
        assert any("growth" in veto for veto in result["vetoes"]), (field, result)
        checked += 1
    return {"bounded_cases": checked, "healthy_increases": grew, "passed": True}


def explore_heavy(decide):
    checked = 0
    census = {"active": 2, "registry_active": 2, "legacy_active": 0, "job_rss_bytes": [GIB, GIB]}
    for current, cores, memory, load, pressure, cpu in itertools.product(
            range(9), (2, 14, 32), (12, 48, 128), (0, 0.5, 1, 9, 26), (1, 2, 4), (20, 95)):
        sample = heavy.Sample(pressure_level=pressure, cpu_busy_pct=cpu, memory_used_pct=30,
                              headroom_bytes=int(memory * GIB * 0.7), physical_bytes=memory * GIB,
                              load_per_core=load, captured_monotonic=1000, free_percent=70,
                              swap_growth_bytes_per_second=0, swapout_bytes_per_second=0,
                              physical_cores=cores)
        previous = {"machine": [cores, memory * GIB], "compressor_bytes": GIB,
                    "compressor_sampled_monotonic": 995, "boot_id": "100",
                    "last_sample_monotonic": 995, "healthy_since_monotonic": 900}
        compressor = {"compressor_bytes": GIB, "sampled_monotonic": 1000}
        _, result = decide(heavy, sample, census, compressor, previous, current, "100", 1000)
        assert 0 <= result["target"] <= max(min(2, cores, memory // 6), current + 1)
        assert result["target"] <= min(cores, memory // 6)
        if pressure == 4 or load >= 1.5:
            assert result["target"] == 0, (sample, result)
        elif load >= 1 or cpu >= 95:
            assert result["target"] <= max(current, 2), (sample, result)
        checked += 1
    healthy = dataclasses.replace(sample, physical_cores=14, physical_bytes=48*GIB,
                                   headroom_bytes=40*GIB, pressure_level=1,
                                   cpu_busy_pct=20, load_per_core=0.2)
    for field in ("free_percent", "swap_growth_bytes_per_second", "swapout_bytes_per_second",
                  "physical_cores", "cpu_busy_pct", "physical_bytes", "headroom_bytes"):
        bad = dataclasses.replace(healthy, **{field: None})
        try:
            _, result = decide(heavy, bad, census, compressor, {}, 4, "100", 1000)
        except (TypeError, ValueError):
            checked += 1
            continue
        assert result["target"] <= 4, (field, result)
        checked += 1
    previous = {}
    current = 0
    grew = 0
    for now in range(1000, 1401, 5):
        sample = dataclasses.replace(healthy, captured_monotonic=now)
        compressor = {"compressor_bytes": GIB, "sampled_monotonic": now}
        previous, result = decide(heavy, sample, census, compressor, previous, current, "100", now)
        assert result["target"] <= max(2, current + 1)
        grew += result["target"] > current
        current = result["target"]
        checked += 1
    assert grew >= 3, "Actual heavy policy never grew above two"
    return {"active_heavy_cases": checked, "active_heavy_increases": grew}


def explore_local_board(module, cfg):
    tick = module["_board_control_tick"]
    namespace = tick.__globals__
    saved = {name: namespace[name] for name in ("board_resources", "command", "_read_private_json", "atomic_json")}
    state = {}
    board = {"limit": 1, "active": [{"id": "fixture/1", "stage": "working"}]}
    now = 1000
    changes = []
    def admission():
        return {"schema": 1, "limit": board["limit"], "active": list(board["active"]), "waiting": []}
    def command(args):
        assert args[1:3] == ["set", "board.agents"], args
        value = int(args[3])
        if value > board["limit"]:
            assert value == board["limit"] + 1 or value == min(14, max(6, len(board["active"]) + 1))
        changes.append([board["limit"], value])
        board["limit"] = value
        return ""
    namespace["board_resources"] = SimpleNamespace(
        board_admission_snapshot=admission,
        board_agent_rss_census=lambda admission=None: {
            "schema": 1, "agents": [], "rss_bytes": [], "complete": False, "errors": [],
        },
    )
    namespace["command"] = command
    namespace["_read_private_json"] = lambda *args, **kwargs: dict(state) if state else None
    namespace["atomic_json"] = lambda path, value: (state.clear(), state.update(value))
    helper = SimpleNamespace(monotonic=lambda: now, admission_block_reason=heavy.admission_block_reason, critical_pressure=heavy.critical_pressure, _sample_invalid_reason=heavy._sample_invalid_reason, _finite_nonnegative=heavy._finite_nonnegative, SAMPLE_MAX_AGE=4.5)
    sample = heavy.Sample(pressure_level=1, cpu_busy_pct=20, memory_used_pct=30,
                          headroom_bytes=32*GIB, physical_bytes=48*GIB,
                          load_per_core=0.2, captured_monotonic=now, free_percent=66,
                          swap_growth_bytes_per_second=0, swapout_bytes_per_second=0,
                          physical_cores=14)
    compressor = {"compressor_growth_bytes_per_second": 0, "compressor_veto": None}
    try:
        cases = 0
        for active, current, pressure, cpu in itertools.product((0, 1, 6, 14, 30), (0, 1, 7, 30), (1, 2, 4), (50, 97)):
            state.clear()
            board.update(limit=current, active=[{"id": "fixture/" + str(n), "stage": "working"} for n in range(active)])
            now += 5
            reading = dataclasses.replace(sample, captured_monotonic=now, pressure_level=pressure, cpu_busy_pct=cpu)
            result = tick(helper, reading, compressor, cfg, "100")["decision"]
            ceiling = result["ceiling"]
            assert 0 <= board["limit"] <= ceiling, result
            if pressure == 4:
                assert board["limit"] == 0, result
            else:
                assert board["limit"] >= min(ceiling, max(6, active + 1)), result
            cases += 1
        board.update(limit=0, active=[{"id": "fixture/" + str(n), "stage": "working"} for n in range(6)])
        now += 5
        reading = dataclasses.replace(sample, captured_monotonic=now)
        result = tick(helper, reading, compressor, cfg, "100")
        assert board["limit"] == 7, result
        for reading in (None, dataclasses.replace(reading, captured_monotonic=now - 30),
                        dataclasses.replace(reading, free_percent=None)):
            board["limit"] = 0
            result = tick(helper, reading, compressor, cfg, "100")
            assert board["limit"] == 0, result
            cases += 1
        board.update(limit=7, active=[{"id": "fixture/" + str(n), "stage": "working"} for n in range(6)])
        state.clear()
        for now in range(2000, 2061, 5):
            result = tick(helper, dataclasses.replace(sample, captured_monotonic=now), compressor, cfg, "100")
            assert board["limit"] == (7 if now < 2060 else 8), result
            cases += 1
        return {"local_board_changes": changes, "local_board_cases": cases + 1}
    finally:
        namespace.update(saved)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutation-check", action="store_true")
    args = parser.parse_args()
    module = runpy.run_path(str(ROOT / "board_governor.py"))
    cfg = module["config"](ROOT / "board_governor.json")
    result = explore(module["decision"], cfg)
    result.update(explore_heavy(module["_capacity_decision"]))
    result.update(explore_local_board(module, cfg))
    if args.mutation_check:
        source = (ROOT / "board_governor.py").read_text()
        broken_source = source.replace('return result(0, "critical",', 'return result(current_value + 1, "critical", start_allowed=True,', 1)
        if broken_source == source:
            raise AssertionError("Critical branch changed; update mutation to match actual source")
        tree = ast.parse(broken_source)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "decision")
        namespace = dict(module)
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<broken-decision>", "exec"), namespace)
        broken = namespace["decision"]
        try:
            explore(broken, cfg)
        except AssertionError:
            result["growth_on_pressure_mutation_detected"] = True
        else:
            raise AssertionError("Verifier missed pressure-growth mutation")
    if args.mutation_check:
        source = (ROOT / "board_governor.py").read_text()
        changed = source.replace('critical = helper.critical_pressure(sample)', 'critical = False', 1)
        if source == changed:
            raise AssertionError("Active host-veto branch changed; update source mutation")
        function = next(node for node in ast.parse(changed).body if isinstance(node, ast.FunctionDef) and node.name == "_capacity_decision")
        namespace = dict(module)
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<broken-active-capacity>", "exec"), namespace)
        try:
            explore_heavy(namespace["_capacity_decision"])
        except AssertionError:
            result["active_pressure_growth_mutation_detected"] = True
        else:
            raise AssertionError("Verifier missed actual heavy pressure mutation")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
