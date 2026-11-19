import importlib.util
import json
import os
import shutil
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))

spec_loader = importlib.util.spec_from_file_location(
    "install_deny_rules", ROOT / "scripts" / "install_deny_rules.py"
)
install_deny_rules = importlib.util.module_from_spec(spec_loader)
spec_loader.loader.exec_module(install_deny_rules)

SPEC = json.loads((ROOT / "runtime/agents/deny-rules.json").read_text())
HOOK = ROOT / "runtime/agents/deny-merge-guard.py"


def git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )


def make_repo(path, branch, upstream=None, remote="origin", config=()):
    """A repo on `branch` with a committed file and a local bare `remote`."""
    bare = Path(str(path) + "-remote.git")
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "init", "-q", "-b", branch, str(path)], check=True)
    git(path, "commit", "-q", "--allow-empty", "-m", "init")
    git(path, "remote", "add", remote, str(bare))
    if upstream:
        git(path, "config", f"branch.{branch}.remote", remote)
        git(path, "config", f"branch.{branch}.merge", upstream)
    for key, value in config:
        git(path, "config", key, value)
    return path


def load(path):
    return json.loads(Path(path).read_text())


class FakeHome(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="deny-rules-test-", dir=TMP))
        self.installer = install_deny_rules.Installer(self.home)
        # A pre-existing user settings file with entries that must survive.
        claude = self.home / ".claude"
        claude.mkdir(parents=True)
        (claude / "settings.json").write_text(
            json.dumps(
                {
                    "env": {"A": "1"},
                    "permissions": {"allow": ["WebSearch", "Read(~/docs/**)"]},
                },
                indent=2,
            )
            + "\n"
        )
        for name in ("agent-openai-api", "agent-anthropic-api"):
            agent = self.home / ".pi" / name
            agent.mkdir(parents=True)
            (agent / "AGENTS.md").write_text("# pi operating index\n\nexisting prose\n")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)


