#!/usr/bin/python3
import argparse
import fcntl
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
PREIMAGES = {'pi-utils/src/fetch-retry.ts': '2d211b23db03a8fcb4a3732b987207a0716b765609aa36273a45fd2656001ca6', 'pi-ai/src/error/flags.ts': '8baf58cd26dfb8ccd08f67975d84bfe6881cf0fbe8fd75db537d4ad49fec0fc2', 'pi-ai/src/providers/cursor.ts': '080c421a3db8e0c4170451b4b243060fe5713a001ff6423f1296e1a3298f8326', 'pi-coding-agent/src/session/turn-recovery.ts': '421f5ffdf2f68e8a716b851441e8a6ff3dd71a25c1d315b45daa4951c6b72103', 'pi-coding-agent/src/session/agent-session.ts': 'eab184756923671f778ff5e9fe68102d686f0b549198c7916a7473e4dc9ebc6a', 'pi-ai/src/types.ts': '78ec43f55e1e02a567cdee70e5450cc0293ad24e53d0701d47aa34bfbe6c15e9', 'pi-ai/src/providers/register-builtins.ts': '86411e55da816e2d5e52759e219c9b644d42128b38fcbff3497579bf5906d355', 'pi-coding-agent/src/cli/profile-alias.ts': 'd409a07d6fe29ee9bf1ab6b7f5256f7bf658bf9d818d8460f6b1f3c33512bcef', 'pi-coding-agent/src/exec/bash-executor.ts': '68966691b2b776e653fd78358c7fd92a84e0ddd716d6b4e21abe82190d15e642'}
POSTIMAGES = {'pi-utils/src/fetch-retry.ts': 'e7320b280e5e2f8b82302d695ba582c5a05e7852da98a6e4478cd834fc7ff573', 'pi-ai/src/error/flags.ts': '57ba38d51ccbc514f51d599fd1fa6396ebeeac41e09384ec0331a4c405825191', 'pi-ai/src/providers/cursor.ts': '10c53b04ea13241f5cf5e242c449d4b96e91a260f1b907f65a0206deb7720961', 'pi-coding-agent/src/session/turn-recovery.ts': '621123a9f950a686409f867bf4da9540de8298cf98d4aac4d28422920a432a29', 'pi-coding-agent/src/session/agent-session.ts': '3e7335195af7b7de8131571e1870e53ef0c87d95f61b7ad0abe754a3bd37e4a7', 'pi-ai/src/types.ts': '4abc74254fea91d19f34ff27fd25af6566b8e1b63176faf583833232b984c9f9', 'pi-ai/src/providers/register-builtins.ts': '0a16f65e189611240740bad796b9d9b01e8a2a09328c77e0732b68cc1fbd19db', 'pi-coding-agent/src/cli/profile-alias.ts': '878d953d1b25f5771a79e270ab9fdbda7829e9489fde9b153df50f3137aa899a', 'pi-coding-agent/src/exec/bash-executor.ts': '9ec1ee83cef33c8cff36dff28cbe2b900e6796c9990bf9546814c3787c1fb7da'}

BUNDLE_OWNER = "mac-ops/35.cursor-retry.v1"

def validate_runtime_path(runtime, managed_launcher):
    pending = list(runtime.absolute().parts[1:])
    cursor = Path(runtime.anchor)
    links = 0
    while pending:
        part = pending.pop(0)
        if part == "..":
            cursor = cursor.parent
            continue
        if part == ".":
            continue
        cursor /= part
        if cursor == managed_launcher:
            raise ValueError("The vendor runtime must not pass through the managed input gate")
        if cursor.is_symlink():
            links += 1
            if links > 40:
                raise ValueError("Vendor runtime symlink chain is cyclic or too deep")
            target = Path(os.readlink(cursor))
            target = target if target.is_absolute() else cursor.parent / target
            pending = list(target.parts[1:]) + pending
            cursor = Path(target.anchor)
    if managed_launcher.is_file() and not managed_launcher.is_symlink() and cursor.samefile(managed_launcher):
        raise ValueError("The vendor runtime must not be the managed input gate")



