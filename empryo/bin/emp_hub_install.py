#!/usr/bin/env python3
"""Deferred Empryo deployment. Only the launchd worker installs or restarts."""
import argparse
import contextlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import time

ACTIVE = ("pending", "waiting idle", "installing", "restarting")
CAP_SECONDS = 1800
# The worker installs from the persistent checkout, never the development checkout.
INSTALL_CHECKOUT = ".local/share/mac-ops-install"


def state_path(home):
    return Path(home) / ".empryo-hub/install.json"


def read_state(home):
    try:
        return json.loads(state_path(home).read_text())
    except FileNotFoundError:
        return {}


def installer(checkout):
    spec = importlib.util.spec_from_file_location("hub_installer", Path(checkout) / "install_empryo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(home, state):
    # Reuse the installer's no-follow atomic writer in both source and live jobs.
    source = Path(__file__).resolve().parents[2]
    checkout = source if (source / "install_empryo.py").is_file() else Path(home) / INSTALL_CHECKOUT
    installer(checkout).atomic_write(state_path(home), json.dumps(state).encode(), 0o600)


@contextlib.contextmanager
def lock(path, blocking=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield
    finally:
        os.close(fd)


def run(argv, cwd=None, timeout=60):
    return subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, check=False)


def git(checkout, *args):
    result = run(["git", "-C", str(checkout), *args])
    if result.returncode:
        raise RuntimeError("checkout verification failed")
    return result.stdout.decode().strip()


def mark(checkout, home, old, head):
    """Called by MO-158 while it holds install.lock across the fast-forward."""
    module = installer(checkout)
    changed = git(checkout, "diff", "--name-only", old, head).splitlines()
    state = read_state(home)
    managed = module.managed_changes(Path(checkout), Path(home), changed)
    if not managed and state.get("state") not in ACTIVE:
        return {"status": "unchanged"}
    if state.get("sha") == head:
        return {"status": state["state"]}
    since = state.get("since", time.time()) if state.get("state") in ACTIVE else time.time()
    state = {"state": "pending", "sha": head, "since": since, "updated": time.time()}
    save(home, state)
    return {"status": "pending"}


def hub_status(home):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(10)
        client.connect(str(Path(home) / ".empryo-hub/hub.sock"))
        client.sendall(b'{"method":"call","tool":"emp_hub_status","arguments":{}}\n')
        with client.makefile("rb") as stream:
            reply = json.loads(stream.readline(1024 * 1024))
    if not reply.get("ok"):
        raise RuntimeError("hub status unavailable")
    return reply["result"]


def notify(reason):
    # Fixed messages only: never pass configuration or child output to a notice.
    script = 'on run argv\ndisplay notification (item 1 of argv) with title "Empryo install refused"\nend run'
    try:
        run(["/usr/bin/osascript", "-e", script, reason], timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def guard(checkout, home):
    installer(checkout).guard_live_routing(Path(checkout), Path(home))


def wait_restarted(home, old_pid, status):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            pid = status(home).get("pid")
            if type(pid) is int and pid > 0 and pid != old_pid:
                return
        except (OSError, ValueError, RuntimeError):
            pass
        time.sleep(0.2)
    raise RuntimeError("replacement hub did not become ready")


def tick(home=None, status=None, execute=None, notice=None, now=None):
    home = Path(home or Path.home())
    status, execute, notice = status or hub_status, execute or run, notice or notify
    now = time.time() if now is None else now
    checkout = home / INSTALL_CHECKOUT
    try:
        with lock(home / ".empryo-hub/install.lock", blocking=False):
            state = read_state(home)
            if state.get("state") not in ACTIVE:
                return state

            def transition(name, reason=None):
                state.update(state=name, updated=now)
                if reason:
                    state["reason"] = reason
                save(home, state)
                if name == "refused":
                    notice(reason)
                return state

            if state["state"] in ("installing", "restarting"):
                return transition("refused", "Interrupted deployment; manual inspection required")
            since = state["since"]
            if type(since) not in (int, float) or not 0 <= now - since < float("inf"):
                return transition("refused", "Invalid install wait start; no restart performed")
            if now - since < CAP_SECONDS:
                return state
            if now - since >= 2 * CAP_SECONDS:
                return transition("refused", "Install waited 30 minutes for idle after batching; no restart performed")
            transition("waiting idle")
            try:
                # empq holds this lock through pre-steps, launch and counting.
                with lock(home / "Code/coordinator/queue/queue.lock", blocking=False):
                    report = status(home)
                    if report.get("installPending") is not True or report.get("installIdle") is not True:
                        return state
                    if git(checkout, "symbolic-ref", "--short", "HEAD") != "main":
                        return transition("refused", "Install checkout is not main")
                    if git(checkout, "status", "--porcelain", "--untracked-files=all"):
                        return transition("refused", "Install checkout has local changes")
                    if git(checkout, "rev-parse", "HEAD") != state["sha"] or git(checkout, "rev-parse", "origin/main") != state["sha"]:
                        return transition("refused", "Install checkout is not the pending fast-forward")
                    old_pid = report.get("pid")
                    if type(old_pid) is not int or old_pid <= 0:
                        return transition("refused", "Hub identity unavailable; no install performed")
                    guard(checkout, home)
                    # Persist before each side effect: an interrupted worker never retries it.
                    transition("installing")
                    result = execute(["./install.sh", "empryo", "--preserve-routing"], cwd=str(checkout), timeout=600)
                    if result.returncode:
                        return transition("refused", "Empryo install failed; no restart performed")
                    guard(checkout, home)
                    report = status(home)
                    if report.get("installPending") is not True or report.get("installIdle") is not True:
                        return transition("refused", "Hub no longer safely idle; no restart performed")
                    transition("restarting")
                    result = execute(["/bin/launchctl", "kickstart", "-k", f"gui/{os.getuid()}/dev.coordinator.emp-hub"], timeout=60)
                    if result.returncode:
                        return transition("refused", "Hub restart failed; manual inspection required")
                    wait_restarted(home, old_pid, status)
                    return transition("done")
            except BlockingIOError:
                return state
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
                return transition("refused", "Deployment safety check failed; no further restart attempted")
    except BlockingIOError:
        return {}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        state = tick()
        print(json.dumps({k: state[k] for k in ("state", "sha", "reason") if k in state}))
    except (OSError, ValueError, KeyError, TypeError):
        notify("Install state unreadable; manual inspection required")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