class InstallTest(FakeHome):
    def test_install_writes_every_enforcement_point(self):
        report = self.installer.install(SPEC)
        actions = "\n".join(report["actions"])
        # pi guards in every instance directory
        for entry in SPEC["pi_instances"]:
            guard = self.home / entry[2:] / "extensions/deny-guard.ts"
            self.assertTrue(guard.is_file(), guard)
            self.assertIn(str(guard), actions)
            text = guard.read_text()
            self.assertNotIn(install_deny_rules.GUARD_MARKER, text)
            embedded = text.split("const SPEC = ", 1)[1].split("; // replaced", 1)[0]
            pi_spec = json.loads(embedded)
            self.assertTrue(
                str(pi_spec["ascend_roots"][0]).endswith("/Code/slash-eureka")
            )
        # claude settings: deny merged, existing keys kept
        settings = load(self.home / ".claude/settings.json")
        self.assertEqual(settings["env"], {"A": "1"})
        self.assertEqual(
            settings["permissions"]["allow"], ["WebSearch", "Read(~/docs/**)"]
        )
        for entry in SPEC["claude_code"]["deny"]:
            self.assertIn(entry, settings["permissions"]["deny"])
        self.assertTrue((self.home / ".claude/hooks/deny-merge-guard.py").is_file())
        commands = [
            h["command"]
            for block in settings["hooks"]["PreToolUse"]
            for h in block.get("hooks", [])
        ]
        self.assertEqual(sum("deny-merge-guard.py" in c for c in commands), 1)
        # the registered matcher must fire for Bash and for the T3 thread
        # tools, or the hook's thread-tool check is unreachable
        hook_matchers = [
            block.get("matcher")
            for block in settings["hooks"]["PreToolUse"]
            for h in block.get("hooks", [])
            if "deny-merge-guard.py" in h.get("command", "")
        ]
        self.assertEqual(len(hook_matchers), 1)
        matcher = re.compile(hook_matchers[0])
        self.assertTrue(matcher.search("Bash"))
        for tool in (
            "mcp__t3-code__t3_thread_launch",
            "t3_thread_send",
            "create_threads",
            "mcp__t3-code__create_threads",
        ):
            self.assertTrue(matcher.search(tool), tool)
        self.assertFalse(matcher.search("Read"))
        # scope sections
        for entry in SPEC["scope_files"]["copies"]:
            text = (self.home / entry[2:]).read_text()
            self.assertIn(install_deny_rules.BEGIN, text)
            self.assertIn("existing prose", text)
        claude_md = (self.home / ".claude/CLAUDE.md").read_text()
        self.assertIn("Machine-enforced deny rules", claude_md)
        # backups taken
        self.assertTrue(Path(report["backups"]).is_dir())
        self.assertTrue((Path(report["backups"]) / ".claude/settings.json").is_file())

    def test_install_is_idempotent(self):
        self.installer.install(SPEC)
        self.installer.install(SPEC)
        settings = load(self.home / ".claude/settings.json")
        self.assertEqual(
            settings["permissions"]["deny"], SPEC["claude_code"]["deny"]
        )
        commands = [
            h["command"]
            for block in settings["hooks"]["PreToolUse"]
            for h in block.get("hooks", [])
        ]
        self.assertEqual(sum("deny-merge-guard.py" in c for c in commands), 1)
        for entry in SPEC["pi_instances"]:
            guard = self.home / entry[2:] / "extensions/deny-guard.ts"
            self.assertEqual(len(list(guard.parent.glob("deny-guard.ts*"))), 1)

    def test_status_and_uninstall(self):
        self.installer.install(SPEC)
        status = self.installer.status(SPEC)
        self.assertTrue(status["installed"])
        self.assertEqual(status["claude_deny_missing"], [])
        self.assertTrue(all(v == "installed" for v in status["pi_guards"].values()))
        report = self.installer.uninstall(SPEC)
        settings = load(self.home / ".claude/settings.json")
        self.assertEqual(settings["permissions"].get("deny") or [], [])
        self.assertEqual(settings["permissions"]["allow"], ["WebSearch", "Read(~/docs/**)"])
        self.assertEqual(settings["env"], {"A": "1"})
        self.assertEqual(settings["hooks"]["PreToolUse"], [])
        self.assertFalse((self.home / ".claude/hooks/deny-merge-guard.py").exists())
        for entry in SPEC["pi_instances"]:
            guard = self.home / entry[2:] / "extensions/deny-guard.ts"
            self.assertFalse(guard.exists())
        for entry in SPEC["scope_files"]["copies"]:
            text = (self.home / entry[2:]).read_text()
            self.assertNotIn(install_deny_rules.BEGIN, text)
            self.assertIn("existing prose", text)
        self.assertFalse((self.home / ".claude/CLAUDE.md").exists())
        self.assertTrue(report["uninstalled"])

    def test_uninstall_restores_what_install_replaced(self):
        settings_path = self.home / ".claude/settings.json"
        settings = load(settings_path)
        kept = SPEC["claude_code"]["deny"][0]
        settings["permissions"]["deny"] = [kept]
        settings_path.write_text(json.dumps(settings))
        hook = self.home / ".claude/hooks/deny-merge-guard.py"
        hook.parent.mkdir(parents=True)
        hook.write_text("# user hook\n")
        guard = self.home / SPEC["pi_instances"][0][2:] / "extensions/deny-guard.ts"
        guard.parent.mkdir(parents=True)
        guard.write_text("// user guard\n")
        conf = SPEC["t3_gate_instance"]
        t3_path = self.home / conf["settings"][2:]
        t3_path.parent.mkdir(parents=True)
        prior = {"driver": "claudeAgent", "displayName": "mine", "enabled": False}
        t3_path.write_text(json.dumps({"providerInstances": {conf["instanceId"]: prior}}))
        self.installer.install(SPEC)
        installed = load(t3_path)["providerInstances"][conf["instanceId"]]
        self.assertFalse(installed["enabled"])
        self.installer.uninstall(SPEC)
        self.assertEqual(load(settings_path)["permissions"]["deny"], [kept])
        self.assertEqual(hook.read_text(), "# user hook\n")
        self.assertEqual(guard.read_text(), "// user guard\n")
        self.assertEqual(load(t3_path)["providerInstances"][conf["instanceId"]], prior)

    def test_a_failed_install_rolls_back_what_it_changed(self):
        blocked = self.home / SPEC["pi_instances"][-1][2:] / "extensions"
        blocked.parent.mkdir(parents=True, exist_ok=True)
        blocked.write_text("a file where the extensions directory must go\n")
        with self.assertRaises(OSError):
            self.installer.install(SPEC)
        settings = load(self.home / ".claude/settings.json")
        self.assertEqual(settings["permissions"].get("deny") or [], [])
        self.assertEqual(settings["hooks"]["PreToolUse"], [])
        self.assertFalse((self.home / ".claude/hooks/deny-merge-guard.py").exists())
        self.assertFalse(self.installer.status(SPEC)["t3_gate_instance"])
        self.assertFalse(self.installer.receipt.exists())

    def test_t3_gate_instance_is_installed_and_removed(self):
        conf = SPEC["t3_gate_instance"]
        settings_path = self.home / conf["settings"][2:]
        self.assertFalse(settings_path.exists())
        self.installer.install(SPEC)
        settings = load(settings_path)
        instance = settings["providerInstances"][conf["instanceId"]]
        self.assertEqual(instance["driver"], "claudeAgent")
        self.assertTrue(instance["enabled"])
        self.assertEqual(
            instance["environment"],
            [{"name": "MAC_OPS_ROLE", "value": "gate", "sensitive": False}],
        )
        self.assertTrue(self.installer.status(SPEC)["t3_gate_instance"])
        self.installer.uninstall(SPEC)
        self.assertNotIn(
            conf["instanceId"], load(settings_path).get("providerInstances") or {}
        )
        self.assertFalse(self.installer.status(SPEC)["t3_gate_instance"])

    def test_install_refuses_when_repo_scope_file_lacks_the_section(self):
        real_repo = install_deny_rules.ROOT_REPO
        fake_repo = Path(tempfile.mkdtemp(prefix="deny-rules-repo-", dir=TMP))
        try:
            (fake_repo / "runtime/pi").mkdir(parents=True)
            (fake_repo / "runtime/pi/AGENTS.md").write_text("no section here\n")
            install_deny_rules.ROOT_REPO = fake_repo
            with self.assertRaises(RuntimeError):
                self.installer.install(SPEC)
        finally:
            install_deny_rules.ROOT_REPO = real_repo

    def test_scope_write_skips_symlinks(self):
        linked = self.home / ".pi/agent-linked/AGENTS.md"
        linked.parent.mkdir(parents=True, exist_ok=True)
        linked.symlink_to(self.home / ".pi/agent-openai-api/AGENTS.md")
        result = self.installer.write_scope_section(linked, SPEC)
        self.assertEqual(result, "skipped (symlink; covered by the repo file)")


