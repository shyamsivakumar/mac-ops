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
        # the regex matches ls too; the exemption for a bare ls lives in the guard
        self.assertTrue(text.search("ls -la ~/.ssh"))
        guard_text = (ROOT / "runtime/agents/deny-guard.ts").read_text()
        self.assertIn('const bareLs = /^\\s*ls\\b/', guard_text)

        force, main = (re.compile(SPEC["bash_denies"][0][0]),
                       re.compile(SPEC["bash_denies"][1][0]))
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
        ):
            self.assertTrue(force.search(denied) or main.search(denied), denied)
        for allowed in (
            "git push origin t3/deny-rules",
            "git push origin t3/main-fix",
            "git push origin feature/main-work",
            "git push --set-upstream origin t3/x",
            "git -C /tmp/repo push origin t3/deny-rules",
        ):
            self.assertFalse(force.search(allowed), allowed)
            self.assertFalse(main.search(allowed), allowed)

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
    def run_hook(self, payload):
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_denies_unpinned_merge(self):
        for command in (
            "gh pr merge 531",
            "gh pr merge 531 --squash",
            "gh pr merge 531 -R shyamsivakumar/mac-ops --squash --delete-branch",
        ):
            out = self.run_hook(
                {"tool_name": "Bash", "tool_input": {"command": command}}
            )
            decision = json.loads(out)["hookSpecificOutput"]
            self.assertEqual(decision["permissionDecision"], "deny", command)

    def test_allows_pinned_merge(self):
        command = (
            "gh pr merge 531 -R shyamsivakumar/mac-ops --squash "
            "--match-head-commit 5d3f2c1a4b5e6f70819283a4b5c6d7e8f9011223"
        )
        self.assertEqual(
            self.run_hook({"tool_name": "Bash", "tool_input": {"command": command}}), ""
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


class GuardTest(unittest.TestCase):
    """The installed guard file, loaded the way pi loads it, on real events."""

    HARNESS = """
const guard = await import(process.argv[2]);
const events = JSON.parse(await Bun.file(process.argv[3]).text());
let handler;
guard.default({ on: (name, fn) => { if (name === "tool_call") handler = fn; } });
const out = [];
for (const item of events) {
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
        cases = [
            ({"toolName": "read", "input": {"path": ascend}}, True),
            ({"toolName": "edit", "input": {"path": str(fake_env)}}, True),
            ({"toolName": "write", "input": {"path": str(fake_env), "content": "x"}}, True),
            ({"toolName": "bash", "input": {"command": f"cat {fake_env}"}}, True),
            ({"toolName": "bash", "input": {"command": "git push --force origin main"}}, True),
            ({"toolName": "bash", "input": {"command": "git push origin main"}}, True),
            ({"toolName": "bash", "input": {"command": "gh pr merge 531 --squash"}}, True),
            (
                {
                    "toolName": "bash",
                    "input": {
                        "command": "gh pr merge 531 --squash --match-head-commit " + "a" * 40
                    },
                },
                False,
            ),
            (
                {
                    "toolName": "bash",
                    "input": {"command": "git push -u origin t3/deny-rules"},
                },
                False,
            ),
            ({"toolName": "ls", "input": {"path": str(fake_env)}}, False),
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
            ),
        ]
        events = [{"cwd": str(scratch), "event": event} for event, _ in cases]
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
        for (event, want_block), reason in zip(cases, reasons):
            self.assertEqual(
                reason is not None,
                want_block,
                f"{event} -> {reason}",
            )
            if want_block:
                self.assertIn("mac-ops deny rules (#530)", reason)


if __name__ == "__main__":
    unittest.main()
