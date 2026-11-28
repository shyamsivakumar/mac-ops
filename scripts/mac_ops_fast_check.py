#!/usr/bin/env python3
"""The mac-ops check, and the proof file it writes.

Every check this script runs is written to a proof file: the check, the
command that ran it, and whether it passed, failed or did not run. The
builder commits that file with the change and the gate brief reads it, so
the reviewer reads the record of the checks instead of one claimed line.
"""
import argparse
import ast
from fnmatch import fnmatch
import importlib.util
from collections import Counter
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

# The overnight runner is Python without a .py suffix, so the changed file
# list has to name it by hand.
SUFFIXLESS_PYTHON = (
    "coordinator/overnight/overnight",
    "coordinator/bin/coord-watch",
    "coordinator/bin/scorecard",
    "coordinator/pi/bin/coord-tick",
)
LOADED_SCRIPTS = (
    "coordinator/bin/coordq",
    "coordinator/bin/ticket",
)

DEFAULT_PROOF = "evidence/check-proof.md"

# Every lint tool runs through uvx at the version pinned here, so the check
# never installs an unpinned tool. This table is the only place a version lives.
TOOL_VERSIONS = {"ruff": "0.14.0", "mypy": "1.18.2"}
RUFF_VERSION = TOOL_VERSIONS["ruff"]
# Only the pyflakes and bugbear rule sets are on.
RUFF_RULES = "F,B"
# mypy checks these modules only; each one is added once it is clean.
MYPY_TARGETS = ("board_resources.py",)
RUFF_BASELINE = "scripts/ruff-baseline.txt"
FINDING_RULES = "scripts/finding_rules.json"


class NotRun(Exception):
    """A check that could not run: recorded as `not run`, not as a failure."""


def uvx_command(tool, *args):
    """The command that runs `tool` through uvx at its pinned version."""
    return ["uvx", f"{tool}@{TOOL_VERSIONS[tool]}", *args]


def require_tool(tool):
    """Raise NotRun unless uvx can run `tool` at its pinned version.

    A tool the machine cannot run is `not run` in the proof file, never a pass.
    """
    if shutil.which("uvx") is None:
        raise NotRun("uvx is not installed")
    probe = subprocess.run(uvx_command(tool, "--version"), cwd=ROOT,
                           capture_output=True, text=True, timeout=300)
    if probe.returncode != 0:
        raise NotRun(f"{tool} {TOOL_VERSIONS[tool]} is not available through uvx")


def ruff_command(*extra):
    """The pinned Ruff command for this repository.

    The overnight runner and the other commands are Python without a `.py`
    suffix, so the `.` scan leaves them out. They are named here, so a typo
    in a runner is a finding like any other.
    """
    runners = [name for name in SUFFIXLESS_PYTHON if (ROOT / name).is_file()]
    return uvx_command("ruff", "check", "--select", RUFF_RULES,
                       "--output-format", "json",
                       "--extend-exclude", "evals/harbor/tasks/*/tests/files",
                       ".", *runners, *extra)


def ruff_counts():
    """Run the pinned Ruff over the repository and count its findings.

    Raises NotRun when Ruff cannot be reached, so the proof file records
    `not run` instead of a pass the run did not earn.
    """
    require_tool("ruff")
    command = ruff_command()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)
    if result.returncode not in (0, 1):
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError(f"ruff exited {result.returncode}: {detail[0] if detail else 'no output'}")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"ruff exited {result.returncode} without a JSON report") from None
    if result.returncode == 1 and not report:
        raise RuntimeError("ruff exited 1 but reported no findings")
    return ruff_findings(report)


def ruff_findings(payload):
    """Count the findings of a Ruff JSON run by path, rule and message."""
    counts = Counter()
    for item in payload:
        name = repo_path(item["filename"])
        counts[(name, item["code"], item["message"])] += 1
    return counts


def repo_path(name):
    """The repository-relative path of a file Ruff reported."""
    path = Path(name)
    if path.is_absolute():
        try:
            return str(path.relative_to(ROOT))
        except ValueError:
            return str(path)
    return str(path)


