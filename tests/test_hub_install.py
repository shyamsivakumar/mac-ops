"""MO-170: real git + fake socket hub, installer and launchctl. Never run emp-hub."""
import ast
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WORKER = load(ROOT / "empryo/bin/emp_hub_install.py", "hub_install")
INSTALLER = load(ROOT / "install_empryo.py", "installer")


def functions(path, names, namespace):
    tree = ast.parse(path.read_text())
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if len(body) != len(names):
        raise AssertionError("missing functions")
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class IdleInstallTests(unittest.TestCase):
    def setUp(self):
        # /tmp resolves the macOS /var symlink before the no-follow installer sees it.
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.checkout = self.home / "Code/mac-ops"
        self.checkout.mkdir(parents=True)
        shutil.copyfile(ROOT / "install_empryo.py", self.checkout / "install_empryo.py")
        self.routing = {"types": {"standard": {"modelSelection": {"instanceId": "fake", "model": "one"}}}}
        self.config = {"modelFallback": {"one": ["two"]}}
        self.write(self.checkout / "empryo/hub/routing.json", self.routing)
        self.write(self.checkout / "empryo/config/routing-config.json", self.config)
        self.write(self.home / ".empryo-hub/routing.json", self.routing)
        self.write(self.home / ".empryo/config.json", self.config)
        (self.checkout / ".gitignore").write_text("__pycache__/\n")
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Proof")
        self.git("config", "user.email", "proof@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.sha = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.sha)
        # The worker installs from the persistent checkout; the live checkout only fast-forwards.
        self.install = self.home / ".local/share/mac-ops-install"
        subprocess.run(["git", "clone", str(self.checkout), str(self.install)], check=True, capture_output=True)
        self.notices = []
        self.calls = []
        self.idle = True
        self.pid = 100
        self.install_code = 0
        self.restart_code = 0
        self.proof = self.home / "fake-command.py"
        self.proof.write_text('import json,sys\nfrom pathlib import Path\np=Path(sys.argv[1])\nwith p.open("a") as f: f.write(json.dumps(sys.argv[3:])+"\\n")\nsys.exit(int(sys.argv[2]))\n')
        self.log = self.home / "commands.jsonl"
        self.socket_path = self.home / ".empryo-hub/hub.sock"
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.socket_path))
        self.server.listen()
        self.server.settimeout(0.1)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        WORKER.save(self.home, {"state": "pending", "sha": self.sha, "since": 100})

    def close_server(self):
        self.stop.set()
        self.thread.join(timeout=2)
        self.server.close()

    def serve(self):
        while not self.stop.is_set():
            try:
                client, _ = self.server.accept()
            except socket.timeout:
                continue
            with client, client.makefile("rb") as stream:
                request = json.loads(stream.readline())
                valid = request == {"method": "call", "tool": "emp_hub_status", "arguments": {}}
                reply = {"ok": valid, "result": {"installPending": True, "installIdle": self.idle, "pid": self.pid}}
                client.sendall((json.dumps(reply) + "\n").encode())

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.checkout), *args], stderr=subprocess.PIPE).decode().strip()

    def execute(self, argv, **kwargs):
        self.calls.append(argv)
        state = WORKER.read_state(self.home)["state"]
        is_install = argv[0] == "./install.sh"
        self.assertEqual(state, "installing" if is_install else "restarting")
        code = self.install_code if is_install else self.restart_code
        if not is_install and code == 0:
            self.pid += 1
        return subprocess.run([sys.executable, str(self.proof), str(self.log), str(code), *argv], capture_output=True, check=False)

    def tick(self, now=101, **kwargs):
        return WORKER.tick(self.home, execute=self.execute, notice=self.notices.append, now=now, **kwargs)

    def test_idle_installs_and_restarts_exactly_once(self):
        self.assertEqual(self.tick()["state"], "done")
        self.assertEqual(self.tick()["state"], "done")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0], ["./install.sh", "empryo", "--preserve-routing"])
        self.assertEqual(self.calls[1], ["/bin/launchctl", "kickstart", "-k", f"gui/{os.getuid()}/dev.coordinator.emp-hub"])
        self.assertEqual(len(self.log.read_text().splitlines()), 2)
        self.assertFalse(self.notices)

    def test_restart_readiness_failure_is_terminal(self):
        with patch.object(WORKER, "wait_restarted", side_effect=RuntimeError("fake not ready")):
            self.assertEqual(self.tick()["state"], "refused")
        self.tick()
        self.assertEqual(len(self.calls), 2)

    def test_running_thread_delays_install(self):
        self.idle = False
        self.assertEqual(self.tick()["state"], "waiting idle")
        self.assertFalse(self.calls)
        self.idle = True
        self.assertEqual(self.tick()["state"], "done")

    def test_queue_start_lock_delays_install(self):
        with WORKER.lock(self.home / "Code/coordinator/queue/queue.lock"):
            self.assertEqual(self.tick()["state"], "waiting idle")
            self.assertFalse(self.calls)
        self.assertEqual(self.tick()["state"], "done")

    def test_worker_lock_prevents_duplicate_work(self):
        with WORKER.lock(self.home / ".empryo-hub/install.lock"):
            self.assertEqual(self.tick(), {})
        self.assertFalse(self.calls)

    def test_primary_difference_refuses_once_without_values(self):
        self.routing["types"]["standard"]["modelSelection"]["model"] = "PRIVATE-PRIMARY"
        self.write(self.home / ".empryo-hub/routing.json", self.routing)
        self.assertEqual(self.tick()["state"], "refused")
        self.tick()
        self.assertEqual(len(self.notices), 1)
        self.assertNotIn("PRIVATE-PRIMARY", str(self.notices) + WORKER.state_path(self.home).read_text())
        self.assertFalse(self.calls)

    def test_fallback_difference_refuses(self):
        self.write(self.home / ".empryo/config.json", {"modelFallback": {"one": ["PRIVATE-FALLBACK"]}})
        self.assertEqual(self.tick()["state"], "refused")
        self.assertFalse(self.calls)
        self.assertEqual(len(self.notices), 1)
        self.assertNotIn("PRIVATE-FALLBACK", str(self.notices))

    def test_fallback_guard_compares_actual_recursive_overlay(self):
        # Local-only fallback entries survive the installer's merge and are safe.
        self.write(self.home / ".empryo/config.json", {"modelFallback": {"one": ["two"], "local": []}})
        self.assertEqual(self.tick()["state"], "done")

    def test_failed_install_never_restarts_or_retries(self):
        self.install_code = 1
        self.assertEqual(self.tick()["state"], "refused")
        self.tick()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.notices), 1)

    def test_restart_failure_never_retries(self):
        self.restart_code = 1
        self.assertEqual(self.tick()["state"], "refused")
        self.tick()
        self.assertEqual(len(self.calls), 2)

    def test_install_timeout_does_not_restart(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired("fake install", 600)
        result = WORKER.tick(self.home, execute=timeout, notice=self.notices.append, now=101)
        self.assertEqual(result["state"], "refused")
        self.assertFalse(self.calls)

    def test_thirty_minute_cap_notifies_once_and_never_restarts(self):
        self.idle = False
        self.assertEqual(self.tick(now=1899)["state"], "waiting idle")
        self.assertEqual(self.tick(now=1900)["state"], "refused")
        self.tick(now=1901)
        self.assertEqual(len(self.notices), 1)
        self.assertFalse(self.calls)

    def test_interrupted_side_effect_is_never_retried(self):
        for state in ("installing", "restarting"):
            WORKER.save(self.home, {"state": state, "sha": self.sha, "since": 100})
            self.assertEqual(self.tick()["state"], "refused")
        self.assertFalse(self.calls)

    def test_old_hub_without_idle_contract_cannot_trigger_install(self):
        self.assertEqual(self.tick(status=lambda home: {"pid": 1})["state"], "waiting idle")
        self.assertFalse(self.calls)

    def test_dirty_checkout_refuses(self):
        (self.install / "unexpected").write_text("dirty")
        self.assertEqual(self.tick()["state"], "refused")
        self.assertFalse(self.calls)

    def test_new_running_turn_after_install_prevents_restart(self):
        def execute(argv, **kwargs):
            result = self.execute(argv, **kwargs)
            self.idle = False
            return result
        result = WORKER.tick(self.home, execute=execute, notice=self.notices.append, now=101)
        self.assertEqual(result["state"], "refused")
        self.assertEqual(len(self.calls), 1)

    def test_post_merge_fast_forward_marks_under_worker_lock(self):
        post = load(ROOT / "empryo/bin/emp_post_merge.py", "post_for_install")
        worker_source = self.checkout / "empryo/bin/emp_hub_install.py"
        worker_source.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "empryo/bin/emp_hub_install.py", worker_source)
        self.git("add", ".")
        self.git("commit", "-qm", "worker available")
        remote = self.home / "remote.git"
        subprocess.run(["git", "clone", "--bare", str(self.checkout), str(remote)], check=True, capture_output=True)
        other = self.home / "other"
        subprocess.run(["git", "clone", "-b", "main", str(remote), str(other)], check=True, capture_output=True)
        def other_git(*args):
            return subprocess.run(["git", "-C", str(other), *args], check=True, capture_output=True)
        other_git("config", "user.name", "Proof")
        other_git("config", "user.email", "proof@example.invalid")
        routing = other / "empryo/hub/routing.json"
        routing.write_text(routing.read_text() + "\n")
        other_git("commit", "-am", "managed merge")
        other_git("push", str(remote), "main")
        self.git("remote", "add", "origin", "https://github.com/shyamsivakumar/mac-ops.git")
        self.git("config", "url." + str(remote) + ".insteadOf", "https://github.com/shyamsivakumar/mac-ops.git")
        config = self.home / ".empryo/post-merge.json"
        self.write(config, {"shyamsivakumar/mac-ops": {"checkout": "mac-ops", "deferEmpryo": True}})
        original = post._git
        locked = []
        def git(checkout, *args, **kwargs):
            if args[0] == "merge":
                locked.append(self.tick())
            return original(checkout, *args, **kwargs)
        with patch.object(post, "_git", side_effect=git):
            result = post.post_merge("shyamsivakumar/mac-ops", "main", self.home)
        self.assertEqual(locked, [{}])
        self.assertEqual(result["fastForward"]["status"], "ok")
        self.assertEqual(result["hubInstall"]["status"], "pending")
        self.assertEqual(WORKER.read_state(self.home)["sha"], self.git("rev-parse", "HEAD"))
        self.assertEqual(WORKER.read_state(self.home)["since"], 100)
        self.assertFalse(self.calls)

    def test_merge_admission_after_final_idle_check_is_refused(self):
        thread = {"threadId": "merge", "status": "completed"}
        runtime = {}
        namespace = {"contextlib": contextlib, "threading": threading, "LOCK": threading.RLock(),
                     "LIVE": ("running", "waiting", "queued"), "HubError": RuntimeError,
                     "runtime_of": lambda tid: runtime,
                     "install_pending": lambda: WORKER.read_state(self.home)["state"] in WORKER.ACTIVE}
        admit = functions(ROOT / "empryo/bin/emp-hub", {"merge_guard"}, namespace)["merge_guard"]
        attempted = []
        def execute(argv, **kwargs):
            if argv[0] == "/bin/launchctl":
                attempted.append(True)
                with self.assertRaisesRegex(RuntimeError, "install pending"):
                    with admit(thread):
                        self.fail("merge admitted between final idle check and kickstart")
                self.assertFalse(runtime.get("merging"))
            return self.execute(argv, **kwargs)
        result = WORKER.tick(self.home, execute=execute, notice=self.notices.append, now=101)
        self.assertEqual(result["state"], "done")
        self.assertEqual(attempted, [True])
        with admit(thread):
            self.assertTrue(runtime["merging"])
        self.assertFalse(runtime.get("merging"))

    def test_wrong_head_refuses(self):
        WORKER.save(self.home, {"state": "pending", "sha": "0" * 40, "since": 100})
        self.assertEqual(self.tick()["state"], "refused")
        self.assertFalse(self.calls)

    def test_mark_detects_managed_files_and_coalesces_without_resetting_cap(self):
        old = self.sha
        path = self.checkout / "empryo/hub/routing.json"
        path.write_text(path.read_text() + "\n")
        self.git("add", ".")
        self.git("commit", "-qm", "managed")
        head = self.git("rev-parse", "HEAD")
        self.assertEqual(WORKER.mark(self.checkout, self.home, old, head)["status"], "pending")
        self.assertEqual(WORKER.read_state(self.home)["since"], 100)
        (self.checkout / "README.md").write_text("unrelated")
        self.git("add", ".")
        self.git("commit", "-qm", "docs")
        latest = self.git("rev-parse", "HEAD")
        WORKER.mark(self.checkout, self.home, head, latest)
        self.assertEqual(WORKER.read_state(self.home)["sha"], latest)
        self.assertEqual(WORKER.read_state(self.home)["since"], 100)

    def test_unmanaged_merge_does_not_arm_terminal_state(self):
        WORKER.save(self.home, {"state": "done", "sha": self.sha, "since": 100})
        (self.checkout / "README.md").write_text("unrelated")
        self.git("add", ".")
        self.git("commit", "-qm", "docs")
        self.assertEqual(WORKER.mark(self.checkout, self.home, self.sha, self.git("rev-parse", "HEAD"))["status"], "unchanged")
        self.assertEqual(WORKER.read_state(self.home)["state"], "done")


