import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))

spec = importlib.util.spec_from_file_location(
    "bot_rollback", ROOT / "scripts" / "bot_rollback.py"
)
bot_rollback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot_rollback)

SHA = "1f0d1a3a805efa235acc383ba768c7e317313bd3"
OTHER_SHA = "f8cb4d92c677c5c67ba0e160859fab19165d1785"


def _entry(bot_id="bot1", **extra):
    entry = {
        "id": bot_id,
        "label": f"Bot {bot_id}",
        "repository": "~/Code/strategy-replay-workbench",
        "liveRef": "origin/paper-live",
        "rollbackSha": None,
        "rollbackCommands": [["node", "scripts/promote.cjs", "--break-glass-rollback", "{sha}"]],
        "healthUrlEnv": "BOT1_HEALTH_URL",
        "healthPath": "/health",
        "healthCommand": None,
    }
    entry.update(extra)
    return entry


def _config(*entries):
    return {"schemaVersion": 1, "bots": list(entries)}


class ParseConfigTests(unittest.TestCase):
    def test_reads_every_bot(self):
        bots = bot_rollback.parse_config(json.dumps(_config(_entry("bot1"), _entry("bot2"))))
        self.assertEqual([bot.id for bot in bots], ["bot1", "bot2"])
        self.assertEqual(bots[0].rollback_commands, [["node", "scripts/promote.cjs", "--break-glass-rollback", "{sha}"]])
        self.assertEqual(bots[0].health_url_env, "BOT1_HEALTH_URL")

    def test_rejects_a_sha_that_is_not_a_commit(self):
        with self.assertRaises(bot_rollback.ConfigError):
            bot_rollback.parse_config(json.dumps(_config(_entry(rollbackSha="abc"))))

    def test_rejects_an_unknown_schema_version(self):
        raw = json.dumps(_config(_entry())).replace('"schemaVersion": 1', '"schemaVersion": 2')
        with self.assertRaises(bot_rollback.ConfigError):
            bot_rollback.parse_config(raw)

    def test_rejects_the_same_bot_twice(self):
        with self.assertRaises(bot_rollback.ConfigError):
            bot_rollback.parse_config(json.dumps(_config(_entry("bot1"), _entry("bot1"))))

    def test_rejects_a_config_with_no_bots(self):
        with self.assertRaises(bot_rollback.ConfigError):
            bot_rollback.parse_config(json.dumps({"schemaVersion": 1, "bots": []}))

    def test_rejects_a_config_that_is_not_json(self):
        with self.assertRaises(bot_rollback.ConfigError):
            bot_rollback.parse_config("not json")

    def test_rejects_a_nul_byte_in_a_value(self):
        with self.assertRaises(bot_rollback.ConfigError):
            bot_rollback.parse_config(json.dumps(_config(_entry(liveRef="origin/paper\x00live"))))

    def test_rejects_a_nul_byte_in_a_command(self):
        with self.assertRaises(bot_rollback.ConfigError):
            bot_rollback.parse_config(json.dumps(_config(_entry(rollbackCommands=[["node", "a\x00b"]]))))

    def test_a_bot_may_have_no_rollback_command(self):
        bots = bot_rollback.parse_config(json.dumps(_config(_entry(rollbackCommands=None))))
        self.assertIsNone(bots[0].rollback_commands)


class ReadConfigTests(unittest.TestCase):
    def test_a_missing_config_is_reported(self):
        with self.assertRaises(bot_rollback.ConfigError):
            bot_rollback.read_config(TMP / "bot-rollback-does-not-exist.json")

    def test_a_config_that_is_not_utf8_is_reported(self):
        path = TMP / "bot-rollback-not-utf8.json"
        path.write_bytes(b'{"schemaVersion": 1, "bots": [\xff]}')
        try:
            with self.assertRaises(bot_rollback.ConfigError):
                bot_rollback.read_config(path)
        finally:
            path.unlink()


