#!/usr/bin/env python3
"""Build Harbor task folders from evals/harbor/sets/ladder.json.

build    writes tasks/<id>/ (instruction, Dockerfile, tests, solution, task.toml)
prepare  writes the parent-commit snapshot into .cache/<id>/ and links it into
         the task's build context; the snapshot never holds a credential and is
         gitignored.
check    verifies ids, merge parents and the frozen held-out slice.
add      appends one merged PR to the selection (usage: add REPO PR).
"""

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HARBOR = Path(__file__).resolve().parent
SELECTION = HARBOR / "sets" / "ladder.json"
TASKS = HARBOR / "tasks"
CACHE = HARBOR / ".cache"
HELDOUT_MODULUS = 4
DROPPED_HEADING = re.compile(
    r"(?i)^(gate|finish|ci|rollback|source|blocked by|type|approval|data/secrets|"
    r"addition|earlier review|left for later|closing|update|after the merge|"
    r"what changed|proof|checks|round|fix round)\b"
)
DROPPED_SENTENCE = re.compile(
    r"(?i)no new unit tests|stop and (report|ask)|stop before|ask shyam|"
    r"report before coding|state the exact command|builder check|\bpaste\b|pr body|"
    r"mac_ops_fast_check|no new test files|say so in the pr"
)
SENSITIVE = re.compile(
    r"(?i)railway (project|service|variable|cli)|_secret\b|_token\b|--skip-deploys|api[_ -]?key|"
    r"\bcopy\b[^.]*\bsecret|\bproduction (service|variable|env)"
)
TEST_FILE = re.compile(r"(?i)^(test_.*|.*_test\.\w+|test\w*\.(js|cjs|mjs))$")
TICKET_REF = re.compile(r"(?i)\b(?:refs|closes|fixes|resolves)\s+#(\d+)")
NOT_SOURCE = ("tests/", "evidence/", "docs/")
FIX_STATEMENT = (
    r"(?i)builder check: pass [0-9a-f]{{7,}}|closing note|merged via #{pr}\b|"
    r"fix round \d+ on|\bhead: [0-9a-f]{{7,}}"
)

DOCKERFILES = {
    "python": """FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates gh python3 python3-pip python3-pytest && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ADD snapshot.tar /app/
RUN git init -q && git add -A && git -c user.name=snapshot -c user.email=snapshot@localhost commit -q -m snapshot
""",
    "node": """FROM node:22-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ADD snapshot.tar /app/
RUN {install}
RUN git init -q && git add -A && git -c user.name=snapshot -c user.email=snapshot@localhost commit -q -m snapshot
""",
}

TASK_TOML = """schema_version = "1.4"
artifacts = []

[task]
name = "ladder/{id}"
version = "1.0.0"
description = "{description}"
keywords = ["ladder", "{type}"]
[[task.authors]]
name = "Shyam Sivakumar"
email = "shyam@example.com"

[metadata]
repo = "{repo}"
pr = {pr}
type = "{type}"

[verifier]
timeout_sec = {verifier_timeout}
environment_mode = "shared"
collect = []

[verifier.env]

[agent]
timeout_sec = {agent_timeout}

[environment]
network_mode = "public"
build_timeout_sec = 900.0
os = "linux"
mcp_servers = []

[environment.env]

[solution.env]
"""

TEST_SH = """#!/bin/bash
# Copies the PR's own test files over the working tree, runs them, and writes
# the reward: 1 when the tests pass, 0 when they fail.

set -u

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

cd /app || exit 1
cp -R "$(dirname "$0")/files/." /app/ || exit 1

if {test_command}; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt
"""

SOLVE_SH = """#!/bin/bash
# The oracle solution: the merged diff without its test files.

set -euo pipefail

cd /app
git apply --whitespace=nowarn "$(dirname "$0")/fix.patch"
"""


def run(args, cwd=None, binary=False):
    result = subprocess.run(args, cwd=cwd, capture_output=True, check=True)
    return result.stdout if binary else result.stdout.decode()


def load():
    return json.loads(SELECTION.read_text())


def local_repo(selection, key):
    return Path(os.path.expanduser(selection["repos"][key]["local"]))


def heldout_for(group):
    digest = hashlib.sha256(group.encode()).hexdigest()
    return int(digest, 16) % HELDOUT_MODULUS == 0


