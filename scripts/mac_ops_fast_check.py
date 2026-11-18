#!/usr/bin/env python3
"""The mac-ops check, and the proof file it writes.

Every check this script runs is written to a proof file: the check, the
command that ran it, and whether it passed, failed or did not run. The
builder commits that file with the change and the gate brief reads it, so
the reviewer reads the record of the checks instead of one claimed line.
"""
import argparse
import ast
import importlib.util
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

# The overnight runner is Python without a .py suffix, so the changed file
# list has to name it by hand.
SUFFIXLESS_PYTHON = (
    "coordinator/overnight/overnight",
    "coordinator/bin/coord-watch",
    "coordinator/pi/bin/coord-tick",
)

DEFAULT_PROOF = "evidence/check-proof.md"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


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

    def check(self, name, command, action):
        """Run one check and record what happened to it."""
        if self.failed:
            self.rows.append((name, command, "not run", "an earlier check failed"))
            return False
        try:
            action()
        except subprocess.TimeoutExpired:
            self.failed = True
            self.rows.append((name, command, "failed", "the command timed out"))
            return False
        except Exception as exc:
            self.failed = True
            detail = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
            self.rows.append((name, command, "failed", detail))
            return False
        self.rows.append((name, command, "passed", ""))
        return True

    def write(self, head, dirty):
        """Write the proof file of this run."""
        lines = [
            "# Check proof",
            "",
            "Command: `python3 scripts/mac_ops_fast_check.py`",
            f"Checked commit: `{head}`",
            f"Working tree clean when the checks ran: {'no' if dirty else 'yes'}",
            "",
            "| Check | Command | Result | Detail |",
            "| --- | --- | --- | --- |",
        ]
        for name, command, status, detail in self.rows:
            lines.append(f"| {name} | `{command}` | {status} | {detail} |")
        lines += [
            "",
            "A result is `passed`, `failed` or `not run`. A failed check stopped the run,",
            "so every check after it is `not run`.",
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
    selected = module.lane_candidates(rows, {"a/d"})
    assert [(r["repository"]["nameWithOwner"], r["number"]) for r in selected] == [
        ("a/c", 7), ("a/e", 11)]
    assert module.lane_candidates([issue("a/b", 1)], set())
    config = {"repos": {"a/b": {"key": "AB"}, "a/c": {"key": "AC"}}}
    snapshots = [
        (0, '{"threads":[{"threadId":"one","title":"AB-1 build"}],"nextCursor":1}'),
        (0, '{"threads":[{"threadId":"two","clientRequestId":"gate:a/c#2:head"}]}')]
    with tempfile.TemporaryDirectory() as scratch:
        with patch.object(module, "DIR", scratch), patch.object(module, "call", side_effect=snapshots):
            assert module.live_lane_repositories(config) == {"a/b", "a/c"}
        config_path = Path(scratch) / "tickets.json"
        config_path.write_text(__import__("json").dumps(config))
        from types import SimpleNamespace
        snapshot = [[{"number": 1, "title": "busy", "labels": ["stage:started"],
                      "updated_at": "now"},
                     {"number": 2, "title": "todo", "labels": ["stage:todo"],
                      "updated_at": "now"}]]
        with patch.object(module, "TICKETS_CONFIG", str(config_path)), \
                patch.object(module, "live_lane_repositories", return_value=set()), \
                patch.object(module.subprocess, "run", return_value=SimpleNamespace(
                    returncode=0, stdout=__import__("json").dumps(snapshot))):
            assert module.board_candidates() == []
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
    args = parser.parse_args()
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
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proof = Proof(args.proof)
    head = git("rev-parse", "HEAD").decode().strip()
    dirty = [line for line in git("status", "--porcelain").decode().splitlines()
             if line[3:].strip() != args.proof]

    def run(command, cwd=ROOT, timeout=300):
        actual = [sys.executable if part == "python3" else part for part in command]
        return subprocess.run(actual, cwd=cwd, env=env, check=True, timeout=timeout)

    lane = ["python3", "scripts/mac_ops_fast_check.py", "--lane-selection"]
    proof.check("lane selection", shlex.join(lane), lambda: run(lane, timeout=120))
    selftest = ["python3", "coordinator/overnight/overnight", "selftest"]
    proof.check("overnight selftest", shlex.join(selftest), lambda: run(selftest, timeout=60))
    for name in changed_python:
        command = ["python3", "-c",
                   "import ast,sys;[ast.parse(open(f,'rb').read(),f) for f in sys.argv[1:]]", name]
        proof.check(f"python syntax: {name}", shlex.join(command),
                    lambda command=command: run(command, timeout=120))
    for name in changed_shell:
        command = ["/bin/sh", "-n", name]
        proof.check(f"shell syntax: {name}", shlex.join(command),
                    lambda command=command: run(command, timeout=120))

    scratch = Path(tempfile.mkdtemp(prefix="heavy-queue-tlc-", dir=os.environ.get("TMPDIR")))
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
    print("fast-check: passed; selected checks are not the full suite", flush=True)


if __name__ == "__main__":
    main()
