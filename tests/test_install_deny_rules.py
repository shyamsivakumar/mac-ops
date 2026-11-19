import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))
HOOK = ROOT / "runtime/agents/deny-merge-guard.py"
SPEC = json.loads((ROOT / "runtime/agents/deny-rules.json").read_text())


def load_module(name, path):
    loader = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


install_deny_rules = load_module(
    "install_deny_rules", ROOT / "scripts/install_deny_rules.py"
)
hook_module = load_module("deny_merge_guard", HOOK)


def load(path):
    return json.loads(Path(path).read_text())


class FakeHome(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="deny-rules-test-", dir=TMP))
        self.installer = install_deny_rules.Installer(self.home)
        self.settings_path = self.home / ".claude/settings.json"
        self.settings_path.parent.mkdir(parents=True)
        self.settings_path.write_text(
            json.dumps({"env": {"A": "1"}, "permissions": {"allow": ["WebSearch"]}})
        )
        for name in ("agent-openai-api", "agent-anthropic-api"):
            agent = self.home / ".pi" / name
            agent.mkdir(parents=True)
            (agent / "AGENTS.md").write_text("existing prose\n")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def managed_bytes(self):
        paths = self.installer.managed_paths(SPEC)
        return {p: p.read_bytes() if p.is_file() else None for p in paths}


