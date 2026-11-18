#!/usr/bin/env python3
"""Proof for MO-520 (mac-ops#520, key MO-1075): the board's progress counts merges and closed tickets.

The fixture is tonight's data (`tonight.json`): the tick times are the shift
log's own lane pass lines, and the events are the pull requests that merged
and the tickets that closed in the monitored repos. The item markers are a
reconstruction, and the proof says so: the board's progress measure reads the
events, not the marker values.

Case one, the fixture as recorded. The merge that landed at 18:27 PT is in the
window of the 18:39 PT tick, so that tick is progress and the board does not
alarm there. The board alarms at the 18:47 PT tick, three ticks after the last
merge: a real stall is still reported.

Case two, the same ticks with the events removed. The board alarms at the
18:39 PT tick, which is the alarm Shyam saw. A three tick stall with nothing
in it still alarms.

Case three, the fixture up to the 18:43 PT tick with the events. The board
never has three idle ticks, so no alert is written at all.

The proof runs the real command (`overnight stall --fixture`) over a temporary
folder. It writes nothing outside that folder and never touches the live
board, the live stall state or the live services.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMMAND = ROOT / "coordinator/overnight/overnight"
FIXTURE = Path(__file__).resolve().parent / "tonight.json"
INCIDENT = "2026-11-17 06:39 PM PT"
LAST = "2026-11-17 06:47 PM PT"


def load():
    """Return tonight's fixture."""
    data = json.loads(FIXTURE.read_text())
    assert isinstance(data.get("ticks"), list) and data["ticks"], "the fixture has no ticks"
    return data


def without_events(data):
    """Return the same ticks with the board's events removed."""
    copy = json.loads(json.dumps(data))
    for tick in copy["ticks"]:
        tick.pop("progress", None)
    return copy


def up_to(data, at):
    """Return the ticks up to and including one of them."""
    copy = json.loads(json.dumps(data))
    copy["ticks"] = [tick for tick in copy["ticks"] if tick.get("at", "") <= at]
    return copy


def run(fixture, root):
    """Run the real command over one fixture and return (lines, decisions)."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / "fixture.json"
    path.write_text(json.dumps(fixture, indent=1) + "\n")
    result = subprocess.run(
        [sys.executable, str(COMMAND), "stall", "--fixture", str(path), "--root", str(root / "records")],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    lines = result.stdout.splitlines()
    board = [line for line in lines if line.startswith("STALL board:")]
    decisions = root / "records/decisions.json"
    items = json.loads(decisions.read_text())["items"] if decisions.exists() else []
    alerts = [item for item in items if item.get("id") == "factory-overnight-stall"]
    return lines, board, alerts


def main():
    data = load()
    with tempfile.TemporaryDirectory(prefix="mo-1075-proof-") as directory:
        root = Path(directory)

        # Case one: tonight's data. The tick Shyam was alerted on is progress.
        lines, board, alerts = run(data, root / "one")
        assert board, ("the board never stalled, so the fixture proves nothing", lines)
        assert all(INCIDENT not in line for line in board), board
        assert any(LAST in line for line in board), board
        assert len(alerts) == 1, alerts
        print("PASS case one: the tick with a merge is progress; the board alarms at "
              + LAST)

        # Case two: the same ticks with nothing in them. The old alarm stands.
        lines, board, alerts = run(without_events(data), root / "two")
        assert board, ("a board with no progress never stalled", lines)
        assert any(INCIDENT in line for line in board), board
        assert len(alerts) == 1, alerts
        print("PASS case two: a real three tick stall still alarms at " + INCIDENT)

        # Case three: up to the tick after the incident, with tonight's events.
        lines, board, alerts = run(up_to(data, "2026-11-17 06:43 PM PT"), root / "three")
        assert not board, board
        assert not alerts, alerts
        print("PASS case three: no alert is written while the merges keep landing")

    print("PASS: the proof wrote nothing outside a temporary folder")


if __name__ == "__main__":
    main()
