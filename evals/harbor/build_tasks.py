#!/usr/bin/env python3
"""Build Harbor task folders from evals/harbor/sets/ladder.json.

build    writes tasks/<id>/ (instruction, Dockerfile, tests, solution, task.toml)
prepare  writes the parent-commit snapshot into .cache/<id>/ and links it into
         the task's build context; the snapshot never holds a credential and is
         gitignored.
check    verifies ids, merge parents and the frozen held-out slice.
"""

import argparse
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
DROPPED_SECTIONS = {"gate", "finish", "ci", "rollback", "source", "blocked by", "type"}

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
cd /app || exit 1
cp -R "$(dirname "$0")/files/." /app/

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


def heldout_for(task_id):
    digest = hashlib.sha256(task_id.encode()).hexdigest()
    return int(digest, 16) % HELDOUT_MODULUS == 0


def ticket_text(github, number):
    issue = json.loads(run(["gh", "api", f"repos/{github}/issues/{number}"]))
    sections = re.split(r"(?m)^(?=## )", issue["body"] or "")
    kept = []
    for section in sections:
        heading = re.match(r"## (.+)", section)
        if heading and heading.group(1).strip().lower() in DROPPED_SECTIONS:
            continue
        if not heading:
            section = "\n".join(
                line
                for line in section.splitlines()
                if not re.match(r"(?i)^(type|source)\b", line)
            )
        kept.append(section.strip())
    body = "\n\n".join(part for part in kept if part)
    return f"# {issue['title']}\n\n{body}\n"


def build_task(selection, task):
    repo = selection["repos"][task["repo"]]
    local = local_repo(selection, task["repo"])
    folder = TASKS / task["id"]
    if folder.exists():
        shutil.rmtree(folder)
    for sub in ("environment", "tests/files", "solution"):
        (folder / sub).mkdir(parents=True)

    (folder / "instruction.md").write_text(
        ticket_text(repo["github"], task["ticket"])
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
        if task["heldout"] != heldout_for(task_id):
            problems.append(f"{task_id}: heldout does not match the stable hash")
        local = local_repo(selection, task["repo"])
        parents = run(
            ["git", "rev-list", "--parents", "-n", "1", task["merge"]], cwd=local
        ).split()
        if parents[1:] != [task["parent"]]:
            problems.append(f"{task_id}: parent is not the merge commit's only parent")
    if len(ids) != len(selection["tasks"]):
        problems.append("duplicate task ids")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["build", "prepare", "check"])
    parser.add_argument("ids", nargs="*", help="task ids; default is every task")
    args = parser.parse_args()
    selection = load()
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