class InstallTest(FakeHome):
    def test_install_writes_every_enforcement_point(self):
        report = self.installer.install(SPEC)
        for guard in self.installer.guard_targets(SPEC):
            embedded = (
                guard.read_text()
                .split("const SPEC = ", 1)[1]
                .split("; // replaced", 1)[0]
            )
            pi_spec = json.loads(embedded)
            self.assertTrue(pi_spec["ascend_roots"][0].endswith("/Code/slash-eureka"))
            self.assertEqual(
                pi_spec["hook_path"], str(self.installer.hook_target(SPEC))
            )
        settings = load(self.settings_path)
        self.assertEqual(settings["env"], {"A": "1"})
        self.assertEqual(settings["permissions"]["allow"], ["WebSearch"])
        self.assertEqual(
            settings["permissions"]["deny"],
            list(dict.fromkeys(install_deny_rules.claude_deny(SPEC, self.home))),
        )
        self.assertTrue(self.installer.hook_target(SPEC).is_file())
        blocks = settings["hooks"]["PreToolUse"]
        self.assertEqual(len(blocks), 1)
        matcher = re.compile(blocks[0]["matcher"])
        self.assertTrue(matcher.search("Bash"))
        self.assertFalse(matcher.search("Read"))
        for path in self.installer.scope_paths(SPEC):
            self.assertIn(install_deny_rules.BEGIN, path.read_text())
        self.assertTrue(Path(report["backups"]).parent.is_dir())

    def test_reinstall_is_idempotent(self):
        self.installer.install(SPEC)
        before = self.managed_bytes()
        self.installer.install(SPEC)
        after = self.managed_bytes()
        receipt = self.installer.receipt
        before.pop(receipt), after.pop(receipt)
        self.assertEqual(before, after)
        self.assertEqual(len(load(self.settings_path)["hooks"]["PreToolUse"]), 1)

    def test_status_and_uninstall(self):
        self.installer.install(SPEC)
        status = self.installer.status(SPEC)
        self.assertTrue(status["installed"])
        self.assertEqual(status["claude_deny_missing"], [])
        self.assertTrue(all(v == "installed" for v in status["pi_guards"].values()))
        self.installer.uninstall(SPEC)
        settings = load(self.settings_path)
        self.assertEqual(settings["permissions"], {"allow": ["WebSearch"], "deny": []})
        self.assertEqual(settings["hooks"]["PreToolUse"], [])
        self.assertFalse(self.installer.hook_target(SPEC).exists())
        self.assertFalse(any(g.exists() for g in self.installer.guard_targets(SPEC)))
        self.assertEqual(
            (self.home / ".pi/agent-openai-api/AGENTS.md").read_text(),
            "existing prose\n",
        )
        self.assertFalse((self.home / ".claude/CLAUDE.md").exists())

    def test_uninstall_restores_what_install_replaced(self):
        kept = install_deny_rules.claude_deny(SPEC, self.home)[0]
        settings = load(self.settings_path)
        settings["permissions"]["deny"] = [kept]
        self.settings_path.write_text(json.dumps(settings))
        hook = self.installer.hook_target(SPEC)
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("# user hook\n")
        self.installer.install(SPEC)
        self.installer.uninstall(SPEC)
        self.assertEqual(load(self.settings_path)["permissions"]["deny"], [kept])
        self.assertEqual(hook.read_text(), "# user hook\n")

    def test_an_unmanaged_guard_is_refused_and_nothing_changes(self):
        guard = self.installer.guard_targets(SPEC)[1]
        guard.parent.mkdir(parents=True)
        guard.write_text("// guard with extra denied paths\n")
        before = self.managed_bytes()
        with self.assertRaises(RuntimeError):
            self.installer.install(SPEC)
        self.assertEqual(self.managed_bytes(), before)

    def test_a_hook_registered_under_another_matcher_still_gets_a_bash_registration(self):
        command = self.installer.hook_command(SPEC)
        read_entry = {"matcher": "Read", "hooks": [{"type": "command", "command": command}]}
        settings = load(self.settings_path)
        settings["hooks"] = {"PreToolUse": [read_entry]}
        self.settings_path.write_text(json.dumps(settings))
        self.installer.install(SPEC)
        matchers = [b["matcher"] for b in load(self.settings_path)["hooks"]["PreToolUse"]]
        self.assertEqual(matchers, ["Read", SPEC["claude_code"]["hook"]["matcher"]])
        self.installer.uninstall(SPEC)
        self.assertEqual(load(self.settings_path)["hooks"]["PreToolUse"], [read_entry])

    def test_unbalanced_scope_markers_refuse_and_change_nothing(self):
        scope = self.installer.scope_paths(SPEC)[0]
        scope.write_text(f"head\n{install_deny_rules.BEGIN}\nuser lines after the marker\n")
        before = self.managed_bytes()
        with self.assertRaises(RuntimeError):
            self.installer.install(SPEC)
        self.assertEqual(self.managed_bytes(), before)
        self.assertFalse(self.installer.receipt.exists())

    def test_a_receipt_without_prior_files_is_upgraded(self):
        self.installer.install(SPEC)
        receipt = load(self.installer.receipt)
        receipt.pop("prior_files")
        self.installer.receipt.write_text(json.dumps(receipt))
        self.installer.install(SPEC)
        self.assertIn("prior_files", load(self.installer.receipt))
        self.assertTrue(all(v == "installed" for v in self.installer.status(SPEC)["pi_guards"].values()))

    def block_last_guard(self):
        last = self.installer.guard_targets(SPEC)[-1]
        real_write = install_deny_rules.atomic_write

        def failing(path, text, mode=0o600):
            if path == last:
                raise OSError("forced write failure")
            real_write(path, text, mode)

        return mock.patch.object(install_deny_rules, "atomic_write", failing)

    def test_a_failed_first_install_leaves_nothing_behind(self):
        before = self.managed_bytes()
        with self.block_last_guard(), self.assertRaises(OSError):
            self.installer.install(SPEC)
        self.assertEqual(self.managed_bytes(), before)

    def test_a_failed_reinstall_restores_the_previous_install(self):
        self.installer.install(SPEC)
        before = self.managed_bytes()
        with self.block_last_guard(), self.assertRaises(OSError):
            self.installer.install(SPEC)
        self.assertEqual(self.managed_bytes(), before)
        status = self.installer.status(SPEC)
        self.assertTrue(status["installed"])
        self.assertEqual(status["claude_deny_missing"], [])
        self.assertTrue(all(v == "installed" for v in status["pi_guards"].values()))

    def test_install_refuses_when_repo_scope_file_lacks_the_section(self):
        fake_repo = Path(tempfile.mkdtemp(prefix="deny-rules-repo-", dir=TMP))
        self.addCleanup(shutil.rmtree, fake_repo, True)
        (fake_repo / "runtime/pi").mkdir(parents=True)
        (fake_repo / "runtime/pi/AGENTS.md").write_text("no section here\n")
        with (
            mock.patch.object(install_deny_rules, "ROOT_REPO", fake_repo),
            self.assertRaises(RuntimeError),
        ):
            self.installer.install(SPEC)

    def test_scope_write_skips_symlinks(self):
        linked = self.home / ".pi/agent-linked/AGENTS.md"
        linked.parent.mkdir(parents=True)
        linked.symlink_to(self.home / ".pi/agent-openai-api/AGENTS.md")
        self.assertIn("skipped", self.installer.write_scope_section(linked, SPEC))


