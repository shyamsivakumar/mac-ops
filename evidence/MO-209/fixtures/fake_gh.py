#!/usr/bin/env python3
"""A stand-in for `gh`, so the real filter can be proven on a fixture
board. It answers `gh issue list -R <repo> ... --json number,title,body`
with the bodies in this folder and nothing else."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    argv = sys.argv[1:]
    if argv[:2] != ["issue", "list"]:
        print("fake_gh: only `issue list` is answered", file=sys.stderr)
        return 2
    repo = argv[argv.index("-R") + 1]
    bodies = json.loads((HERE / "bodies.json").read_text())
    print(json.dumps(bodies.get(repo, [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