class WiringTests(unittest.TestCase):
    def test_installer_owns_detection_and_job_rendering(self):
        self.assertTrue(INSTALLER.managed_changes(ROOT, Path("/fake"), ["empryo/mods/cockpit/deleted.js"]))
        self.assertTrue(INSTALLER.managed_changes(ROOT, Path("/fake"), ["install_empryo.py"]))
        self.assertFalse(INSTALLER.managed_changes(ROOT, Path("/fake"), ["README.md"]))
        jobs = {target.name: plistlib.loads(data) for data, target in INSTALLER.render_plists(ROOT, Path("/fake"))}
        job = jobs["dev.coordinator.emp-hub-install.plist"]
        self.assertEqual(job["StartInterval"], 60)
        self.assertNotIn("KeepAlive", job)
        self.assertEqual(job["ProgramArguments"], ["/usr/bin/python3", "/fake/.local/lib/empryo/emp_hub_install.py"])
        planned = {src.name for src, _, _ in INSTALLER.plan(ROOT, Path("/fake"))}
        self.assertIn("emp_hub_install.py", planned)

    def test_hub_and_queue_gate_fail_closed_and_release_terminal_states(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "install.json"
            for source in ("emp-hub", "empq"):
                namespace = {"HUB_DIR": folder, "json": json, "os": os}
                gate = functions(ROOT / "empryo/bin" / source, {"install_pending"}, namespace)["install_pending"]
                with patch("os.path.expanduser", return_value=str(marker)):
                    for state in WORKER.ACTIVE:
                        marker.write_text(json.dumps({"state": state}))
                        self.assertTrue(gate())
                    for state in ("done", "refused"):
                        marker.write_text(json.dumps({"state": state}))
                        self.assertFalse(gate())
                    marker.write_text("broken")
                    self.assertTrue(gate())
                    marker.unlink()
                    self.assertFalse(gate())

    def test_running_turn_contract_counts_starting_and_waiting_not_pending(self):
        threads = {"run": {"threadId": "run", "status": "running"}, "queue": {"threadId": "queue", "status": "queued", "pendingTurn": {}}, "start": {"threadId": "start", "status": "idle"}}
        # Pending turns are nonempty in the actual store.
        threads["queue"]["pendingTurn"] = {"message": "queued"}
        namespace = {"THREADS": SimpleNamespace(data=threads), "RUNTIME": {"start": {"starting": True}}, "LIVE": ("running", "waiting", "queued")}
        running = functions(ROOT / "empryo/bin/emp-hub", {"running_turns"}, namespace)["running_turns"]
        self.assertEqual({t["threadId"] for t in running()}, {"run", "start"})

    def test_queue_drain_does_not_consume_attempts_while_pending(self):
        messages = []
        namespace = {"install_pending": lambda: True, "log": messages.append}
        functions(ROOT / "empryo/bin/empq", {"drain"}, namespace)["drain"]()
        self.assertEqual(len(messages), 1)

    def test_start_turn_persists_pending_instead_of_starting_an_engine(self):
        thread = {"threadId": "t", "status": "idle", "runCount": 0}
        rt = {}
        def set_status(thread, status):
            thread["status"] = status
        namespace = {"runtime_of": lambda tid: rt, "require_unheld": lambda thread: None,
                     "LOCK": threading.RLock(), "HubError": RuntimeError, "LIVE": ("running", "waiting", "queued"),
                     "DRAINING": {"requested": False}, "install_pending": lambda: True,
                     "set_status": set_status, "log": lambda message: None}
        start = functions(ROOT / "empryo/bin/emp-hub", {"start_turn"}, namespace)["start_turn"]
        start(thread, "hold this")
        self.assertEqual(thread["status"], "queued")
        self.assertEqual(thread["pendingTurn"]["message"], "hold this")
        self.assertFalse(rt.get("starting"))


if __name__ == "__main__":
    unittest.main()