class ListTest(unittest.TestCase):
    def test_claude_list_only_denies_and_covers_token_files(self):
        entries = install_deny_rules.claude_deny(SPEC, Path("/Users/t"))
        self.assertTrue(all(e.startswith(("Read(", "Edit(", "Bash(")) for e in entries))
        for tool in ("Read", "Edit"):
            self.assertIn(f"{tool}(**/*token*.json)", entries)
            self.assertIn(f"{tool}(//Users/t/.ssh/**)", entries)
        self.assertIn("Bash(cat $HOME/Code/slash-eureka:*)", entries)
        self.assertIn("Bash(git push --force-if-includes:*)", entries)

    def test_hook_constants_match_the_list(self):
        self.assertEqual(hook_module.PROTECTED, set(SPEC["push_protected"]))
        for flag in SPEC["push_force_flags"]:
            self.assertTrue(hook_module.push_reason(["origin", "t3/x", flag]), flag)

    def test_secret_regexes_classify_paths_and_commands(self):
        secret = re.compile(SPEC["secret_file_re"])
        text = re.compile(install_deny_rules.derive_text_re(SPEC["secret_file_re"]))
        for path in (
            "/h/.env",
            "/h/app/.env.local",
            "/h/.ssh/id_rsa.pub",
            "/h/k/deploy.pem",
            "/h/auth.json",
            "/h/tokens.json",
            "/h/api-token.txt",
        ):
            self.assertTrue(secret.search(path), path)
            self.assertTrue(text.search("cat " + path), path)
        for path in (
            "/h/app/env.ts",
            "/h/src/tokens.ts",
            "/h/notes/environment.md",
            "/h/tokenizer.py",
        ):
            self.assertFalse(secret.search(path), path)

    def test_ascend_text_res_cover_spellings(self):
        home = "/Users/t"
        combined = re.compile(
            "|".join(
                install_deny_rules.ascend_text_res([home + "/Code/slash-eureka"], home)
            )
        )
        for command in (
            "cat /Users/t/Code/slash-eureka/x",
            "ls ~/Code/slash-eureka",
            "rg a $HOME/Code/slash-eureka/ops",
            "cd ${HOME}/Code/slash-eureka",
        ):
            self.assertTrue(combined.search(command), command)
        for command in (
            "cat ~/Code/mac-ops/README.md",
            "cat ~/Code/slash-eureka-notes/x",
        ):
            self.assertFalse(combined.search(command), command)