def tree_stamp(root):
    rows = []
    for path in [root, *sorted(root.rglob("*"))]:
        info = path.lstat()
        link = os.readlink(path) if path.is_symlink() else None
        if link is not None and not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Dependency symlink escapes snapshot: {path}")
        rows.append((str(path.relative_to(root)), info.st_ino, info.st_size,
                     info.st_mtime_ns, info.st_ctime_ns, info.st_mode, link))
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def upstream_identity(source, runtime):
    verify(source, PREIMAGES)
    version = json.loads((source / "@oh-my-pi/pi-coding-agent/package.json").read_text())["version"]
    if version != "18.13.3":
        raise ValueError(f"Unsupported omp source version: {version}")
    return {"patch": digest(PATCH), "runtime": digest(runtime), "tree": tree_stamp(source)}


def apply_patch(modules):
    verify(modules, PREIMAGES)
    result = subprocess.run(
        ["/usr/bin/patch", "-p1", "-F0", "--forward", "--batch", "--no-backup-if-mismatch", "-r", "-"],
        input=PATCH.read_text(), cwd=modules / "@oh-my-pi", text=True, capture_output=True,
    )
    if result.returncode:
        raise ValueError("Patch rejected upstream source:\n" + result.stdout + result.stderr)
    verify(modules, POSTIMAGES)


def prepare_generation(root, source, runtime, managed_launcher):
    with (root / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        identity = upstream_identity(source, runtime)
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        target = root / "generations" / key
        if target.exists():
            manifest = json.loads((target / "manifest.json").read_text())
            if manifest["upstream"] != identity or manifest["tree"] != tree_stamp(target / "node_modules"):
                raise ValueError(f"Damaged retry generation: {target}")
            verify(target / "node_modules", POSTIMAGES)
            if digest(target / "runtime") != identity["runtime"]:
                raise ValueError("Retry runtime changed")
            if digest(target / "omp") != manifest["launcher"]:
                raise ValueError("Retry generation launcher changed")
        else:
            version = subprocess.run(
                [str(runtime), "--version"], env=dict(os.environ, BUN_BE_BUN=""),
                check=True, text=True, capture_output=True,
            ).stdout.strip()
            if version != "omp/18.13.3":
                raise ValueError(f"Unsupported omp runtime version: {version}")
            target.parent.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=target.parent, prefix=".stage-") as temporary:
                stage = Path(temporary) / "copy"
                stage.mkdir()
                modules = stage / "node_modules"
                subprocess.run(["/bin/cp", "-cR", str(source.resolve(strict=True)), str(modules)], check=True)
                shutil.copy2(runtime, stage / "runtime")
                if upstream_identity(source, runtime) != identity or digest(stage / "runtime") != identity["runtime"]:
                    raise ValueError("Upstream changed while copying; retry after its update completes")
                tree_stamp(modules)
                apply_patch(modules)
                bun = subprocess.run(
                    [str(stage / "runtime"), "--version"], env=dict(os.environ, BUN_BE_BUN="1"),
                    check=True, text=True, capture_output=True,
                ).stdout.strip()
                if bun != "1.4.4":
                    raise ValueError(f"Expected embedded Bun 1.4.4, got {bun}")
                launch = stage / "omp"
                launch.write_text(
                    '#!/bin/sh\ndir=${0%/*}\nMAC_OPS_OMP_LAUNCHER='
                    + shlex.quote(str(managed_launcher))
                    + ' BUN_BE_BUN=1 exec "$dir/runtime" '
                    '"$dir/node_modules/@oh-my-pi/pi-coding-agent/src/cli.ts" "$@"\n'
                )
                launch.chmod(0o700)
                (stage / "manifest.json").write_text(json.dumps({
                    "upstream": identity, "tree": tree_stamp(modules), "launcher": digest(launch),
                }, indent=2) + "\n")
                stage.rename(target)
            print(f"omp Cursor retry: prepared {key}", file=sys.stderr)
        return target


