#!/usr/bin/env python3
"""A stand-in for `gh`, so the real filter and the real second check can
be proven on a fixture board. It answers `gh issue list -R <repo> ...`
with the bodies in this folder, `gh pr view <n> -R <repo> ...` with the
pull request in this folder, and nothing else."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    argv = sys.argv[1:]
    if argv[:2] == ["issue", "list"]:
        repo = argv[argv.index("-R") + 1]
        bodies = json.loads((HERE / "bodies.json").read_text())
        print(json.dumps(bodies.get(repo, [])))
        return 0
    if argv[:2] == ["pr", "view"]:
        number = argv[2]
        pulls = json.loads((HERE / "pulls.json").read_text())
        if number not in pulls:
            print(f"fake_gh: no pull request {number}", file=sys.stderr)
            return 1
        print(json.dumps(pulls[number]))
        return 0
    print("fake_gh: only `issue list` and `pr view` are answered", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