PR_TEXT = "Rule: no git push origin main, no git push --force."
DENIED_PUSHES = [
    "git push",
    "git push origin",
    "git push -u origin",
    "git push origin HEAD",
    "git push main",
    "git push --all origin",
    "git push --mirror origin",
    "git push origin :",
    "git push origin 'refs/heads/*:refs/heads/*'",
    "git push origin $BRANCH",
    "git push origin main",
    "git push upstream master",
    "git push -u origin main",
    "git push origin HEAD:main",
    "git push origin feature:master",
    "git push origin refs/heads/main",
    "git push origin :main",
    "git push origin feature:refs/heads/main",
    "git push origin --delete main",
    "git push https://github.com/x/y.git main",
    "git push git@github.com:x/y.git master",
    "git -C /tmp/r push elsewhere refs/heads/main",
    "heavy git push origin main",
    "bash -c 'git push origin main'",
    "git push main main",
    "git push master HEAD:master",
    "git push origin t3/x && git push origin main",
    "if true; then git push origin main; fi",
    "for b in x; do git push origin main; done",
    "! git push origin main",
    "{ git push origin main; }",
    "while true; do git push; done",
    "git push --force origin t3/x",
    "git push -f upstream t3/x",
    "git push --force-with-lease other t3/x",
    "git push --force-if-includes origin t3/x",
    "git push origin t3/x --force",
    "git push origin +t3/x",
    "git push -fu origin t3/x",
]
ALLOWED_COMMANDS = [
    "git push origin task",
    "git push -u origin t3/x",
    "git push --set-upstream upstream t3/x",
    "git push main task",
    "git push master t3/deny-rules",
    "git push main main:task-530",
    "git push origin main.fix",
    "git push origin main/fix",
    "git push origin main2",
    "git push origin HEAD:main.fix",
    "git push origin refs/heads/main:task-530",
    "git push --repo=origin t3/x",
    "git -C /tmp/r push origin t3/main-fix",
    "git push https://github.com/x/y.git t3/x",
    "heavy git push -u origin t3/x",
    f"git push origin t3/x && gh pr create --title T --body '{PR_TEXT}'",
    "git push origin t3/x\ngh pr create --body-file - <<'EOF'\ngit push origin main\nEOF",
    "git push origin t3/x && gh pr edit 1 --body \"$(cat <<'EOF'\nNever git push origin main\nEOF\n)\"",
    "hc send coordinator 'No push to main, no git push --force, no gh pr merge for a builder'",
    "hc send coordinator git push origin main is denied",
    "git commit -m 'Deny gh pr merge for builders'",
    "gh pr view 531",
    "gh -R x/y pr view 1",
    "gh pr view 1 -R x/y",
    "gh --repo x/y pr list",
]
MERGES_NOT_ENFORCED = [
    "gh pr merge 531",
    "gh pr merge 531 -R x/y --squash --delete-branch",
    "gh -R x/y pr merge 531 --squash",
    "gh --repo=x/y pr merge 531",
    "gh pr -R x/y merge 531",
    "hc send c 'gh pr merge is gated' && gh pr merge 531 --squash",
    "gh pr merge 531 --match-head-commit",
    "gh pr merge 531 --match-head-commit main",
    "if true; then gh pr merge 531 --squash; fi",
    "until false; do gh pr merge 531; done",
]


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
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return (
            json.loads(proc.stdout)["hookSpecificOutput"]
            if proc.stdout.strip()
            else None
        )

    def decided(self, command, role=None):
        return self.run_hook(
            {"tool_name": "Bash", "tool_input": {"command": command}}, role
        )

    def test_pushes_are_decided_from_the_command_destinations(self):
        for command in DENIED_PUSHES:
            decision = self.decided(command)
            self.assertEqual(
                (decision or {}).get("permissionDecision"), "deny", command
            )
        for command in ALLOWED_COMMANDS:
            self.assertIsNone(self.decided(command), command)

    def test_a_push_without_a_destination_says_to_name_the_branch(self):
        for command in (
            "git push",
            "git push origin",
            "git push origin HEAD",
            "git push --all origin",
        ):
            self.assertIn(
                "name the branch",
                self.decided(command)["permissionDecisionReason"],
                command,
            )

    def test_merge_commands_are_not_enforced_here(self):
        for role in (None, "gate"):
            for command in MERGES_NOT_ENFORCED:
                self.assertIsNone(self.decided(command, role), (role, command))

    def test_a_command_in_or_moving_into_the_ascend_tree_is_denied(self):
        ascend = Path.home() / "Code/slash-eureka/x"

        def at(command, cwd):
            payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}
            return self.run_hook(payload)

        self.assertEqual(at("cat README.md", ascend)["permissionDecision"], "deny")
        self.assertIsNone(at("cat README.md", ROOT))
        for command in ("cd ~/Code/slash-eureka/x && ls", "cd $HOME/Code/slash-eureka && ls", "cd ../slash-eureka/x && ls"):
            cwd = Path.home() / "Code/mac-ops"
            self.assertEqual(at(command, cwd)["permissionDecision"], "deny", command)
        self.assertIsNone(at("cd src && ls", ROOT))

    def test_other_tools_and_missing_input_are_ignored(self):
        self.assertIsNone(
            self.run_hook({"tool_name": "Read", "tool_input": {"path": "/x"}})
        )
        self.assertIsNone(self.run_hook({"tool_name": "Bash"}))


