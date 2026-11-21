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
import json
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
# The whole argument list is matched, so a write to a path the tests only
# read, such as `pulls/1/merge`, is refused instead of answered with the
# fixture pull request.
FAKE_GH = '''#!/usr/bin/env python3
"""A fake `gh` for the test run.

It answers the reads the tests make and fails on anything else, so a test
that needs a real call is caught instead of passing against a fake that
always succeeds.
"""
import json
import os
import sys

RATE_LIMIT = {"resources": {"core": {"remaining": 5000},
                            "graphql": {"remaining": 5000}}}
PULL = {"number": 0, "state": "open", "changed_files": 1, "body": "",
        "head": {"sha": "0" * 40}}


def answer(argv):
    """Return (code, stdout, stderr), or None when the call is not known."""
    if argv == ["api", "rate_limit"]:
        return 0, json.dumps(RATE_LIMIT), ""
    if len(argv) == 2 and argv[0] == "api":
        parts = argv[1].split("/")
        if len(parts) == 5 and parts[0] == "repos" and parts[3] == "pulls":
            return 0, json.dumps(PULL), ""
        if len(parts) > 4 and parts[0] == "repos" and parts[3] == "contents":
            return 1, "", "gh: Not Found (HTTP 404)"
    return None


def refuse(argv):
    """Write the refusal down where the check reads it, then fail.

    A suite that captures the fake's stderr would otherwise hide the
    refusal, so the refusal is also appended to the file the check reads.
    """
    line = " ".join(argv)
    path = os.environ.get("COORDINATOR_GH_REFUSALS")
    if path:
        try:
            with open(path, "a") as stream:
                stream.write(line + "\\n")
        except OSError:
            pass
    sys.stderr.write("fake gh: no answer for " + line + "\\n")
    return 1


def main():
    argv = sys.argv[1:]
    known = answer(argv)
    if known is None:
        return refuse(argv)
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


FAKE_T3MCP = '''#!/usr/bin/env python3
import json
import os
import sys

tool = sys.argv[2] if len(sys.argv) > 2 else ""
sys.stdin.read()
if tool in ("t3_thread_launch", "t3_thread_send"):
    path = os.environ.get("COORDINATOR_GH_REFUSALS")
    if path:
        try:
            with open(path, "a") as stream:
                stream.write("t3mcp " + tool + "\\n")
        except OSError:
            pass
    sys.stderr.write("fake t3mcp: no answer for " + tool + "\\n")
    raise SystemExit(1)
print(json.dumps({"total": 0, "threads": []} if tool == "t3_thread_list" else {}))
'''


def _fake_t3mcp(directory):
    path = Path(directory) / "t3mcp"
    path.write_text(FAKE_T3MCP)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# The run's temp root. A launcher that names one owns it, and every entry
# point that installs the isolation again reuses it, so the fake `gh`, the
# logs and the refusal file are one set for the whole run. Without it each
# install would make its own root, and a refusal written by a suite would
# land in a file the launcher never reads.
ROOT_VAR = "COORDINATOR_TEST_ISOLATION_DIR"

QUEUE_CONFIG = {"cap": 8}
STATE_DIRS = {"COORD_JOURNAL_DIR": "journal", "COORDQ_DIR": "queue"}


def environment(base=None):
    """Return the environment a test run needs, with the fake `gh` first.

    The fake `gh` is first on PATH, and an inherited `OVERNIGHT_GH` is
    redirected to it, and the gh usage log, the gh cache, the skip log and
    the refusal log all point into one temp directory, so a run leaves the
    live files untouched. The caller name marks every row the run writes.

    A launcher that sets `COORDINATOR_TEST_ISOLATION_DIR` owns that
    directory and reads the refusal file in it. An install that finds the
    variable reuses the directory and leaves the cleanup to the owner, so
    the entry points and the launcher share one set of files.
    """
    env = dict(os.environ if base is None else base)
    named = env.get(ROOT_VAR)
    if named:
        root = Path(named)
        root.mkdir(parents=True, exist_ok=True)
    else:
        root = Path(tempfile.mkdtemp(prefix="mac-ops-test-"))
        atexit.register(shutil.rmtree, str(root), True)
    bin_dir = root / "bin"
    bin_dir.mkdir(exist_ok=True)
    _fake_gh(bin_dir)
    env["COORDQ_T3MCP"] = str(_fake_t3mcp(bin_dir))
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    # The overnight runner takes an absolute path from this variable, which
    # would bypass PATH and reach the real `gh`. It is redirected only when
    # the caller already set it: left unset, the runner resolves `gh` on the
    # PATH above, which is the fake.
    if "OVERNIGHT_GH" in env:
        env["OVERNIGHT_GH"] = str(bin_dir / "gh")
    env[ROOT_VAR] = str(root)
    for variable, folder in STATE_DIRS.items():
        if variable not in env:
            (root / folder).mkdir(exist_ok=True)
            env[variable] = str(root / folder)
    queue = Path(env["COORDQ_DIR"])
    if not (queue / "config.json").exists():
        (queue / "config.json").write_text(json.dumps(QUEUE_CONFIG))
    env["COORDINATOR_GH_USAGE_LOG"] = str(root / "gh-usage.jsonl")
    env["COORDINATOR_GH_CACHE_DIR"] = str(root / "gh-cache")
    env["COORDINATOR_SKIP_LOG"] = str(root / "skips.log")
    env["COORDINATOR_GH_REFUSALS"] = str(root / "refusals.log")
    env["COORDINATOR_CALLER"] = CALLER
    return env


def install():
    """Put the environment in this process, so every test inherits it."""
    os.environ.update(environment())