def read_baseline(path=None):
    """Read the baseline file: finding key to how many of it are known.

    The fields are separated by a tab, so a path or a message with a space
    in it still round trips.
    """
    path = Path(path or ROOT / RUFF_BASELINE)
    baseline = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        count, name, code, message = line.split("\t")
        baseline[(name, code, message)] = int(count)
    return baseline


def write_baseline(counts, path=None):
    """Write the baseline file: one line per finding, with its count."""
    path = Path(path or ROOT / RUFF_BASELINE)
    lines = [
        "# Ruff baseline for mac-ops.",
        "#",
        "# The findings Ruff reports today, so the check fails only on findings",
        "# that are not in this file. Rule sets: F and B.",
        f"# Ruff version: {RUFF_VERSION}.",
        "# Regenerate with: python3 scripts/mac_ops_fast_check.py --write-ruff-baseline",
        "#",
        "# Format: <count>\\t<path>\\t<rule>\\t<message>",
        "",
    ]
    for (name, code, message), count in sorted(counts.items()):
        lines.append(f"{count}\t{name}\t{code}\t{message}")
    path.write_text("\n".join(lines) + "\n")


def new_findings(counts, baseline):
    """The findings the baseline does not have, and how many are new."""
    extra = []
    for key, count in sorted(counts.items()):
        if count > baseline.get(key, 0):
            extra.append((key, count - baseline.get(key, 0)))
    return extra


def check_ruff():
    """Compare the Ruff run against the baseline.

    A finding the baseline does not have fails the check. A tool that is not
    there is recorded as `not run` instead.
    """
    counts = ruff_counts()
    baseline = read_baseline()
    extra = new_findings(counts, baseline)
    for (name, code, message), count in extra:
        print(f"fast-check: new ruff finding: {name} {code} {message} (x{count})", flush=True)
    if extra:
        name, code, message = extra[0][0]
        raise RuntimeError(
            f"{sum(count for _, count in extra)} Ruff findings are not in the baseline; "
            f"first: {name} {code} {message}")
    return f"{sum(counts.values())} findings, all in the baseline"


def mypy_command():
    """The pinned mypy command. Imports are followed silently, so only the
    target modules are reported on."""
    return uvx_command("mypy", "--strict", "--follow-imports=silent", "--ignore-missing-imports",
                       "--python-version", "3.9", *MYPY_TARGETS)


def check_mypy():
    """Run the pinned mypy over the target modules; any error fails the check."""
    require_tool("mypy")
    result = subprocess.run(mypy_command(), cwd=ROOT, capture_output=True, text=True,
                            timeout=300)
    if result.returncode == 0:
        return f"{len(MYPY_TARGETS)} modules, no issues"
    lines = result.stdout.strip().splitlines()
    errors = [line for line in lines if ": error:" in line]
    if result.returncode == 1 and errors:
        for line in errors:
            print(f"fast-check: mypy: {line}", flush=True)
        raise RuntimeError(f"{len(errors)} mypy errors; first: {errors[0]}")
    detail = (result.stderr or result.stdout).strip().splitlines()
    raise RuntimeError(f"mypy exited {result.returncode}: {detail[0] if detail else 'no output'}")


FINDING_RULE_CHECKS = ("grep", "lint", "type", "property")


def validate_finding_rule(rule):
    missing = [key for key in ("id", "check", "message") if not rule.get(key)]
    if missing:
        raise ValueError(f"finding rule {rule.get('id', '?')}: missing {', '.join(missing)}")
    if rule["check"] not in FINDING_RULE_CHECKS:
        raise ValueError(f"finding rule {rule['id']}: check {rule['check']!r} is not one of "
                         f"{', '.join(FINDING_RULE_CHECKS)}")
    if rule["check"] == "grep" and not (rule.get("paths") and rule.get("pattern")):
        raise ValueError(f"finding rule {rule['id']}: a grep rule needs paths and pattern")
    if rule.get("scope", "added") not in ("added", "file"):
        raise ValueError(f"finding rule {rule['id']}: scope must be 'added' or 'file'")


def added_lines(path, base):
    diff = git("diff", "--no-renames", "-U0", base, "--", path).decode(errors="replace")
    return "\n".join(line[1:] for line in diff.splitlines()
                     if line.startswith("+") and not line.startswith("+++"))


