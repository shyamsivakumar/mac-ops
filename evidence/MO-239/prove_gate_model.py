#!/usr/bin/env python3
"""Prove which gate model the backstop picks for a builder.

The rule is the coordinator's own: a Claude builder gets the Sol gate,
every other builder gets the Opus gate. The backstop (coordq gate) also
has to answer for a builder whose executed model it cannot read, and
there the two cases differ:

- a route that can run an Anthropic model is a Claude build, so it gets
  the Sol gate, the same rule a known Claude build gets;
- a builder whose model is truly unknown gets the Opus gate.

This proof stubs the network calls, so it reads nothing from the board
and changes nothing. It prints one line per case and fails when a case
does not get the model the rule gives it.

    python3 evidence/MO-239/prove_gate_model.py
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_coordq():
    """Return the queue's module, read from the checkout.

    The file has no `.py` suffix, so the loader is named: it is a script
    the coordinator runs, and the proof only reads it."""
    path = ROOT / "coordinator" / "bin" / "coordq"
    loader = importlib.machinery.SourceFileLoader("coordq", str(path))
    spec = importlib.util.spec_from_loader("coordq", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def main() -> int:
    coordq = load_coordq()
    real_chain = coordq.router_chain
    real_read = coordq.read_builder_thread
    failures = []

    def case(name, thread, runs, chain, expected, note):
        coordq.router_chain = lambda route: chain
        coordq.read_builder_thread = lambda thread_id: (thread, runs)
        try:
            model = coordq.backstop_model(thread, runs)
        finally:
            coordq.router_chain = real_chain
            coordq.read_builder_thread = real_read
        got = f"{model['instanceId']}/{model['model']}"
        want = f"{expected['instanceId']}/{expected['model']}"
        ok = model == expected
        if not ok:
            failures.append(name)
        print(f"{'PASS' if ok else 'FAIL'} {name}: {got} (expected {want}) - {note}")

    # 1. A known Claude builder: the rule the queue already applied.
    case(
        "a known Claude builder",
        {"providerInstanceId": "claudeAgent", "model": "claude-sonnet-5-5"},
        [{"executedModel": "claude-sonnet-5-5"}],
        [],
        coordq.SOL_MODEL,
        "the executed model is Claude, so the gate is Sol",
    )
    # 2. A known builder that is not Claude: the Opus gate.
    case(
        "a known builder that is not Claude",
        {"providerInstanceId": "minimax", "model": "minimax/minimax-M3.1-Flash"},
        [{"executedModel": "minimax/minimax-M3.1-Flash"}],
        [],
        coordq.OPUS_MODEL,
        "the executed model is not Claude, so the gate is Opus",
    )
    # 3. A route that can run an Anthropic model: a Claude build whose
    #    executed model the router did not report.
    case(
        "a route that can run an Anthropic model",
        {"providerInstanceId": "router", "model": "task/standard"},
        [],
        ["claude/claude-sonnet-5-5", "minimax/minimax-M3.1-Flash"],
        coordq.SOL_MODEL,
        "the chain includes Claude, so the gate is Sol",
    )
    # 4. A builder whose model is truly unknown.
    case(
        "a builder whose model is truly unknown",
        {"providerInstanceId": "", "model": ""},
        [],
        [],
        coordq.OPUS_MODEL,
        "nothing says the builder is Claude, so the gate is Opus",
    )
    # 5. The real route of this machine, read from the router's own table.
    route = coordq.router_chain("task/standard") or []
    case(
        "this machine's task/standard route",
        {"providerInstanceId": "router", "model": "task/standard"},
        [],
        route,
        coordq.SOL_MODEL if any(coordq.is_anthropic(m) for m in route) else coordq.OPUS_MODEL,
        f"the route is {route or 'unknown'}",
    )
    if failures:
        print(f"FAIL: {len(failures)} case(s) got the wrong gate model: {failures}")
        return 1
    print("PASS: every case got the gate model the rule gives it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