def clean_paragraph(text):
    lines = []
    for line in text.splitlines():
        sentences = re.split(r"(?<=[.!?])\s+", line)
        kept = [x for x in sentences if not DROPPED_SENTENCE.search(x)]
        if kept:
            lines.append(" ".join(kept))
    return "\n".join(lines)


def fetch_ticket(github, number, pr):
    issue = json.loads(run(["gh", "api", f"repos/{github}/issues/{number}"]))
    if issue.get("pull_request"):
        raise ValueError(f"ticket {number} is a pull request")
    merged_at = json.loads(run(["gh", "api", f"repos/{github}/pulls/{pr}"]))[
        "merged_at"
    ]
    issue["merged_at"] = merged_at
    return issue


def ticket_text(github, number, pr):
    issue = fetch_ticket(github, number, pr)
    kept = []
    for section in re.split(r"(?m)^(?=## )", issue["body"] or ""):
        heading = re.match(r"## (.+)", section)
        if heading and DROPPED_HEADING.match(heading.group(1).strip()):
            continue
        if not heading:
            section = "\n".join(
                line
                for line in section.splitlines()
                if not re.match(r"(?i)^(type|source)\b", line)
            )
        kept.append(clean_paragraph(section).strip())
    body = "\n\n".join(part for part in kept if part)
    if issue["updated_at"] > issue["merged_at"] and re.search(FIX_STATEMENT.format(pr=pr), body):
        raise ValueError(f"ticket {number} was edited after the merge and states the fix")
    hits = sorted({m.group(0).lower() for m in SENSITIVE.finditer(body)})
    if hits:
        raise ValueError(f"ticket {number} mentions {hits}")
    return f"# {issue['title']}\n\n{body}\n"


PY_FUNCTION = (ast.FunctionDef, ast.AsyncFunctionDef)
JS_PATTERNS = (
    (re.compile(r"(?m)^(?:async\s+)?function\s*\*?\s*(\w+)\s*\(([^)]*)\)"),
     "function {0}({1})"),
    (re.compile(r"(?m)^(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>"),
     "function {0}({1})"),
    (re.compile(r"(?m)^(?:const|let|var)\s+(\w+)\s*=(?!\s*(?:async\s*)?\(|\s*require\()"), "constant {0}"),
    (re.compile(r"(?m)^class\s+(\w+)"), "class {0}"),
    (re.compile(r"(?m)^\s+(?:async\s+)?(?!if|for|while|switch|catch|function)(\w+)\s*\(([^)]*)\)\s*\{"),
     "method {0}({1})"),
    (re.compile(r"(?m)^\s+(\w+):\s*(?:async\s*)?(?:function\s*)?\(([^)]*)\)"),
     "method {0}({1})"),
    (re.compile(r"(?m)^\s*(?:module\.)?exports\.(\w+)\s*=\s*(?:async\s*)?(?:function\s*)?\(([^)]*)\)"),
     "function {0}({1})"),
)


def python_symbols(source):
    symbols = {}
    for node in ast.parse(source).body:
        if isinstance(node, PY_FUNCTION):
            symbols[node.name] = f"def {node.name}({ast.unparse(node.args)})"
        elif isinstance(node, ast.ClassDef):
            symbols[node.name] = f"class {node.name}"
            for sub in node.body:
                if isinstance(sub, PY_FUNCTION):
                    symbols[f"{node.name}.{sub.name}"] = (
                        f"def {node.name}.{sub.name}({ast.unparse(sub.args)})"
                    )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    symbols[target.id] = f"constant {target.id}"
    return symbols


def javascript_symbols(source):
    symbols = {}
    for pattern, template in JS_PATTERNS:
        for match in pattern.finditer(source):
            symbols.setdefault(match.group(1), template.format(*match.groups()))
    return symbols


def symbols_in(source, path):
    try:
        if path.endswith((".js", ".cjs", ".mjs")):
            return javascript_symbols(source)
        return python_symbols(source)
    except SyntaxError:
        return {}


def show(local, commit, path):
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=local, capture_output=True
    )
    return result.stdout.decode(errors="replace") if result.returncode == 0 else None