def check_finding_rules(paths, rules=None, base=None):
    if rules is None:
        rules = json.loads((ROOT / FINDING_RULES).read_text())
    for rule in rules:
        validate_finding_rule(rule)
    found = []
    for rule in rules:
        if rule["check"] != "grep":
            continue
        for path in paths:
            if fnmatch(str(path), rule["paths"]) and (ROOT / path).is_file():
                whole_file = base is None or rule.get("scope") == "file"
                text = (ROOT / path).read_text(errors="replace") if whole_file else added_lines(path, base)
                if re.search(rule["pattern"], text):
                    found.append(f"{rule['id']}: {rule['message']} ({path})")
    return found


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def load_isolation():
    """The fake `gh` and temp logs every suite this check launches runs under."""
    loader = SourceFileLoader("gh_isolation", str(ROOT / "coordinator/bin/gh_isolation.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def live_log_counts(isolation):
    """The live log rows a run would add: its own caller's rows, the skip
    log's line count, and the usage log's total line count.

    The live coordinator writes to both files while the check runs, so the
    gh usage log is counted by the caller name the run's rows carry. The
    skip log has no caller field, so its line count is compared as it is.
    The total is reported and not compared: a row another caller wrote
    while the run was going is the live coordinator's, and a row the run
    leaked under another caller name shows up in the total.
    """
    usage = Path.home() / "Library/Logs/coordinator/gh-usage.jsonl"
    skips = Path.home() / "Library/Logs/coordinator/skips.log"
    rows = 0
    total = 0
    if usage.is_file():
        for line in usage.read_text().splitlines():
            if not line.strip():
                continue
            total += 1
            try:
                if json.loads(line).get("caller") == isolation.CALLER:
                    rows += 1
            except ValueError:
                continue
    lines = len(skips.read_text().splitlines()) if skips.is_file() else 0
    return rows, lines, total


# The suite this check runs discovers well over this many tests. A run that
# imports a module badly, or fails to discover the suite at all, reports far
# fewer, and would otherwise leave the live logs untouched and pass.
MIN_TESTS = 600


def check_isolation(run, isolation, env):
    """A full run makes no real `gh` call and writes no live log row.

    The two suites are the ones that reached GitHub and the live skip log
    before the environment was set for them. Their own result is recorded
    in the detail, and a red suite fails this check and names the failing
    tests. The run must also discover the suite and finish it, so a run that
    never got as far as the tests cannot pass by leaving the live files alone.

    Each suite runs under `env`, which names a temp root and nothing else,
    so the entry point has to install the isolation itself. The check then
    looks for the fake `gh` the entry point wrote into that root: an entry
    point that lost its installer leaves the root empty, reaches the real
    `gh` and the live logs, and fails here. Supplying the fake `gh` and the
    temp log paths from this side would hide exactly that regression.

    The fake `gh` writes every call it was not asked to answer to a file in
    the same root, so a suite that captures the fake's stderr cannot hide
    the refusal. A refusal is a failure of this check: it means the run
    reached for a call the fake does not answer, and the isolation is not
    complete.
    """
    before = live_log_counts(isolation)
    results = {}
    roots = {}
    refused = []
    for name, command, timeout in (
        ("unittest", ["python3", "-m", "unittest"], 300),
        ("selftest", ["python3", "coordinator/overnight/overnight", "selftest"], 120),
    ):
        # The root carries the run's own prefix, because the isolation tests
        # read the log paths and expect the run's name in them.
        root = isolation.make_dir(f"{isolation.CALLER}-check-{name}-")
        roots[name] = root
        child_env = {**env, isolation.ROOT_VAR: str(root)}
        results[name] = run(command, timeout=timeout, check=False, capture=True,
                            child_env=child_env)
        for fake in ("gh", "t3mcp"):
            if not (root / "bin" / fake).is_file():
                raise AssertionError(
                    f"the {name} entry point did not install the isolation: no fake "
                    f"`{fake}` in {root}, so the run reached the real one")
        refusals = root / "refusals.log"
        if refusals.is_file():
            refused.extend(refusals.read_text().splitlines())
    # The tests for this feature must pass under the environment the check
    # gives them. A run that is red here is a finding about the isolation,
    # not the machine's own state, so it fails the check.
    isolation_tests = run(
        ["python3", "-m", "unittest", "tests.test_tick_external_call_bounds.IsolationTests"],
        timeout=120, check=False, capture=True,
        child_env={**env, isolation.ROOT_VAR: str(roots["unittest"])})
    after = live_log_counts(isolation)
    if after[:2] != before[:2]:
        raise AssertionError(
            f"the run wrote to the live logs: gh-usage rows for {isolation.CALLER} "
            f"{before[0]} -> {after[0]}, skips.log lines {before[1]} -> {after[1]}")
    if refused:
        raise AssertionError(
            f"the run needed a call the fake `gh` does not answer: {refused[0]}")
    if isolation_tests.returncode != 0:
        tail = (isolation_tests.stdout + isolation_tests.stderr).strip().splitlines()[-3:]
        raise AssertionError(
            f"the isolation tests failed under the check's own environment: "
            f"{' | '.join(tail)}")
    suite = results["unittest"]
    selftest = results["selftest"]
    ran = re.search(r"^Ran (\d+) tests? in ", suite.stdout + suite.stderr, re.MULTILINE)
    if ran is None or int(ran.group(1)) < MIN_TESTS:
        found = ran.group(1) if ran else "no test count"
        raise AssertionError(
            f"the suite did not run: {found} tests, expected at least {MIN_TESTS} "
            f"(unittest exited {suite.returncode})")
    if suite.returncode != 0:
        failing = [line for line in (suite.stdout + suite.stderr).splitlines()
                   if line.startswith(('FAIL:', 'ERROR:'))]
        raise AssertionError(
            f"the unittest suite is red (exited {suite.returncode}): "
            f"{' | '.join(failing)}")
    if selftest.returncode != 0:
        raise AssertionError(
            f"the overnight selftest did not run: exited {selftest.returncode}")
    for root in roots.values():
        shutil.rmtree(root, ignore_errors=True)
    return (f"gh-usage rows for {isolation.CALLER} {before[0]}, skips.log lines "
            f"{before[1]}, unchanged after the run; gh-usage lines in total "
            f"{before[2]} -> {after[2]}; both entry points installed the fake "
            f"`gh` and `t3mcp` themselves; no call the fake `gh` refused; the isolation "
            f"tests passed; {ran.group(1)} tests ran (unittest exited "
            f"{suite.returncode}, selftest exited {selftest.returncode})")


def installed_selftest(root):
    tmp = Path(tempfile.mkdtemp(prefix="installed-selftest-"))
    home = tmp / "home"
    code = ("import json, sys\nfrom pathlib import Path\n"
            "sys.path.insert(0, sys.argv[1])\nimport install_coordinator\n"
            "print(json.dumps([[str(s), str(d), m] for s, d, m in "
            "install_coordinator.plan(Path(sys.argv[1]), Path(sys.argv[2]))]))\n")
    base_env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}
    built = subprocess.run([sys.executable, "-B", "-c", code, str(root), str(home)],
                           cwd=root, env=base_env, capture_output=True, text=True, timeout=60)
    if built.returncode != 0:
        first = built.stderr.strip().splitlines()
        return False, "plan could not be built: " + (first[0] if first else "no output")
    for src, dst, _ in json.loads(built.stdout):
        if Path(src).is_file():
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
    isolation = load_isolation()
    env = isolation.environment({**base_env, "HOME": str(home),
                                 "COORD_INBOX_DIR": str(tmp / "inbox"),
                                 isolation.ROOT_VAR: str(tmp / "isolation")})
    try:
        result = subprocess.run([sys.executable, "selftest.py"], cwd=home / ".local/bin",
                                env=env, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp, ignore_errors=True)
        return False, "installed selftest timed out"
    lines = (result.stdout + result.stderr).splitlines()
    failed = [line for line in lines if line.startswith("FAIL")]
    passed = len([line for line in lines if line.startswith("PASS")])
    ok = result.returncode == 0 and not failed
    detail = failed[0] if failed else f"exit {result.returncode}, {passed} PASS"
    shutil.rmtree(tmp, ignore_errors=True)
    return ok, detail


def imports(path):
    tree = ast.parse(path.read_bytes(), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            package = module_name(path.parent / "__init__.py") if path.name != "__init__.py" else module_name(path)
            module = node.module or ""
            if node.level:
                module = importlib.util.resolve_name("." * node.level + module, package)
            if module:
                names.add(module)
                names.update(f"{module}.{alias.name}" for alias in node.names)
    return names


def module_name(path):
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


class Proof:
    """The record of the checks one run made.

    The first check that fails stops the run, so every check after it is
    recorded as `not run` rather than left out of the file.
    """

    def __init__(self, path):
        self.path = path
        self.rows = []
        self.failed = False
        self.incomplete = False

    def check(self, name, command, action):
        """Run one check and record what happened to it."""
        if self.failed:
            self.rows.append((name, command, "not run", "an earlier check failed"))
            return False
        try:
            outcome = action()
        except subprocess.TimeoutExpired:
            self.failed = True
            self.rows.append((name, command, "failed", "the command timed out"))
            return False
        except NotRun as exc:
            self.incomplete = True
            self.rows.append((name, command, "not run", str(exc)))
            return False
        except Exception as exc:
            self.failed = True
            detail = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
            self.rows.append((name, command, "failed", detail))
            return False
        detail = outcome if isinstance(outcome, str) else ""
        self.rows.append((name, command, "passed", detail))
        return True

    def write(self, head, dirty):
        """Write the proof file of this run."""
        result = "failed" if self.failed else "incomplete" if self.incomplete else "passed"
        lines = [
            "# Check proof",
            "",
            "Command: `python3 scripts/mac_ops_fast_check.py`",
            f"Host: {socket.gethostname()}",
            f"Checked commit: `{head}`",
            f"Working tree clean when the checks ran: {'no' if dirty else 'yes'}",
            f"Run result: {result}",
            "",
            "| Check | Command | Result | Detail |",
            "| --- | --- | --- | --- |",
        ]
        for name, command, status, detail in self.rows:
            lines.append(f"| {name} | `{command}` | {status} | {detail} |")
        lines += [
            "",
            "A result is `passed`, `failed` or `not run`. A failed check stopped the run,",
            "so every check after it is `not run`. A tool that is not on this machine",
            "is recorded as `not run` too, and leaves the run incomplete: the run is",
            "then not a pass.",
            "",
        ]
        path = ROOT / self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines))