def install_bundle(root, source, runtime):
    managed_launcher = root.parent / "omp"
    validate_runtime_path(runtime, managed_launcher)
    if runtime.name != "omp":
        raise ValueError("The vendor runtime must be named omp for upstream update target resolution")
    if source.resolve() == root.resolve() or source.resolve() in root.resolve().parents:
        raise ValueError("The retry bundle must be outside the vendor source tree")
    identity = {"owner": BUNDLE_OWNER, "source": str(source.absolute()), "runtime": str(runtime.absolute()),
                "helper": digest(Path(__file__)), "patch": digest(PATCH), "launcher": str(managed_launcher)}
    if root.exists():
        if json.loads((root / "config.json").read_text()) != identity:
            raise ValueError(f"Retry bundle differs: {root}; restore the recorded configuration before installing")
        if digest(root / "omp_cursor_retry.py") != identity["helper"] or digest(root / "omp_cursor_retry.patch") != identity["patch"]:
            raise ValueError("Installed retry helper or patch changed")
        prepare_generation(root, source, runtime, managed_launcher)
        return root / "launch"
    with tempfile.TemporaryDirectory(dir=root.parent, prefix=".omp-retry-install-") as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir()
        shutil.copy2(__file__, stage / "omp_cursor_retry.py")
        shutil.copy2(PATCH, stage / "omp_cursor_retry.patch")
        (stage / "config.json").write_text(json.dumps(identity, indent=2) + "\n")
        prepare_generation(stage, source, runtime, managed_launcher)
        launch = stage / "launch"
        launch.write_text("#!/bin/sh\nexec /usr/bin/python3 "
                          + shlex.quote(str(root / "omp_cursor_retry.py"))
                          + " run --root " + shlex.quote(str(root)) + ' -- "$@"\n')
        launch.chmod(0o700)
        stage.rename(root)
    return root / "launch"


def run_installed(root, args):
    config = json.loads((root / "config.json").read_text())
    if config["owner"] != BUNDLE_OWNER or config["helper"] != digest(Path(__file__)) or config["patch"] != digest(PATCH):
        raise ValueError("Installed retry bundle changed")
    source, runtime = Path(config["source"]), Path(config["runtime"])
    managed_launcher = Path(config["launcher"])
    validate_runtime_path(runtime, managed_launcher)
    command_args = list(args)
    while command_args:
        if command_args[0] == "--profile" and len(command_args) > 1:
            command_args = command_args[2:]
        elif command_args[0].startswith("--profile="):
            command_args = command_args[1:]
        else:
            break
    if command_args and command_args[0] == "update":
        os.environ.pop("MAC_OPS_OMP_READY_FD", None)
        env = dict(os.environ)
        env.pop("BUN_BE_BUN", None)
        env["PATH"] = str(runtime.parent) + os.pathsep + env.get("PATH", "")
        os.execve(str(runtime), [str(runtime), *args], env)
    generation = prepare_generation(root, source, runtime, managed_launcher)
    executable = str(generation / "omp")
    ready_fd = os.environ.pop("MAC_OPS_OMP_READY_FD", None)
    if ready_fd is not None:
        os.write(int(ready_fd), b"1")
        os.close(int(ready_fd))
    os.execv(executable, [executable, *args])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(modules, expected):
    for name, wanted in expected.items():
        path = modules / "@oh-my-pi" / name
        if digest(path) != wanted:
            raise ValueError(f"Source drift or damaged copy: {path}. Refresh the patch and recorded hashes.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        parser = argparse.ArgumentParser(description="Run an opted-in, checked Cursor retry installation")
        parser.add_argument("command")
        parser.add_argument("--root", type=Path, required=True)
        options, rest = parser.parse_known_args()
        run_installed(options.root, rest[1:] if rest[:1] == ["--"] else rest)
        return
    parser = argparse.ArgumentParser(description="Prepare a task-local omp Cursor retry proof copy")
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