class GuardTest(FakeHome):
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

    def test_the_installed_guard_denies_and_allows_the_list(self):
        bun = Path.home() / ".bun/bin/bun"
        if not bun.is_file():
            self.skipTest("bun is not installed; the pi guard cannot be loaded here")
        self.installer.install(SPEC)
        guard = self.installer.guard_targets(SPEC)[0]
        fake_env = self.home / "app/.env"
        ascend = str(self.home / "Code/slash-eureka/README.md")
        (self.home / "Code/slash-eureka").mkdir(parents=True)
        (self.home / "link").symlink_to(self.home / "Code/slash-eureka")

        def bash(command, env=None, cwd=None):
            event = {"toolName": "bash", "input": {"command": command}}
            return ({**event, "cwd": cwd} if cwd else event, env or {})

        cases = [
            (({"toolName": "read", "input": {"path": ascend}}, {}), True),
            (({"toolName": "edit", "input": {"path": str(fake_env)}}, {}), True),
            (bash(f"cat {fake_env}"), True),
            (bash("git push origin main"), True),
            (({"toolName": "write", "input": {"path": str(self.home / "link/new.txt")}}, {}), True),
            (bash("if true; then git push origin main; fi"), True),
            (bash("cat README.md", cwd=str(self.home / "Code/slash-eureka/x")), True),
            (bash("cat README.md", cwd=str(self.home)), False),
            (bash("git push"), True),
            (bash("git push origin t3/x --force"), True),
            (bash("git push origin HEAD:main"), True),
            (bash("gh -R x/y pr merge 531 --squash"), False),
            (bash("ls ~/.ssh; cat ~/.ssh/id_rsa"), True),
            (bash("git push -u origin t3/x"), False),
            (bash("git push main task"), False),
            (bash("gh -R x/y pr view 531"), False),
            (bash("ls -la ~/.ssh"), False),
            (
                (
                    {
                        "toolName": "write",
                        "input": {
                            "path": str(self.home / "d.md"),
                            "content": "no .env reads",
                        },
                    },
                    {},
                ),
                False,
            ),
        ]
        events = [
            {"cwd": event.pop("cwd", str(self.home)), "event": event, "env": env}
            for (event, env), _ in cases
        ]
        (self.home / "events.json").write_text(json.dumps(events))
        (self.home / "harness.ts").write_text(self.HARNESS)
        proc = subprocess.run(
            [
                str(bun),
                str(self.home / "harness.ts"),
                str(guard),
                str(self.home / "events.json"),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        reasons = json.loads(proc.stdout)
        self.assertEqual(len(reasons), len(cases))
        for index, ((event, _), want_block) in enumerate(cases):
            reason = reasons[index]
            self.assertEqual(reason is not None, want_block, f"{event} -> {reason}")

    def test_a_guard_whose_hook_is_missing_blocks_every_command(self):
        bun = Path.home() / ".bun/bin/bun"
        if not bun.is_file():
            self.skipTest("bun is not installed; the pi guard cannot be loaded here")
        self.installer.install(SPEC)
        self.installer.hook_target(SPEC).unlink()
        events = [
            {
                "cwd": str(self.home),
                "event": {"toolName": "bash", "input": {"command": "echo hi"}},
            }
        ]
        (self.home / "events.json").write_text(json.dumps(events))
        (self.home / "harness.ts").write_text(GuardTest.HARNESS)
        guard = self.installer.guard_targets(SPEC)[0]
        proc = subprocess.run(
            [
                str(bun),
                str(self.home / "harness.ts"),
                str(guard),
                str(self.home / "events.json"),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertIn("did not run", json.loads(proc.stdout)[0])


if __name__ == "__main__":
    unittest.main()
