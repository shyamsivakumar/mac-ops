#!/usr/bin/python3
"""Prepare a task-local omp Cursor retry proof copy. Never install a launcher."""
import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PATCH = Path(__file__).with_suffix(".patch")
PREIMAGES = {'pi-utils/src/fetch-retry.ts': '2d211b23db03a8fcb4a3732b987207a0716b765609aa36273a45fd2656001ca6', 'pi-ai/src/error/flags.ts': '8baf58cd26dfb8ccd08f67975d84bfe6881cf0fbe8fd75db537d4ad49fec0fc2', 'pi-ai/src/providers/cursor.ts': '080c421a3db8e0c4170451b4b243060fe5713a001ff6423f1296e1a3298f8326', 'pi-coding-agent/src/session/turn-recovery.ts': '421f5ffdf2f68e8a716b851441e8a6ff3dd71a25c1d315b45daa4951c6b72103', 'pi-coding-agent/src/session/agent-session.ts': 'eab184756923671f778ff5e9fe68102d686f0b549198c7916a7473e4dc9ebc6a', 'pi-coding-agent/src/exec/non-interactive-env.ts': '4e55d4eae39be35d00b1489e5ace48590dc622d9c5958ab966cf0b14be57593e', 'pi-ai/src/types.ts': '78ec43f55e1e02a567cdee70e5450cc0293ad24e53d0701d47aa34bfbe6c15e9', 'pi-ai/src/providers/register-builtins.ts': '86411e55da816e2d5e52759e219c9b644d42128b38fcbff3497579bf5906d355'}
POSTIMAGES = {'pi-utils/src/fetch-retry.ts': 'e7320b280e5e2f8b82302d695ba582c5a05e7852da98a6e4478cd834fc7ff573', 'pi-ai/src/error/flags.ts': '57ba38d51ccbc514f51d599fd1fa6396ebeeac41e09384ec0331a4c405825191', 'pi-ai/src/providers/cursor.ts': '10c53b04ea13241f5cf5e242c449d4b96e91a260f1b907f65a0206deb7720961', 'pi-coding-agent/src/session/turn-recovery.ts': '621123a9f950a686409f867bf4da9540de8298cf98d4aac4d28422920a432a29', 'pi-coding-agent/src/session/agent-session.ts': '3e7335195af7b7de8131571e1870e53ef0c87d95f61b7ad0abe754a3bd37e4a7', 'pi-coding-agent/src/exec/non-interactive-env.ts': 'b9a64e9660212613bd66442a1cff8c2d8598717ed39d0524a5d896f37017742b', 'pi-ai/src/types.ts': '4abc74254fea91d19f34ff27fd25af6566b8e1b63176faf583833232b984c9f9', 'pi-ai/src/providers/register-builtins.ts': '0a16f65e189611240740bad796b9d9b01e8a2a09328c77e0732b68cc1fbd19db'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(modules, expected):
    for name, wanted in expected.items():
        path = modules / "@oh-my-pi" / name
        if digest(path) != wanted:
            raise ValueError(f"Source drift or damaged copy: {path}. Refresh the patch and recorded hashes.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "apply"])
    parser.add_argument("--source", type=Path, default=Path.home() / ".bun/install/global/node_modules")
    parser.add_argument("--omp", type=Path, default=Path.home() / ".bun/bin/omp")
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    verify(source, PREIMAGES)
    if args.command == "check":
        print("Exact upstream preimages match")
        return
    if args.root is None:
        raise ValueError("apply requires --root inside this task's TMPDIR")
    root = args.root.resolve()
    task_tmp = Path(os.environ["TMPDIR"]).resolve()
    if root == task_tmp or task_tmp not in root.parents:
        raise ValueError("Refusing to write outside a subdirectory of this task's TMPDIR")
    identity = {"patch": digest(PATCH), "runtime": digest(args.omp), "files": POSTIMAGES}
    if root.exists():
        if json.loads((root / "manifest.json").read_text()) != identity:
            raise ValueError(f"Existing proof copy differs: {root}. Choose a new --root.")
        verify(root / "node_modules", POSTIMAGES)
        if digest(root / "runtime") != identity["runtime"]:
            raise ValueError("Task-local runtime has changed")
        print(f"unchanged {root}")
        return
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root.parent, prefix=".omp-cursor-proof-") as temporary:
        staging = Path(temporary) / "copy"
        modules = staging / "node_modules"
        modules.mkdir(parents=True)
        for entry in source.iterdir():
            if entry.name != "@oh-my-pi":
                (modules / entry.name).symlink_to(entry)
        subprocess.run(["/bin/cp", "-cR", str(source / "@oh-my-pi"), str(modules / "@oh-my-pi")], check=True)
        verify(modules, PREIMAGES)
        result = subprocess.run(
            ["/usr/bin/patch", "-p1", "-F0", "--forward", "--batch", "--no-backup-if-mismatch", "-r", "-"],
            input=PATCH.read_text(), cwd=modules / "@oh-my-pi", text=True, capture_output=True,
        )
        if result.returncode:
            raise ValueError("Patch rejected upstream source:\n" + result.stdout + result.stderr)
        verify(modules, POSTIMAGES)
        shutil.copy2(args.omp, staging / "runtime")
        runtime = subprocess.run(
            [str(staging / "runtime"), "--version"], env=dict(os.environ, BUN_BE_BUN="1"),
            check=True, text=True, capture_output=True,
        ).stdout.strip()
        if runtime != "1.4.4":
            raise ValueError(f"Expected embedded Bun 1.4.4, got {runtime}")
        launcher = staging / "omp"
        launcher.write_text(
            "#!/bin/sh\nBUN_BE_BUN=1 exec " + shlex.quote(str(root / "runtime")) + " "
            + shlex.quote(str(root / "node_modules/@oh-my-pi/pi-coding-agent/src/cli.ts")) + ' "$@"\n'
        )
        launcher.chmod(0o755)
        (staging / "manifest.json").write_text(json.dumps(identity, indent=2) + "\n")
        staging.rename(root)
    print(f"applied {root}; task-local Bun {runtime}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"omp_cursor_retry: {error}", file=sys.stderr)
        sys.exit(2)