def check_lane_selection():
    loader = SourceFileLoader("coordq_lane_check", str(ROOT / "coordinator/bin/coordq"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    def issue(repo, number, priority=1, stage="todo", body=""):
        return {"repository": {"nameWithOwner": repo}, "number": number,
                "labels": [f"priority:{priority}", f"stage:{stage}"], "body": body}

    rows = [issue("a/b", 1), issue("a/b", 2, stage="started"),
            issue("a/c", 9, 2), issue("a/c", 8), issue("a/c", 7),
            issue("a/d", 1), issue("a/e", 10, body="## Blocked by\n#3"),
            issue("a/e", 11, body="## Blocked by\n#2")]
    # A stale stage:started label is a claim, not evidence: a/b#2 carries it
    # with no live thread and no open pull request, so a/b#1 is a candidate.
    selected = module.lane_candidates(rows, {"a/d"})
    assert [(r["repository"]["nameWithOwner"], r["number"]) for r in selected] == [
        ("a/b", 1), ("a/c", 7), ("a/e", 11), ("a/c", 8), ("a/e", 10), ("a/c", 9)]
    # A live lane thread still makes its repo busy.
    assert module.lane_candidates([issue("a/b", 1)], {"a/b"}) == []
    # An open, non-draft pull request that refs an open ticket makes its repo
    # busy; one that refs another number does not.
    assert module.lane_candidates([issue("a/b", 1)], set(), {"a/b": {1}}) == []
    assert module.lane_candidates([issue("a/b", 1)], set(), {"a/b": {2}})
    assert module.lane_candidates([issue("a/b", 1)], set())
    # The stale ticket is the one the refill logs, and only that one.
    assert [row["number"] for row in module.stale_started(rows, {"a/d"}, {})] == [2]
    assert module.stale_started(rows, {"a/b#2"}, {}) == []
    assert module.stale_started(rows, set(), {"a/b": {2}}) == []
    # A pull request body refs a ticket with Refs, Closes or Fixes.
    assert module.PR_REF.findall("Refs #7, closes #8 and Fixes #9") == ["7", "8", "9"]
    assert module.PR_REF.findall("refs #12") == ["12"]
    assert module.PR_REF.findall("no ticket here") == []
    config = {"repos": {"a/b": {"key": "AB"}, "a/c": {"key": "AC"}}}
    snapshots = [
        (0, '{"threads":[{"threadId":"one","title":"AB-1 build"}],"nextCursor":1}'),
        (0, '{"threads":[{"threadId":"two","clientRequestId":"gate:a/c#2:head"}]}')]
    with tempfile.TemporaryDirectory() as scratch:
        asked = []

        def threads(tool, args):
            asked.append(args)
            return snapshots[len(asked) - 1]

        with patch.object(module, "DIR", scratch), patch.object(module, "call", side_effect=threads):
            assert module.live_lane_repositories(config) == {"a/b#AB-1", "a/c#pr2"}
        # A thread that waits for an answer is still a builder in flight, so
        # the lane read asks for it: the ticket CLI counts it as live.
        assert all("waiting" in args["statuses"] for args in asked), asked
        config_path = Path(scratch) / "tickets.json"
        config_path.write_text(__import__("json").dumps(config))
        # One repo, so a ticket number names one ticket and the log line is
        # counted once.
        one_repo = Path(scratch) / "one-repo.json"
        one_repo.write_text(__import__("json").dumps({"repos": {"a/b": {"key": "AB"}}}))
        from types import SimpleNamespace
        snapshot = [[{"number": 1, "title": "busy", "labels": ["stage:started"],
                      "updated_at": "now"},
                     {"number": 2, "title": "todo", "labels": ["stage:todo"],
                      "updated_at": "now"}]]

        def gateway(pulls, calls=None):
            """The gateway answer for one pass: the issue snapshot for the
            issue read, and `pulls` for the pull request read. The pull read
            is recorded, so the check can see how it was asked for."""
            def run(argv, **kwargs):
                if "/pulls?" in argv[-1]:
                    if calls is not None:
                        calls.append((argv, kwargs))
                    body = pulls if isinstance(pulls, str) else __import__("json").dumps(pulls)
                    return SimpleNamespace(returncode=0, stdout=body)
                return SimpleNamespace(returncode=0, stdout=__import__("json").dumps(snapshot))
            return run

        def board(pulls, calls=None):
            logged = []
            with patch.object(module, "TICKETS_CONFIG", str(one_repo)), \
                    patch.object(module, "live_lane_repositories", return_value=set()), \
                    patch.object(module, "log", side_effect=logged.append), \
                    patch.object(module.gh_gateway, "run", side_effect=gateway(pulls, calls)):
                return [row["number"] for row in module.board_candidates()], logged

        # No open pull request: the stale started ticket is logged and does
        # not block its repo, and the todo ticket is the candidate.
        assert board([]) == ([2], ["refill: #1 is stage:started with no live thread or open PR"])
        # An open, non-draft pull request that refs the started ticket is
        # evidence, so nothing is logged and the repo stays busy.
        assert board([{"number": 5, "draft": False, "body": "Refs #1"}]) == ([], [])
        # A draft pull request is not a builder in flight.
        assert board([{"number": 5, "draft": True, "body": "Refs #1"}]) == (
            [2], ["refill: #1 is stage:started with no live thread or open PR"])
        # A pull request that refs a number that is not an open ticket of the
        # repo is not evidence for this repo.
        assert board([{"number": 5, "draft": False, "body": "Refs #9"}]) == (
            [2], ["refill: #1 is stage:started with no live thread or open PR"])
        # The pull read is one fresh page, so a cached or paginated read can
        # never hide a pull request that is open now.
        calls = []
        board([], calls)
        assert len(calls) == 1
        argv, kwargs = calls[0]
        assert argv[-1].endswith("/pulls?state=open&per_page=100"), argv
        assert "--paginate" not in argv and "--slurp" not in argv, argv
        assert kwargs.get("fresh") is True, kwargs
        # A pull request list that cannot be read stops the pass: a failed
        # read, a body that is not a list, a page that is not a list of pull
        # requests, and a list longer than the one page the pass may read.
        for pulls in ("not json", {}, [None], [{"number": n} for n in range(100)]):
            try:
                board(pulls)
            except (RuntimeError, ValueError):
                pass
            else:
                raise AssertionError(f"unreadable pull request snapshot accepted: {pulls!r:.40}")
        with patch.object(module, "TICKETS_CONFIG", str(one_repo)), \
                patch.object(module, "live_lane_repositories", return_value=set()), \
                patch.object(module.gh_gateway, "run", return_value=SimpleNamespace(
                    returncode=1, stdout="", stderr="boom")):
            try:
                module.board_candidates()
            except RuntimeError:
                pass
            else:
                raise AssertionError("failed pull request read accepted")
        with patch.object(module, "DIR", scratch), patch.object(module, "call", return_value=(1, "failed")):
            try:
                module.live_lane_repositories(config)
            except RuntimeError:
                pass
            else:
                raise AssertionError("failed thread snapshot accepted")
    print("PASS lane-one-active", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--lane-selection", action="store_true")
    parser.add_argument("--proof", default=DEFAULT_PROOF,
                        help="the proof file this run writes")
    parser.add_argument("--write-ruff-baseline", action="store_true",
                        help="write the Ruff baseline file and stop")
    args = parser.parse_args()
    if args.write_ruff_baseline:
        write_baseline(ruff_counts())
        print(f"fast-check: wrote {RUFF_BASELINE}", flush=True)
        return
    if args.lane_selection:
        check_lane_selection()
        return
    base = git("merge-base", "origin/main", "HEAD").decode().strip()
    changes = set(os.fsdecode(p) for p in git("diff", "--name-only", "--no-renames", "-z", base).split(b"\0") if p)
    untracked = set(os.fsdecode(p) for p in git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if p)
    changes.update(untracked)
    tracked = set(os.fsdecode(p) for p in git("ls-files", "-z").split(b"\0") if p)
    python_files = sorted(ROOT / name for name in tracked | untracked if name.endswith(".py") and (ROOT / name).is_file())
    modules = {module_name(path): path for path in python_files}
    dependencies = {name: imports(path) for name, path in modules.items()}
    affected = {module_name(ROOT / name) for name in changes if name.endswith(".py")}
    loaded = [Path(name).name for name in LOADED_SCRIPTS if name in changes]
    affected |= {name for name, path in modules.items()
                 if path.parent == ROOT / "tests"
                 and any(f'"{script}"' in path.read_text() for script in loaded)}
    while True:
        new = affected | {name for name, deps in dependencies.items() if any(dep == changed or dep.startswith(changed + ".") for dep in deps for changed in affected)}
        if new == affected:
            break
        affected = new
    tests = sorted(str(path.relative_to(ROOT)) for name, path in modules.items() if name in affected and path.parent == ROOT / "tests" and path.name.startswith("test_") and path.name.endswith(".py"))
    changed_python = sorted(name for name in changes if name.endswith(".py") and (ROOT / name).is_file())
    changed_python = sorted(
        set(changed_python)
        | {name for name in SUFFIXLESS_PYTHON if name in changes}
    )
    changed_shell = sorted(name for name in changes if name.endswith(".sh") and (ROOT / name).is_file())
    print(f"fast-check: base={base}", flush=True)
    print(f"fast-check: changed={sorted(changes)}", flush=True)
    print(f"fast-check: Python syntax={changed_python}; shell syntax={changed_shell}; tests={tests}", flush=True)
    if args.plan:
        return
    isolation = load_isolation()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
           **isolation.environment(),
           "COORD_JOURNAL_DIR": isolation.make_dir("check-journal-"),
           "COORDQ_DIR": isolation.make_dir("check-queue-")}
    # The suites that prove the entry points install the isolation run under
    # this environment instead: it carries no fake `gh` on PATH and no temp
    # log path, so an entry point that lost its installer is not covered for
    # by this side.
    entry_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                 "COORD_JOURNAL_DIR": env["COORD_JOURNAL_DIR"],
                 "COORDQ_DIR": env["COORDQ_DIR"]}
    proof = Proof(args.proof)
    head = git("rev-parse", "HEAD").decode().strip()
    dirty = [line for line in git("status", "--porcelain", "--untracked-files=all").decode().splitlines()
             if line[3:].strip() != args.proof]

    def run(command, cwd=ROOT, timeout=300, check=True, capture=False, child_env=None):
        actual = [sys.executable if part == "python3" else part for part in command]
        return subprocess.run(actual, cwd=cwd, env=child_env or env, check=check, timeout=timeout,
                              capture_output=capture, text=capture)

    lane = ["python3", "scripts/mac_ops_fast_check.py", "--lane-selection"]
    proof.check("lane selection", shlex.join(lane), lambda: run(lane, timeout=120))
    selftest = ["python3", "coordinator/overnight/overnight", "selftest"]
    proof.check("overnight selftest", shlex.join(selftest), lambda: run(selftest, timeout=60))

    def installed():
        ok, detail = installed_selftest(ROOT)
        if not ok:
            raise AssertionError(detail)
        return detail

    proof.check("installed selftest", "installed_selftest(ROOT)", installed)
    proof.check("test isolation: no live gh call or log row",
                "python3 -m unittest; " + shlex.join(selftest),
                lambda: check_isolation(run, isolation, entry_env))
    for name in changed_python:
        command = ["python3", "-c",
                   "import ast,sys;[ast.parse(open(f,'rb').read(),f) for f in sys.argv[1:]]", name]
        proof.check(f"python syntax: {name}", shlex.join(command),
                    lambda command=command: run(command, timeout=120))
    for name in changed_shell:
        command = ["/bin/sh", "-n", name]
        proof.check(f"shell syntax: {name}", shlex.join(command),
                    lambda command=command: run(command, timeout=120))

    ruff = ruff_command()
    proof.check(f"ruff {RUFF_RULES}", shlex.join(ruff), check_ruff)
    proof.check("mypy", shlex.join(mypy_command()), check_mypy)
    changed_files = sorted(name for name in changes if (ROOT / name).is_file())

    def finding_rules():
        found = check_finding_rules(changed_files, base=base)
        if found:
            raise AssertionError("; ".join(found))

    proof.check("finding rules", "check_finding_rules(changed files)", finding_rules)

    scratch = isolation.make_dir("heavy-queue-tlc-")
    model_dir = ROOT / "formal" / "heavy-queue"
    java = os.environ.get("MAC_OPS_JAVA_BIN", "/opt/homebrew/opt/openjdk@17/bin/java" if Path("/opt/homebrew/opt/openjdk@17/bin/java").is_file() else "java")
    jar = os.environ.get("MAC_OPS_TLA_JAR", str(Path.home() / "Code/llmwiki/runtime/tla/tla2tools.jar"))
    tlc_command = [java, "-Xmx128m", f"-Djava.io.tmpdir={scratch}", "-cp", jar,
                   "tlc2.TLC", "-workers", "1", "-noGenerateSpecTE",
                   "-metadir", str(scratch / "states"), "-config", "HeavyQueue.cfg",
                   "HeavyQueue.tla"]

    def tlc():
        for name in ("HeavyQueue.tla", "HeavyQueue.cfg"):
            shutil.copyfile(model_dir / name, scratch / name)
        run(tlc_command, cwd=scratch, timeout=55)

    proof.check("TLC heavy queue model", shlex.join(tlc_command), tlc)
    heavy = ["python3", "heavy.py", "--help"]
    proof.check("heavy help", shlex.join(heavy), lambda: run(heavy, timeout=120))
    for name in tests:
        module = name[:-3].replace("/", ".")
        command = ["python3", "-m", "unittest", module]
        proof.check(f"tests: {module}", shlex.join(command),
                    lambda command=command: run(command, timeout=300))
    proof.write(head, bool(dirty))
    if proof.failed:
        print(f"fast-check: failed; the proof file is {args.proof}", flush=True)
        sys.exit(1)
    if proof.incomplete:
        print(f"fast-check: incomplete; a check did not run and the proof file is {args.proof}",
              flush=True)
        sys.exit(1)
    print("fast-check: passed; selected checks are not the full suite", flush=True)


if __name__ == "__main__":
    main()
