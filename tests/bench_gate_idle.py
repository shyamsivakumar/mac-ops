#!/usr/bin/env python3
"""Simulate idle-agent terminal spinner load through gate output paths."""

import importlib.util
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPINNER = (
    b"\x1b[K\x1b[1;32m\xe2\xa0\x8b\x1b[0m working..."
    b"\r\x1b[K\x1b[1;32m\xe2\xa0\x99\x1b[0m working...\r"
)
FRAMES = 3000


def load_gate(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _devnull_stdout(gate, sink):
    gate.stdout = lambda data: None if not data else sink.write(data) or None


def run_heavy(gate, frames: int) -> float:

    queries = gate.Queries()
    visible = gate.Visible()
    with open(os.devnull, "wb") as sink:
        _devnull_stdout(gate, sink)
        start = time.perf_counter()
        for i in range(frames):
            raw = SPINNER if i % 2 == 0 else SPINNER[::-1][: len(SPINNER)]
            gate.stdout(raw)
            gate.stdout(b"\x1b[?2004h")
            queries.observe(raw)
            visible.feed(raw)
        return time.perf_counter() - start


def run_passthrough(gate, frames: int) -> float:
    with open(os.devnull, "wb") as sink:
        _devnull_stdout(gate, sink)
        start = time.perf_counter()
        for i in range(frames):
            raw = SPINNER if i % 2 == 0 else SPINNER[::-1][: len(SPINNER)]
            gate.stdout(raw)
        return time.perf_counter() - start


def main() -> int:
    gate = load_gate("cursor_agent_gate.py")
    heavy_s = run_heavy(gate, FRAMES)
    light_s = run_passthrough(gate, FRAMES)
    ratio = heavy_s / light_s if light_s else float("inf")
    print(f"frames={FRAMES}")
    print(f"heavy_path_sec={heavy_s:.3f}")
    print(f"passthrough_sec={light_s:.3f}")
    print(f"ratio={ratio:.2f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