class RepoFixture:
    """A checkout with a remote-tracking ref that keeps its own history."""

    def __init__(self):
        self.path = Path(tempfile.mkdtemp(prefix="bot-rollback-repo-", dir=TMP))
        self.env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        self.git("init", "-q", str(self.path))
        readme = self.path / "README.md"
        readme.write_text("one\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-q", "-m", "one")
        self.first = self.rev("HEAD")
        readme.write_text("two\n", encoding="utf-8")
        self.git("commit", "-q", "-a", "-m", "two")
        self.second = self.rev("HEAD")
        self.git("update-ref", "--create-reflog", "refs/remotes/origin/paper-live", self.first)
        self.git("update-ref", "refs/remotes/origin/paper-live", self.second)

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.path), *args], check=True, capture_output=True, env=self.env)

    def rev(self, ref):
        return subprocess.run(
            ["git", "-C", str(self.path), "rev-parse", "--verify", f"{ref}^{{commit}}"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()


class DryRunTests(unittest.TestCase):
    def setUp(self):
        self.repo = RepoFixture()
        self.config = self.repo.path / "config.json"
        self.sentinel = self.repo.path / "sentinel.txt"
        self._write(_entry(
            repository=str(self.repo.path),
            rollbackCommands=[["touch", str(self.sentinel)]],
        ))
        os.environ["BOT1_HEALTH_URL"] = "https://bot1.example.test"

    def tearDown(self):
        os.environ.pop("BOT1_HEALTH_URL", None)

    def _write(self, *entries):
        self.config.write_text(json.dumps(_config(*entries)), encoding="utf-8")

    def _run(self, *args):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = bot_rollback.main(["--dry-run", "--config", str(self.config), *args])
        return code, buffer.getvalue()

    def test_the_dry_run_prints_the_exact_steps_for_the_bot(self):
        code, output = self._run()
        repo = str(self.repo.path.resolve())
        self.assertEqual(code, 0)
        self.assertIn(f"recorded rollback SHA: {self.repo.first}", output)
        self.assertIn(f"origin/paper-live = {self.repo.second}", output)
        self.assertIn(
            f"step precheck: git -C {repo} merge-base --is-ancestor "
            f"{self.repo.first} {self.repo.second}",
            output,
        )
        self.assertIn(f"step rollback: touch {self.sentinel} {self.repo.first}", output)
        self.assertIn("step health check: curl -fsS https://bot1.example.test/health", output)

    def test_the_dry_run_changes_nothing(self):
        self._run()
        self.assertFalse(self.sentinel.exists())

    def test_the_dry_run_reports_a_bot_it_cannot_resolve(self):
        self._write(_entry(repository=str(self.repo.path), liveRef=None, rollbackCommands=None))
        code, output = self._run()
        self.assertEqual(code, 1)
        self.assertIn("problem: no live ref is recorded for this bot", output)
        self.assertIn("problem: no rollback command is recorded for this bot", output)
        self.assertIn("problem: no rollback SHA is recorded for this bot", output)

    def test_the_dry_run_reports_a_missing_health_url(self):
        os.environ.pop("BOT1_HEALTH_URL", None)
        code, output = self._run()
        self.assertEqual(code, 1)
        self.assertIn("problem: BOT1_HEALTH_URL is not set, so there is no health check", output)

    def test_the_dry_run_reports_a_sha_the_checkout_does_not_hold(self):
        self._write(_entry(repository=str(self.repo.path), rollbackSha=OTHER_SHA))
        code, output = self._run()
        self.assertEqual(code, 1)
        self.assertIn(f"problem: the checkout does not hold {OTHER_SHA}", output)

    def test_an_unknown_bot_is_reported(self):
        code, output = self._run("--bot", "bot9")
        self.assertEqual(code, 1)
        self.assertNotIn("step rollback", output)

    def test_a_missing_config_is_reported(self):
        code = bot_rollback.main(["--dry-run", "--config", str(self.repo.path / "missing.json")])
        self.assertEqual(code, 1)

    def test_both_modes_at_once_are_refused(self):
        with self.assertRaises(SystemExit):
            bot_rollback.main(["--dry-run", "--execute"])

    def test_a_relative_repository_path_is_resolved_once(self):
        self._write(_entry(
            repository=os.path.relpath(self.repo.path, TMP),
            rollbackCommands=[["touch", str(self.sentinel)]],
        ))
        previous = os.getcwd()
        os.chdir(TMP)
        try:
            code, output = self._run()
        finally:
            os.chdir(previous)
        repo = str(self.repo.path.resolve())
        self.assertEqual(code, 0)
        self.assertIn(f"step precheck: git -C {repo} merge-base", output)
        self.assertNotIn(f"git -C {os.path.relpath(self.repo.path, TMP)}/", output)


class ExecuteTests(unittest.TestCase):
    def setUp(self):
        self.repo = RepoFixture()
        self.config = self.repo.path / "config.json"
        self.order = self.repo.path / "order.txt"
        os.environ["BOT1_HEALTH_URL"] = "https://bot1.example.test"

    def tearDown(self):
        os.environ.pop("BOT1_HEALTH_URL", None)

    def _write(self, *entries):
        self.config.write_text(json.dumps(_config(*entries)), encoding="utf-8")

    def _run(self, *args):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = bot_rollback.main(["--execute", "--config", str(self.config), *args])
        return code, buffer.getvalue()

    def test_the_rollback_runs_before_the_health_check(self):
        self._write(_entry(
            repository=str(self.repo.path),
            rollbackCommands=[["/bin/sh", "-c", f"echo rollback >> {self.order}"]],
            healthCommand=["/bin/sh", "-c", f"echo health >> {self.order}"],
        ))
        code, _ = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(self.order.read_text(encoding="utf-8").split(), ["rollback", "health"])

    def test_a_failed_rollback_stops_the_run(self):
        second = self.repo.path / "second.txt"
        self._write(
            _entry(
                repository=str(self.repo.path),
                rollbackCommands=[["/bin/sh", "-c", f"echo rollback >> {self.order}; exit 3"]],
            ),
            _entry(
                bot_id="bot2",
                label="Bot 2",
                repository=str(self.repo.path),
                liveRef="origin/paper-live",
                rollbackCommands=[["touch", str(second)]],
                healthCommand=["true"],
            ),
        )
        code, _ = self._run()
        self.assertEqual(code, 1)
        self.assertFalse(second.exists())

    def test_nothing_runs_when_a_bot_cannot_be_resolved(self):
        self._write(_entry(repository=str(self.repo.path), liveRef=None, rollbackCommands=None))
        code, _ = self._run()
        self.assertEqual(code, 1)
        self.assertFalse(self.order.exists())


if __name__ == "__main__":
    unittest.main()
