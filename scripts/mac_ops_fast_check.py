#!/usr/bin/env python3
import argparse
import ast
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

# The overnight runner is Python without a .py suffix, so the changed file
# list has to name it by hand.
SUFFIXLESS_PYTHON = ("coordinator/overnight/overnight", "coordinator/bin/coord-watch")


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
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
    for name in changed_python:
        ast.parse((ROOT / name).read_bytes(), filename=name)
    for name in changed_shell:
        subprocess.run(["/bin/sh", "-n", name], cwd=ROOT, check=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    scratch = Path(tempfile.mkdtemp(prefix="heavy-queue-tlc-", dir=os.environ.get("TMPDIR")))
    model_dir = ROOT / "formal" / "heavy-queue"
    for name in ("HeavyQueue.tla", "HeavyQueue.cfg"):
        shutil.copyfile(model_dir / name, scratch / name)
    java = os.environ.get("MAC_OPS_JAVA_BIN", "/opt/homebrew/opt/openjdk@17/bin/java" if Path("/opt/homebrew/opt/openjdk@17/bin/java").is_file() else "java")
    jar = os.environ.get("MAC_OPS_TLA_JAR", str(Path.home() / "Code/llmwiki/runtime/tla/tla2tools.jar"))
    subprocess.run([java, "-Xmx128m", f"-Djava.io.tmpdir={scratch}", "-cp", jar,
                    "tlc2.TLC", "-workers", "1", "-noGenerateSpecTE",
                    "-metadir", str(scratch / "states"), "-config", "HeavyQueue.cfg",
                    "HeavyQueue.tla"], cwd=scratch, env=env, check=True, timeout=55)
    subprocess.run([sys.executable, "heavy.py", "--help"], cwd=ROOT, env=env, check=True)
    for name in tests:
        subprocess.run([sys.executable, "-m", "unittest", name[:-3].replace("/", ".")], cwd=ROOT, env=env, check=True)
    subprocess.run([sys.executable, "coordinator/overnight/overnight", "selftest"], cwd=ROOT, env=env, check=True)
    print("fast-check: passed; selected checks are not the full suite", flush=True)


if __name__ == "__main__":
    main()