class ListTest(unittest.TestCase):
    def test_every_claude_entry_only_denies(self):
        for entry in SPEC["claude_code"]["deny"]:
            self.assertTrue(
                entry.startswith(("Read(", "Edit(", "Bash(")), entry
            )
        secret = re.compile(SPEC["secret_file_re"])
        for name in ("tokens.json", "api-token.txt", "tokens.prod.yaml"):
            self.assertTrue(secret.search("/h/" + name), name)
            for tool in ("Read", "Edit"):
                suffix = name.rsplit(".", 1)[1]
                self.assertIn(f"{tool}(**/*token*.{suffix})", SPEC["claude_code"]["deny"])

    def test_regexes_compile_and_classify(self):
        secret = re.compile(SPEC["secret_file_re"])
        text = re.compile(install_deny_rules.derive_text_re(SPEC["secret_file_re"]))
        for path in (
            "/h/.env",
            "/h/Code/app/.env",
            "/h/Code/app/.env.local",
            "/h/.ssh/id_ed25519",
            "/h/.ssh/id_rsa.pub",
            "/h/keys/deploy.pem",
            "/h/secrets/auth.json",
            "/h/tokens.json",
            "/h/api-token.txt",
            "/h/creds/credentials.json",
        ):
            self.assertTrue(secret.search(path), path)
            self.assertTrue(text.search("cat " + path), "cat " + path)
        for path in (
            "/h/Code/app/env.ts",
            "/h/Code/app/src/tokens.ts",
            "/h/notes/environment.md",
            "/h/Code/app/tokenizer.py",
        ):
            self.assertFalse(secret.search(path), path)
        for command in (
            "gh api repos/x --input /h/.env",
            "cat ~/Code/app/.env",
            "cat $HOME/.ssh/id_rsa",
        ):
            self.assertTrue(text.search(command), command)
        # the regex matches ls too; the guard exempts one directory listing only
        self.assertTrue(text.search("ls -la ~/.ssh"))
        guard_text = (ROOT / "runtime/agents/deny-guard.ts").read_text()
        self.assertIn("SINGLE_LS", guard_text)
        self.assertNotIn("bareLs", guard_text)

        hook_spec = importlib.util.spec_from_file_location("deny_merge_guard", HOOK)
        hook = importlib.util.module_from_spec(hook_spec)
        hook_spec.loader.exec_module(hook)
        push = SPEC["push_deny"]
        self.assertEqual(hook.PROTECTED, set(push["protected"]))
        self.assertEqual(hook.FORCE_FLAGS, set(push["force_flags"]))
        for denied in (
            "git push --force origin main",
            "git push -f origin x",
            "git push --force-with-lease origin x",
            "git push origin +main",
            "git push origin main",
            "git push origin main",
            "git -C /tmp/repo push --force origin main",
            "git -C '/tmp/repo with space' push origin main",
            "git push origin master",
            "git push -u origin main",
            "git push origin HEAD:main",
            "git push origin feature:main",
            "git push origin refs/heads/main",
            # the protected ref is the destination of the refspec, so a delete
            # refspec and a full ref destination are the same rule
            "git push origin :main",
            "git push origin feature:refs/heads/main",
            # a remote URL contains ':', so the repository token must allow it
            "git push https://github.com/shyamsivakumar/mac-ops.git main",
            "git push git@github.com:shyamsivakumar/mac-ops.git master",
            "git push -u https://github.com/shyamsivakumar/mac-ops.git main",
        ):
            self.assertIsNotNone(hook.decision(denied), denied)
        for allowed in (
            "git push origin t3/deny-rules",
            "git push origin t3/main-fix",
            "git push origin feature/main-work",
            "git push origin main.fix",
            "git push origin master.fix",
            "git push origin main/fix",
            "git push origin main2",
            "git push origin HEAD:main.fix",
            "git push origin HEAD:main/fix",
            "git push origin refs/heads/main.fix",
            "git push origin refs/heads/main/fix",
            "git push --set-upstream origin t3/x",
            "git -C /tmp/repo push origin t3/deny-rules",
            # a refspec's destination decides the rule: a protected source that
            # writes a task branch is a task-branch push
            "git push origin main:task-530",
            "git push origin master:task-530",
            "git push origin refs/heads/main:task-530",
            # a task branch pushed to a URL remote stays allowed
            "git push https://github.com/shyamsivakumar/mac-ops.git t3/deny-rules",
            "git push git@github.com:shyamsivakumar/mac-ops.git t3/main-fix",
        ):
            self.assertIsNone(hook.decision(allowed), allowed)

        merge = re.compile(SPEC["merge_deny"]["match_re"])
        self.assertTrue(merge.search("gh pr merge 531 -R shyamsivakumar/mac-ops --squash"))

    def test_ascend_text_res_covers_spellings(self):
        home = "/Users/t"
        patterns = install_deny_rules.ascend_text_res([home + "/Code/slash-eureka"], home)
        combined = re.compile("|".join(patterns))
        for command in (
            "cat /Users/t/Code/slash-eureka/dbt/x",
            "ls ~/Code/slash-eureka",
            "rg foo $HOME/Code/slash-eureka/ops",
            "cd ${HOME}/Code/slash-eureka",
            "cat ~/Code/slash-eureka",
        ):
            self.assertTrue(combined.search(command), command)
        for command in (
            "cat ~/Code/mac-ops/README.md",
            "rg slash-eureka ~/Code/mac-ops",
            "cat ~/Code/slash-eureka-notes/x",
        ):
            self.assertFalse(combined.search(command), command)


