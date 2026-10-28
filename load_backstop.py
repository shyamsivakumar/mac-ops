#!/usr/bin/env python3
"""Launch the shared Mac capacity controller or read its status."""
import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import board_governor


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=["run", "once", "status"], default="run")
    parser.add_argument("--config", type=Path, default=board_governor.CONFIG)
    parser.add_argument("--no-board-control", action="store_true",
                        help="Disable board limit changes while continuing host capacity publication")
    args = parser.parse_args(argv)
    if args.no_board_control and args.action not in ("run", "once"):
        parser.error("--no-board-control applies only to run and once")
    command = [args.action, "--config", str(args.config)]
    if args.no_board_control:
        command.append("--no-board-control")
    return board_governor.main(command)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, OverflowError, RuntimeError) as error:
        print(type(error).__name__ + ": " + str(error).splitlines()[0][:240], file=sys.stderr)
        sys.exit(1)
