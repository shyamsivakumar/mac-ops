import os
import subprocess
import sys
import tempfile
from pathlib import Path

OVERNIGHT = Path(__file__).resolve().parents[2] / "coordinator" / "overnight"
CODE = "/Users/shyamsivakumar/Code/"
REPO = "fixture/repo"

CHILD = """
import os, sys
sys.path.insert(0, {overnight!r})
import lane_driver as lane
lane.PATHS = {{{repo!r}: {name!r}}}
lane.LANE_REPOS = [{repo!r}]
lane.CFG = {{{repo!r}: {{"key": "FIX"}}}}
lane.DRY = False
step = sys.argv[1]
if step == "close-then-exit":
    lane.run = lambda cmd, timeout=150: print("ticket closed", flush=True) or "closed"
    def exit_before_fast_forward(repo):
        print("process exits before the fast-forward", flush=True)
        os._exit(0)
    lane.fast_forward_main = exit_before_fast_forward
    lane.after_merge({repo!r}, 20, "a" * 40, "10", {{"threadId": "gate"}})
else:
    lane.drift_ff({{}})
"""


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def child(step, name):
    code = CHILD.format(overnight=str(OVERNIGHT), repo=REPO, name=name)
    done = subprocess.run(
        [sys.executable, "-c", code, step], check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


with tempfile.TemporaryDirectory() as scratch:
    root = Path(scratch)
    origin, work, local = root / "origin.git", root / "work", root / "local"
    git("init", "--bare", "-b", "main", str(origin), cwd=root)
    git("clone", str(origin), str(work), cwd=root)
    git(
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "--allow-empty",
        "-m",
        "one",
        cwd=work,
    )
    git("push", "origin", "HEAD:main", cwd=work)
    git("clone", str(origin), str(local), cwd=root)
    git(
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "--allow-empty",
        "-m",
        "merged PR",
        cwd=work,
    )
    git("push", "origin", "HEAD:main", cwd=work)
    name = os.path.relpath(local, CODE)
    before = git("rev-parse", "main", cwd=local)
    target = git("rev-parse", "main", cwd=work)

    print("process 1:", child("close-then-exit", name))
    assert git("rev-parse", "main", cwd=local) == before, "main moved in process 1"
    print("process 2 (next pass):", child("pass", name))
    assert git("rev-parse", "main", cwd=local) == target, "main not fast-forwarded"
    print("process 3 (pass again):", repr(child("pass", name)))
    assert git("rev-parse", "main", cwd=local) == target
    print("local main", before[:8], "->", target[:8], "once; second pass no-op")