def interface_lines(selection, task):
    local = local_repo(selection, task["repo"])
    test_text = "\n".join(
        show(local, task["merge"], path) or "" for path in task["test_files"]
    )
    names = run(
        ["git", "diff", "--name-status", task["parent"], task["merge"]], cwd=local
    ).splitlines()
    lines = []
    for entry in names:
        status, _, path = entry.partition("\t")
        if path in task["test_files"] or path.startswith(("evidence/", "docs/")):
            continue
        after = show(local, task["merge"], path)
        if after is None:
            continue
        before = show(local, task["parent"], path)
        if before is None:
            stem = Path(path).stem
            if re.search(rf"\b{re.escape(stem)}\b", test_text):
                lines.append(f"- new file `{path}`")
        old = symbols_in(before, path) if before else {}
        for name, signature in symbols_in(after, path).items():
            leaf = name.split(".")[-1]
            if old.get(name) == signature or not re.search(rf"\b{re.escape(leaf)}\b", test_text):
                continue
            lines.append(f"- `{path}`: `{signature}`")
    return lines


def interface_section(selection, task):
    lines = interface_lines(selection, task)
    if not lines:
        return ""
    return (
        "\n## Interface\n\nThe tests use these names and signatures, which "
        "the change must provide (names only, no behaviour implied):\n\n"
        + "\n".join(lines)
        + "\n"
    )


def shared_groups(tasks):
    owners = {}
    for task in tasks:
        for path in task["test_files"]:
            if path.endswith((".py", ".js", ".cjs")):
                owners.setdefault(path, []).append(task["id"])
    parent = {task["id"]: task["id"] for task in tasks}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    label = {}
    for path, ids in sorted(owners.items()):
        for other in ids[1:]:
            parent[find(other)] = find(ids[0])
        if len(ids) > 1:
            label.setdefault(find(ids[0]), Path(path).stem)
    return {
        task["id"]: label.get(find(task["id"]), task["id"]) for task in tasks
    }


def build_task(selection, task):
    repo = selection["repos"][task["repo"]]
    local = local_repo(selection, task["repo"])
    folder = TASKS / task["id"]
    if folder.exists():
        shutil.rmtree(folder)
    for sub in ("environment", "tests/files", "solution"):
        (folder / sub).mkdir(parents=True)

    (folder / "instruction.md").write_text(
        ticket_text(repo["github"], task["ticket"], task["pr"])
        + interface_section(selection, task)
        + "\nThe repository is at `/app`. Make the change there. "
        "Do not edit test files.\n"
    )

    dockerfile = DOCKERFILES[repo["profile"]].format(
        install=repo.get("install", "true")
    )
    (folder / "environment" / "Dockerfile").write_text(dockerfile)

    for path in task["test_files"]:
        content = run(
            ["git", "show", f"{task['merge']}:{path}"], cwd=local, binary=True
        )
        target = folder / "tests" / "files" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    test_sh = folder / "tests" / "test.sh"
    test_sh.write_text(TEST_SH.format(test_command=task["test_command"]))
    test_sh.chmod(0o755)

    excludes = [f":(exclude){p}" for p in task["test_files"]]
    patch = run(
        [
            "git",
            "diff",
            "--binary",
            task["parent"],
            task["merge"],
            "--",
            ".",
            *excludes,
        ],
        cwd=local,
        binary=True,
    )
    (folder / "solution" / "fix.patch").write_bytes(patch)
    solve_sh = folder / "solution" / "solve.sh"
    solve_sh.write_text(SOLVE_SH)
    solve_sh.chmod(0o755)

    (folder / "task.toml").write_text(
        TASK_TOML.format(
            id=task["id"],
            description=f"{task['repo']} PR {task['pr']}",
            type=task["type"],
            repo=task["repo"],
            pr=task["pr"],
            agent_timeout=repo.get("agent_timeout", 900.0),
            verifier_timeout=repo.get("verifier_timeout", 600.0),
        )
    )