class HookTest(unittest.TestCase):
    def run_hook(self, payload, role=None):
        env = {k: v for k, v in os.environ.items() if k != "MAC_OPS_ROLE"}
        if role is not None:
            env["MAC_OPS_ROLE"] = role
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    PINNED = (
        "gh pr merge 531 -R shyamsivakumar/mac-ops --squash "
        "--match-head-commit 5d3f2c1a4b5e6f70819283a4b5c6d7e8f9011223"
    )

    def scratch_repo(self, branch, upstream=None, **options):
        root = Path(tempfile.mkdtemp(prefix="deny-rules-repo-", dir=TMP))
        self.addCleanup(shutil.rmtree, root, True)
        return make_repo(root / "work", branch, upstream, **options)

    def decided(self, command, role=None, cwd=None):
        payload = {"tool_name": "Bash", "tool_input": {"command": command}}
        if cwd:
            payload["cwd"] = str(cwd)
        out = self.run_hook(payload, role=role)
        return json.loads(out)["hookSpecificOutput"] if out.strip() else None

    def test_denies_unpinned_merge(self):
        for role in (None, "gate"):
            for command in (
                "gh pr merge 531",
                "gh pr merge 531 --squash",
                "gh pr merge 531 -R shyamsivakumar/mac-ops --squash --delete-branch",
                "gh -R shyamsivakumar/mac-ops pr merge 531 --squash",
                "gh --repo=shyamsivakumar/mac-ops pr merge 531",
                "gh pr -R shyamsivakumar/mac-ops merge 531",
            ):
                decision = self.decided(command, role)
                self.assertIsNotNone(decision, (role, command))
                self.assertEqual(decision["permissionDecision"], "deny", (role, command))

    def test_denies_pinned_merge_without_the_gate_role(self):
        for role in (None, "builder", ""):
            decision = self.decided(self.PINNED, role)
            self.assertIsNotNone(decision, role)
            self.assertEqual(decision["permissionDecision"], "deny", role)

    def test_a_mentioned_pin_is_not_a_merge_argument(self):
        for command in (
            # the flag appears inside another argument's value, not as the pin
            "gh pr merge 531 --squash --body 'see --match-head-commit 5d3f2c1a4b5e6f70819283a4b5c6d7e8f9011223'",
            # a quoted, multiword subject keeps its words: the flag and id
            # inside it are subject text, so they are not a merge argument
            "gh pr merge 531 --squash --subject 'Merge --match-head-commit 5d3f2c1a4b5e6f70819283a4b5c6d7e8f9011223'",
            'gh pr merge 531 --squash --subject "Merge --match-head-commit=5d3f2c1a4b5e6f70819283a4b5c6d7e8f9011223"',
            # no value after the flag
            "gh pr merge 531 --squash --match-head-commit",
            # not a commit id
            "gh pr merge 531 --squash --match-head-commit main",
            "gh pr merge 531 --squash --match-head-commit abc123",
        ):
            decision = self.decided(command, "gate")
            self.assertIsNotNone(decision, command)
            self.assertEqual(decision["permissionDecision"], "deny", command)

    def test_allows_pinned_merge(self):
        self.assertIsNone(self.decided(self.PINNED, "gate"))
        pinned = self.PINNED.replace("gh pr merge", "gh -R x/y pr merge")
        self.assertIsNone(self.decided(pinned, "gate"))
        self.assertIsNotNone(self.decided(pinned, None))

    def test_denies_protected_branch_pushes_on_every_remote(self):
        for command in (
            "git push origin main",
            "git push upstream main",
            "git push other master",
            "git push --set-upstream repo2 main",
            "git push origin HEAD:main",
            "git push repo2 feature:master",
            "git -C /tmp/r push elsewhere refs/heads/main",
            "git push origin :main",
            "git push origin feature:refs/heads/main",
            "git push https://github.com/shyamsivakumar/mac-ops.git main",
            "git push git@github.com:shyamsivakumar/mac-ops.git master",
        ):
            decision = self.decided(command)
            self.assertIsNotNone(decision, command)
            self.assertEqual(decision["permissionDecision"], "deny", command)

    def test_implicit_and_bulk_pushes_are_resolved_or_refused(self):
        on_main = self.scratch_repo("main", "refs/heads/main")
        on_task = self.scratch_repo("t3/x", "refs/heads/t3/x")
        task_tracking_main = self.scratch_repo("t3/y", "refs/heads/main")
        task_remote_pushes_main = self.scratch_repo(
            "t3/z",
            "refs/heads/t3/z",
            config=[("remote.origin.push", "refs/heads/t3/z:refs/heads/main")],
        )
        task_on_remote_named_main = self.scratch_repo(
            "t3/w", remote="main", config=[("push.default", "current")]
        )
        self.assertIsNone(
            self.decided("git push main", cwd=task_on_remote_named_main),
            "a remote named main, pushing a task branch",
        )
        for command in ("git push", "git push origin"):
            decision = self.decided(command, cwd=task_remote_pushes_main)
            self.assertIsNotNone(decision, command)
            self.assertEqual(decision["permissionDecision"], "deny", command)
        for repo, commands in (
            (on_main, ("git push", "git push origin", "git push -u origin", "git push origin HEAD")),
            (task_tracking_main, ("git push", "git push origin")),
        ):
            for command in commands:
                decision = self.decided(command, cwd=repo)
                self.assertIsNotNone(decision, (repo, command))
                self.assertEqual(decision["permissionDecision"], "deny", command)
        for command in (
            "git push --all origin",
            "git push origin --all",
            "git push --mirror origin",
            "git push origin :",
            "git push origin 'refs/heads/*:refs/heads/*'",
            f"git -C {on_main} push",
            f"cd {on_main} && git push",
        ):
            decision = self.decided(command, cwd=on_task)
            self.assertIsNotNone(decision, command)
            self.assertEqual(decision["permissionDecision"], "deny", command)
        for command in (
            "git push",
            "git push origin",
            "git push -u origin",
            "git push origin HEAD",
            "git push origin t3/x",
            f"git -C {on_task} push",
        ):
            self.assertIsNone(self.decided(command, cwd=on_task), command)
        self.assertIsNone(
            self.decided(f"git -C {on_task} push", cwd=on_main), "git -C task repo"
        )

    def test_allows_task_branches_that_start_with_a_protected_name(self):
        # `main.fix` is a task branch, not the protected ref `main`: the rule
        # compares the complete destination ref, not a prefix of it.
        for command in (
            "git push origin main.fix",
            "git push origin master.fix",
            "git push origin main/fix",
            "git push origin master/fix",
            "git push origin main2",
            "git push origin HEAD:main.fix",
            "git push origin HEAD:main/fix",
            "git push origin refs/heads/main.fix",
            "git push origin refs/heads/main/fix",
            "git push origin feature/main.fix",
            # the destination of each refspec is compared, not the source, so a
            # task-branch push is not read as a push to its source's name
            "git push origin main:task-530",
            "git push origin master:task-530",
            "git push origin refs/heads/main:task-530",
        ):
            self.assertIsNone(self.decided(command), command)

    def test_denies_force_push_on_every_remote(self):
        for command in (
            "git push --force origin t3/x",
            "git push -f upstream t3/x",
            "git push --force-with-lease other t3/x",
            "git push repo2 +t3/x",
        ):
            decision = self.decided(command)
            self.assertIsNotNone(decision, command)
            self.assertEqual(decision["permissionDecision"], "deny", command)

    def test_allows_task_branch_push(self):
        for command in (
            "git push origin t3/deny-rules",
            "git push --set-upstream upstream t3/deny-rules",
            "git -C /tmp/r push other t3/main-fix",
            "git push origin feature/main-work",
            "git push https://github.com/shyamsivakumar/mac-ops.git t3/deny-rules",
        ):
            self.assertIsNone(self.decided(command), command)

    def test_a_remote_named_main_does_not_block_a_task_branch_push(self):
        # The first bare word after `push` is the repository argument, so a
        # remote called `main` or `master` is not a destination branch.
        for command in (
            "git push main task-530",
            "git push master task-530",
            "git push main main.fix",
            "git push master t3/deny-rules",
            "git push -u main t3/deny-rules",
            "git push main main:task-530",
        ):
            self.assertIsNone(self.decided(command), command)
        for command in (
            "git push main main",
            "git push master master",
            "git push master HEAD:master",
        ):
            decision = self.decided(command)
            self.assertIsNotNone(decision, command)
            self.assertEqual(decision["permissionDecision"], "deny", command)
        # a lone protected word names the branch to push, not only a remote
        self.assertIsNotNone(self.decided("git push main"))
        self.assertIsNotNone(self.decided("git push master"))

    def test_denies_launching_a_thread_on_the_gate_instance(self):
        payload = {
            "tool_name": "mcp__t3-code__t3_thread_launch",
            "tool_input": {
                "title": "gate",
                "modelSelection": {
                    "instanceId": "claudeAgentGate",
                    "model": "claude-opus-5-5",
                },
            },
        }
        decision = json.loads(self.run_hook(payload))["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertEqual(self.run_hook(payload, role="gate"), "")
        self.assertEqual(
            self.run_hook(
                {
                    "tool_name": "mcp__t3-code__t3_thread_launch",
                    "tool_input": {
                        "title": "builder",
                        "modelSelection": {
                            "instanceId": "pi",
                            "model": "deepseek/deepseek-flash",
                        },
                    },
                }
            ),
            "",
        )

    def test_ignores_other_tools_and_commands(self):
        self.assertEqual(
            self.run_hook({"tool_name": "Read", "tool_input": {"path": "/x"}}), ""
        )
        self.assertEqual(
            self.run_hook({"tool_name": "Bash", "tool_input": {"command": "gh pr view 531"}}),
            "",
        )
        self.assertEqual(self.run_hook({"tool_name": "Bash"}), "")
        for command in ("gh -R x/y pr view 1", "gh pr view 1 -R x/y", "gh --repo x/y pr list"):
            self.assertIsNone(self.decided(command), command)


class GuardTest(unittest.TestCase):
    """The installed guard file, loaded the way pi loads it, on real events."""

    HARNESS = """
const guard = await import(process.argv[2]);
const events = JSON.parse(await Bun.file(process.argv[3]).text());
const baseEnv = { ...process.env };
let handler;
guard.default({ on: (name, fn) => { if (name === "tool_call") handler = fn; } });
const out = [];
for (const item of events) {
  for (const key of Object.keys(process.env)) if (!(key in baseEnv)) delete process.env[key];
  Object.assign(process.env, baseEnv, item.env || {});
  const decision = await handler(item.event, { cwd: item.cwd });
  out.push(decision ? decision.reason : null);
}
console.log(JSON.stringify(out));
"""

    def test_guard_denies_and_allows_the_list(self):
        bun = Path.home() / ".bun/bin/bun"
        if not bun.is_file():
            self.skipTest("bun is not installed; the pi guard cannot be loaded here")
        scratch = Path(tempfile.mkdtemp(prefix="deny-guard-test-", dir=TMP))
        self.addCleanup(shutil.rmtree, scratch, True)
        harness = scratch / "harness.ts"
        harness.write_text(self.HARNESS)
        # The template carries an empty spec; render it the way the installer does.
        guard = scratch / "deny-guard.ts"
        guard.write_text(install_deny_rules.render_guard(SPEC, Path.home()))
        fake_env = scratch / "app/.env"
        fake_env.parent.mkdir()
        fake_env.write_text("FAKE=1\n")
        ascend = str(Path.home() / "Code/slash-eureka/README.md")
        pinned = "gh pr merge 531 --squash --match-head-commit " + "a" * 40
        gate = {"MAC_OPS_ROLE": "gate"}
        on_main = scratch / "on-main"
        on_task = scratch / "on-task"
        make_repo(on_main, "main", "refs/heads/main")
        make_repo(on_task, "t3/x", "refs/heads/t3/x")
        cases = [
            ({"toolName": "read", "input": {"path": ascend}}, True, {}),
            ({"toolName": "edit", "input": {"path": str(fake_env)}}, True, {}),
            (
                {"toolName": "write", "input": {"path": str(fake_env), "content": "x"}},
                True,
                {},
            ),
            ({"toolName": "bash", "input": {"command": f"cat {fake_env}"}}, True, {}),
            (
                {"toolName": "bash", "input": {"command": "git push --force origin main"}},
                True,
                {},
            ),
            ({"toolName": "bash", "input": {"command": "git push origin main"}}, True, {}),
            # The protected branch rule covers every remote, not only origin.
            ({"toolName": "bash", "input": {"command": "git push other master"}}, True, {}),
            (
                {"toolName": "bash", "input": {"command": "git push repo2 HEAD:main"}},
                True,
                {},
            ),
            ({"toolName": "bash", "input": {"command": "gh pr merge 531 --squash"}}, True, {}),
            (
                {"toolName": "bash", "input": {"command": "gh -R x/y pr merge 531 --squash"}},
                True,
                {},
            ),
            ({"toolName": "bash", "input": {"command": "gh -R x/y pr view 531"}}, False, {}),
            ({"toolName": "bash", "input": {"command": f"git -C {on_main} push"}}, True, {}),
            ({"toolName": "bash", "input": {"command": f"git -C {on_main} push origin"}}, True, {}),
            ({"toolName": "bash", "input": {"command": "git push --all origin"}}, True, {}),
            ({"toolName": "bash", "input": {"command": "git push --mirror origin"}}, True, {}),
            ({"toolName": "bash", "input": {"command": f"git -C {on_task} push"}}, False, {}),
            # A pin in the command grants nothing without the gate role.
            ({"toolName": "bash", "input": {"command": pinned}}, True, {}),
            # A mentioned pin is not a merge argument.
            (
                {
                    "toolName": "bash",
                    "input": {
                        "command": "gh pr merge 531 --squash --body 'pin " + "a" * 40 + "'"
                    },
                },
                True,
                gate,
            ),
            (
                {
                    "toolName": "bash",
                    "input": {
                        "command": "gh pr merge 531 --squash --subject 'Merge --match-head-commit " + "a" * 40 + "'"
                    },
                },
                True,
                gate,
            ),
            (
                {
                    "toolName": "bash",
                    "input": {
                        "command": "gh pr merge 531 --squash --match-head-commit main"
                    },
                },
                True,
                gate,
            ),
            ({"toolName": "bash", "input": {"command": pinned}}, False, gate),
            (
                {"toolName": "bash", "input": {"command": "git push -u origin t3/deny-rules"}},
                False,
                {},
            ),
            # A task branch whose name continues past a protected one with a
            # slash is a task branch, not the protected ref.
            (
                {"toolName": "bash", "input": {"command": "git push origin main/fix"}},
                False,
                {},
            ),
            # A single directory listing only shows names.
            ({"toolName": "ls", "input": {"path": str(fake_env)}}, False, {}),
            ({"toolName": "bash", "input": {"command": "ls -la ~/.ssh"}}, False, {}),
            # The same command with a second operation is a read of the key.
            (
                {"toolName": "bash", "input": {"command": "ls ~/.ssh; cat ~/.ssh/id_rsa"}},
                True,
                {},
            ),
            ({"toolName": "bash", "input": {"command": "ls ~/.ssh | xargs cat"}}, True, {}),
            # Writing prose that mentions a secret path is not a secret read.
            (
                {
                    "toolName": "write",
                    "input": {
                        "path": str(scratch / "docs/deny.md"),
                        "content": "No reads of .env, auth.json or ~/.ssh/id_ed25519.\n",
                    },
                },
                False,
                {},
            ),
            # Editing prose around a path is not a secret edit either.
            (
                {
                    "toolName": "edit",
                    "input": {
                        "path": str(scratch / "docs/deny.md"),
                        "edits": [{"oldText": "a", "newText": "cat app/.env"}],
                    },
                },
                False,
                {},
            ),
        ]
        events = [
            {"cwd": str(scratch), "event": event, "env": extra}
            for event, _, extra in cases
        ]
        events_path = scratch / "events.json"
        events_path.write_text(json.dumps(events))
        proc = subprocess.run(
            [str(bun), str(harness), str(guard), str(events_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        reasons = json.loads(proc.stdout)
        self.assertEqual(len(reasons), len(cases))
        for (event, want_block, _), reason in [
            (case, reasons[index]) for index, case in enumerate(cases)
        ]:
            self.assertEqual(
                reason is not None,
                want_block,
                f"{event} -> {reason}",
            )
            if want_block:
                self.assertIn("mac-ops deny rules (#530)", reason)


if __name__ == "__main__":
    unittest.main()
