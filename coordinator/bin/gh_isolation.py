"""A fake `gh` and temp logs, so a test run never reaches GitHub.

The suites run the real code paths, and those paths reach `gh_gateway.run`
and the overnight runner's skip log. A run that is not isolated spends the
live quota and appends fixture rows to the live logs, so the environment is
built once here and every test in the run inherits it.

The fake `gh` answers only the reads the tests make and fails on anything
else, so a test that needs a real call is caught instead of passing against
a fake that always succeeds.
"""
import atexit
import os
import shutil
import stat
import tempfile
from pathlib import Path

# The caller name every row the run writes carries. The proof counts the
# rows with this name, so the live coordinator's own rows are never counted
# as the run's.
CALLER = "mac-ops-test"

# The reads the tests make. Anything else is a call the run did not ask for,
# and the fake fails it rather than answering with a success it invented.
FAKE_GH = '''#!/usr/bin/env python3
"""A fake `gh` for the test run.

It answers the reads the tests make and fails on anything else, so a test
that needs a real call is caught instead of passing against a fake that
always succeeds.
"""
import json
import sys

RATE_LIMIT = {"resources": {"core": {"remaining": 5000},
                            "graphql": {"remaining": 5000}}}
PULL = {"number": 0, "state": "open", "changed_files": 1, "body": "",
        "head": {"sha": "0" * 40}}


def answer(argv):
    """Return (code, stdout, stderr), or None when the call is not known."""
    if argv[:2] == ["api", "rate_limit"]:
        return 0, json.dumps(RATE_LIMIT), ""
    if argv[:1] == ["api"] and len(argv) > 1:
        parts = argv[1].split("/")
        if len(parts) > 4 and parts[0] == "repos" and parts[3] == "pulls":
            return 0, json.dumps(PULL), ""
        if len(parts) > 4 and parts[0] == "repos" and parts[3] == "contents":
            return 1, "", "gh: Not Found (HTTP 404)"
    return None


def main():
    argv = sys.argv[1:]
    known = answer(argv)
    if known is None:
        sys.stderr.write("fake gh: no answer for " + " ".join(argv) + "\\n")
        return 1
    code, out, err = known
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _fake_gh(directory):
    """Write the fake `gh` into `directory` and return its path."""
    path = Path(directory) / "gh"
    path.write_text(FAKE_GH)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def environment(base=None):
    """Return the environment a test run needs, with the fake `gh` first.

    The fake `gh` is first on PATH, and the gh usage log, the gh cache and
    the skip log all point into one temp directory, so a run leaves the live
    files untouched. The caller name marks every row the run writes.
    """
    env = dict(os.environ if base is None else base)
    root = Path(tempfile.mkdtemp(prefix="mac-ops-test-"))
    atexit.register(shutil.rmtree, str(root), True)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    _fake_gh(bin_dir)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["COORDINATOR_GH_USAGE_LOG"] = str(root / "gh-usage.jsonl")
    env["COORDINATOR_GH_CACHE_DIR"] = str(root / "gh-cache")
    env["COORDINATOR_SKIP_LOG"] = str(root / "skips.log")
    env["COORDINATOR_CALLER"] = CALLER
    return env


def install():
    """Put the environment in this process, so every test inherits it."""
    os.environ.update(environment())
