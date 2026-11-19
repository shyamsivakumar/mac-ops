#!/usr/bin/env python3
"""Replay captured host readings through controller_tick without external writes."""
import argparse
import dataclasses
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import heavy

BOARD_FLOOR_REPLAY_TIME = 1793150983.444375
BOARD_FLOOR_REPLAY_WINDOW_SECONDS = 30.0


def boardfloor_source(path):
    candidates = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        row = json.loads(line)
        board = row.get("board")
        decision = board.get("decision") if isinstance(board, dict) else None
        stamp = row.get("updated_at")
        if (not isinstance(stamp, (int, float)) or isinstance(stamp, bool)
                or abs(float(stamp) - BOARD_FLOOR_REPLAY_TIME) > BOARD_FLOOR_REPLAY_WINDOW_SECONDS
                or not isinstance(decision, dict)
                or decision.get("current") != 0
                or decision.get("active") != 6
                or decision.get("reason") != "await_healthy_window"):
            continue
        host = row.get("host")
        census = row.get("census")
        compressor = row.get("compressor")
        capacity = row.get("capacity")
        active_ids = decision.get("active_ids")
        if (not isinstance(host, dict) or not isinstance(census, dict)
                or not isinstance(compressor, dict) or not isinstance(capacity, dict)
                or type(capacity.get("heavy_slots")) is not int
                or not isinstance(active_ids, list) or len(active_ids) != 6
                or any(not isinstance(task_id, str) for task_id in active_ids)):
            continue
        candidates.append((abs(float(stamp) - BOARD_FLOOR_REPLAY_TIME), line_number, row))
    if not candidates:
        raise ValueError("No valid board-floor source row matched the recorded zero-limit six-active sample")
    _, line_number, row = min(candidates, key=lambda item: (item[0], item[1]))
    board = row["board"]
    decision = board["decision"]
    if row.get("board_control") is not True or board.get("control") != "enabled":
        raise ValueError("Board-floor source row did not have board control enabled")
    return line_number, row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overload", type=Path)
    parser.add_argument("--starvation", type=Path)
    parser.add_argument("--boardfloor", type=Path,
                        help="Controller JSONL with the recorded zero-to-board-floor sample")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.overload is None and args.starvation is None and args.boardfloor is None:
        parser.error("at least one of --overload, --starvation, or --boardfloor is required")
    module = runpy.run_path(str(ROOT / "board_governor.py"))
    tick = module["controller_tick"]
    namespace = tick.__globals__
    cfg = module["config"](ROOT / "board_governor.json")
    args.output.mkdir(parents=True, exist_ok=True)
    summaries = []
    modes = []
    if args.overload is not None:
        modes.append(("overload", args.overload))
    if args.starvation is not None:
        modes.append(("starvation", args.starvation))
    if args.boardfloor is not None:
        modes.append(("boardfloor", args.boardfloor))
    for mode, path in modes:
        namespace["_cpu_history"].clear()
        store = {}
        clock = {"wall": 0, "mono": 0}
        board = {"limit": 8}
        context = {}
        boot = "1793065584"

        class Helper:
            def __getattr__(self, key):
                return getattr(heavy, key)

            def sample_with_emergency(self):
                return context["sample"]

            def kernel_boot_identity(self):
                return boot

            def monotonic(self):
                return clock["mono"]

            def request_critical_pauses(self):
                context["calls"].append("critical_pause_request")
                return []

            def reap_dead_jobs(self):
                return 0

        helper = Helper()

        def command(argv):
            if argv[1:3] != ["set", "board.agents"]:
                raise AssertionError("Unexpected replay side effect")
            board["limit"] = int(argv[3])
            return ""

        def admission_snapshot():
            context["calls"].append("board_read")
            return {"schema": 1, "limit": board["limit"],
                    "active": context.get("board_active", [{"id": "replay/1", "stage": "working"}]),
                    "waiting": []}

        def save(path, value):
            store[Path(path).name] = dict(value)
            context["calls"].append(Path(path).name)

        def board_agent_rss_census(_admission=None):
            return context.get("board_agent_census") or {
                "schema": 1, "agents": [], "rss_bytes": [], "complete": False, "errors": [],
            }

        resources = SimpleNamespace(
            compressor_snapshot=lambda: context["compressor"],
            active_heavy_census=lambda: context["census"],
            board_admission_snapshot=admission_snapshot,
            board_agent_rss_census=board_agent_rss_census,
        )
        namespace.update(
            _heavy_module=lambda: helper,
            _ensure_state_dir=lambda **kwargs: module["STATE_DIR"],
            _read_private_json=lambda path, **kwargs: store.get(Path(path).name),
            atomic_json=save,
            append_log=lambda value: None,
            board_resources=resources,
            command=command,
            time=SimpleNamespace(time=lambda: clock["wall"], monotonic=lambda: clock["mono"]),
        )
        count = critical_rows = floor_rows = explicit_unknown = 0
        loads = []
        selected_boardfloor = boardfloor_source(path) if mode == "boardfloor" else None
        with (args.output / (mode + ".jsonl")).open("w") as out:
            for line_number, line in enumerate(path.read_text().splitlines(), 1):
                row = json.loads(line)
                if mode == "boardfloor" and line_number != selected_boardfloor[0]:
                    continue
                if mode == "overload":
                    reading = row.get("readings", {})
                    load, cores = reading.get("load1"), reading.get("cores")
                    if not isinstance(load, (int, float)) or not isinstance(cores, (int, float)) or cores <= 0 or load < 2 * cores:
                        continue
                    host = {
                        "pressure_level": reading.get("pressure"),
                        "cpu_busy_pct": reading.get("cpu_busy_pct"),
                        "memory_used_pct": reading.get("memory_used_pct"),
                        "headroom_bytes": reading.get("available_bytes"),
                        "physical_bytes": reading.get("total_bytes"),
                        "load_per_core": load / cores,
                        "captured_monotonic": float(row["time"]),
                        "free_percent": reading.get("free_percent"),
                        "swap_growth_bytes_per_second": reading.get("swap_growth_bytes_per_second"),
                        "swapout_bytes_per_second": reading.get("swapout_bytes_per_second"),
                        "physical_cores": cores,
                    }
                    current = row.get("current", (row.get("decision") or {}).get("current", 0))
                    clock.update(wall=float(row["time"]), mono=float(row["time"]))
                    compressor = {"compressor_bytes": reading.get("compressor_bytes"), "sampled_monotonic": clock["mono"]}
                    loads.append(load)
                elif mode == "starvation":
                    host = row.get("host")
                    if not isinstance(host, dict):
                        continue
                    stamp = row.get("updated_at", (row.get("capacity") or {}).get("updated_at"))
                    if not isinstance(stamp, (int, float)) or not 1793138400 <= stamp <= 1793146200:
                        continue
                    current = (store.get("capacity.json") or {}).get("heavy_slots", 0)
                    clock.update(wall=stamp, mono=host["captured_monotonic"])
                    compressor = row.get("compressor") or {"compressor_bytes": None, "sampled_monotonic": clock["mono"]}
                else:
                    host = row["host"]
                    census = row["census"]
                    compressor = row["compressor"]
                    source_board = row["board"]
                    source_decision = source_board["decision"]
                    stamp = row["updated_at"]
                    current = row["capacity"]["heavy_slots"]
                    board["limit"] = source_board["current"]
                    context["board_active"] = [
                        {"id": task_id, "stage": "working"}
                        for task_id in source_decision["active_ids"]
                    ]
                    boot = census["boot_id"]
                    clock.update(wall=stamp, mono=host["captured_monotonic"])
                fields = {field.name for field in dataclasses.fields(heavy.Sample)}
                sample = heavy.Sample(**{key: host.get(key) for key in fields})
                census = row.get("census") if mode == "starvation" else census if mode == "boardfloor" else None
                if not isinstance(census, dict):
                    census = {"boot_id": boot, "active": None, "registry_active": None,
                              "legacy_active": None, "job_rss_bytes": []}
                context.update(sample=sample, compressor=compressor, census=census, calls=[])
                store["capacity.json"] = {"heavy_slots": int(current), "updated_at": clock["wall"], "boot_id": boot}
                entry = tick(board_control=True, cfg=cfg)
                target = entry["capacity"]["heavy_slots"]
                critical = namespace["_critical_pressure"](
                    heavy, dataclasses.replace(sample, cpu_busy_pct=entry["host"]["cpu_busy_pct"]))
                valid = heavy._sample_invalid_reason(sample, clock["mono"]) is None
                if critical:
                    assert target == 0, (line_number, entry)
                    assert entry["board"]["decision"]["target"] == 0, (line_number, entry)
                    calls = context["calls"]
                    assert calls.index("capacity.json") < calls.index("critical_pause_request") < calls.index("board_read"), calls
                    critical_rows += 1
                elif valid:
                    assert target >= 2, (line_number, entry)
                    floor_rows += 1
                else:
                    assert target <= current, (line_number, entry)
                    explicit_unknown += 1
                if mode == "overload":
                    assert target <= current
                if mode == "boardfloor":
                    board_decision = entry["board"]["decision"]
                    assert not critical, (line_number, entry)
                    assert board_decision["current"] == 0, (line_number, entry)
                    assert board_decision["active"] == 6, (line_number, entry)
                    assert board_decision["floor"] == 7, (line_number, entry)
                    assert board_decision["target"] == 7, (line_number, entry)
                    assert board_decision["reason"] == "board_baseline_floor", (line_number, entry)
                    assert board["limit"] == 7, (line_number, entry)
                record = {"source_line": line_number, "time": clock["wall"], "mode": mode,
                          "recorded_current": current, "target": target, "critical": critical,
                          "complete_host": valid, "decision": entry.get("heavy_decision"),
                          "error": entry.get("heavy_error"), "board": entry.get("board"),
                          "io_order": context["calls"]}
                if mode == "boardfloor":
                    record["recorded_board_limit"] = source_board["current"]
                    record["source_fields"] = row
                out.write(json.dumps(record, allow_nan=False) + "\n")
                count += 1
        assert count > 0, "No source readings selected for " + mode
        summary = {"mode": mode, "rows": count, "critical_zero": critical_rows,
                   "noncritical_floor": floor_rows, "incomplete_holds": explicit_unknown,
                   "min_load": min(loads) if loads else None,
                   "max_load": max(loads) if loads else None, "passed": True}
        if mode == "boardfloor":
            summary.update(source_time=selected_boardfloor[1]["updated_at"],
                           expected_board_limit=7, replayed_board_limit=board["limit"])
        summaries.append(summary)
    (args.output / "summary.json").write_text(json.dumps(summaries, indent=2))
    print(json.dumps(summaries))


if __name__ == "__main__":
    main()