def add_task(selection, repo, pr):
    if repo not in selection["repos"]:
        raise ValueError(f"unknown repo {repo}")
    task_id = f"{repo}-{pr}"
    if any(t["id"] == task_id for t in selection["tasks"]):
        return None
    profile = selection["repos"][repo]
    local = local_repo(selection, repo)
    pull = json.loads(run(["gh", "api", f"repos/{profile['github']}/pulls/{pr}"]))
    if not pull.get("merged_at"):
        raise ValueError(f"PR {pr} is not merged")
    merge = pull["merge_commit_sha"]
    parents = run(["git", "rev-list", "--parents", "-n", "1", merge], cwd=local).split()[1:]
    if len(parents) != 1:
        raise ValueError(f"{merge} is not a single-parent merge commit")
    ticket = TICKET_REF.search(pull["body"] or "")
    if not ticket:
        raise ValueError(f"PR {pr} does not name its ticket")
    changes = [
        entry.partition("\t")[::2]
        for entry in run(
            ["git", "diff", "--name-status", parents[0], merge], cwd=local
        ).splitlines()
    ]
    files = [path.split("\t")[-1] for _, path in changes if TEST_FILE.match(Path(path).name)]
    if not files:
        raise ValueError(f"PR {pr} changes no test file")
    added = [
        path.split("\t")[-1]
        for status, path in changes
        if status == "A" and not path.startswith(NOT_SOURCE)
    ]
    command = (
        f"python3 -m pytest -q -x {' '.join(files)}"
        if profile["profile"] == "python"
        else " && ".join(f"node {path}" for path in files)
    )
    selection["tasks"].append(
        {
            "id": task_id,
            "repo": repo,
            "pr": pr,
            "ticket": int(ticket.group(1)),
            "merge": merge,
            "parent": parents[0],
            "type": "feature" if added else "bugfix",
            "test_command": command,
            "test_files": files,
            "heldout": False,
            "group": task_id,
        }
    )
    groups = shared_groups(selection["tasks"])
    for entry in selection["tasks"]:
        entry["group"] = groups[entry["id"]]
        entry["heldout"] = heldout_for(entry["group"])
    SELECTION.write_text(json.dumps(selection, indent=2) + "\n")
    return task_id


def prepare_task(selection, task):
    local = local_repo(selection, task["repo"])
    cache = CACHE / task["id"]
    cache.mkdir(parents=True, exist_ok=True)
    snapshot = cache / "snapshot.tar"
    run(
        ["git", "archive", "--format=tar", "-o", str(snapshot), task["parent"]],
        cwd=local,
    )
    link = TASKS / task["id"] / "environment" / "snapshot.tar"
    link.unlink(missing_ok=True)
    try:
        os.link(snapshot, link)
    except OSError:
        shutil.copy2(snapshot, link)


def check(selection):
    problems = []
    ids = set()
    for task in selection["tasks"]:
        task_id = task["id"]
        ids.add(task_id)
        if task_id != f"{task['repo']}-{task['pr']}":
            problems.append(f"{task_id}: id is not <repo>-<pr>")
        if task["heldout"] != heldout_for(task["group"]):
            problems.append(f"{task_id}: heldout does not match the hash of its group")
        local = local_repo(selection, task["repo"])
        parents = run(
            ["git", "rev-list", "--parents", "-n", "1", task["merge"]], cwd=local
        ).split()
        if parents[1:] != [task["parent"]]:
            problems.append(f"{task_id}: parent is not the merge commit's only parent")
    for task_id, group in shared_groups(selection["tasks"]).items():
        recorded = next(t for t in selection["tasks"] if t["id"] == task_id)
        if recorded.get("group") != group:
            problems.append(f"{task_id}: group is not {group}")
    if len(ids) != len(selection["tasks"]):
        problems.append("duplicate task ids")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["build", "prepare", "check", "add"])
    parser.add_argument("ids", nargs="*", help="task ids, or REPO PR for add")
    args = parser.parse_args()
    selection = load()
    if args.command == "add":
        if len(args.ids) != 2:
            parser.error("usage: build_tasks.py add REPO PR")
        added = add_task(selection, args.ids[0], int(args.ids[1]))
        print(f"add: {added}" if added else "add: already present")
        return
    tasks = [t for t in selection["tasks"] if not args.ids or t["id"] in args.ids]
    if args.command == "check":
        problems = check(selection)
        print("\n".join(problems) or f"ok: {len(selection['tasks'])} tasks")
        sys.exit(1 if problems else 0)
    action = build_task if args.command == "build" else prepare_task
    for task in tasks:
        action(selection, task)
        print(f"{args.command}: {task['id']}")


if __name__ == "__main__":
    main()
