#!/usr/bin/env python3
"""A stand-in for the ticket CLI, so the real filter can be proven on a
fixture board. It answers `ticket list --fresh --json` with the board in
this folder and nothing else."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    if len(sys.argv) < 4 or sys.argv[1:4] != ["list", "--fresh", "--json"]:
        print("fake_ticket: only `list --fresh --json` is answered", file=sys.stderr)
        return 2
    board = json.loads((HERE / "board.json").read_text())
    print(json.dumps(board, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
