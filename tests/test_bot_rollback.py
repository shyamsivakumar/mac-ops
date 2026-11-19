import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))

spec = importlib.util.spec_from_file_location(
    "bot_rollback", ROOT / "scripts" / "bot_rollback.py"
)
bot_rollback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot_rollback)

SHA = "1f0d1a3a805efa235acc383ba768c7e317313bd3"


def _entry(bot_id="bot1", **extra):
    entry = {
        "id": bot_id,
        "label": f"Bot {bot_id}",
        "rollbackSha": SHA,
        "liveRef": "origin/paper-live",
        "rollbackCommand": ["node", "scripts/promote.cjs", "--break-glass-rollback"],
        "healthCommand": ["node", "scripts/health.cjs"],
    }
    entry.update(extra)
    return entry


def _ledger(*entries):
    return {"schemaVersion": 1, "bots": list(entries)}


class ParseLedgerTests(unittest.TestCase):
    def test_reads_every_bot(self):
        bots = bot_rollback.parse_ledger(json.dumps(_ledger(_entry("bot1"), _entry("bot2"))))
        self.assertEqual([bot.id for bot in bots], ["bot1", "bot2"])
        self.assertEqual(bots[0].rollback_sha, SHA)
        self.assertEqual(bots[0].live_ref, "origin/paper-live")
        self.assertEqual(bots[0].rollback_command[-1], "--break-glass-rollback")

    def test_rejects_a_sha_that_is_not_a_commit(self):
        with self.assertRaises(bot_rollback.LedgerError):
            bot_rollback.parse_ledger(json.dumps(_ledger(_entry(rollbackSha="abc"))))

    def test_rejects_an_unknown_schema_version(self):
        raw = json.dumps(_ledger(_entry()))
        raw = raw.replace('"schemaVersion": 1', '"schemaVersion": 2')
        with self.assertRaises(bot_rollback.LedgerError):
            bot_rollback.parse_ledger(raw)

    def test_rejects_a_bot_without_a_rollback_command(self):
        entry = _entry()
        del entry["rollbackCommand"]
        with self.assertRaises(bot_rollback.LedgerError):
            bot_rollback.parse_ledger(json.dumps(_ledger(entry)))

    def test_rejects_a_bot_without_a_health_command(self):
        entry = _entry()
        entry["healthCommand"] = []
        with self.assertRaises(bot_rollback.LedgerError):
            bot_rollback.parse_ledger(json.dumps(_ledger(entry)))

    def test_rejects_the_same_bot_twice(self):
        with self.assertRaises(bot_rollback.LedgerError):
            bot_rollback.parse_ledger(json.dumps(_ledger(_entry("bot1"), _entry("bot1"))))

    def test_rejects_a_ledger_with_no_bots(self):
        with self.assertRaises(bot_rollback.LedgerError):
            bot_rollback.parse_ledger(json.dumps({"schemaVersion": 1, "bots": []}))

    def test_rejects_a_ledger_that_is_not_json(self):
        with self.assertRaises(bot_rollback.LedgerError):
            bot_rollback.parse_ledger("not json")


class ReadLedgerTests(unittest.TestCase):
    def test_a_missing_ledger_is_reported(self):
        with self.assertRaises(bot_rollback.LedgerError):
            bot_rollback.read_ledger(TMP / "bot-rollback-does-not-exist.json")


class DryRunTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="bot-rollback-repo-", dir=TMP))
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        readme = self.repo / "README.md"
        readme.write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "README.md"], check=True, env=env)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "-m", "one"], check=True, env=env)
        self.sha = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        subprocess.run(["git", "-C", str(self.repo), "branch", "paper-live"], check=True)
        self.ledger = self.repo / "rollback.json"
        self.ledger.write_text(
            json.dumps(_ledger(_entry(rollbackSha=self.sha, liveRef="paper-live"))), encoding="utf-8"
        )

    def test_the_dry_run_prints_the_exact_steps_for_each_bot(self):
        code = bot_rollback.main(
            ["--dry-run", "--srw-repo", str(self.repo), "--ledger", str(self.ledger)]
        )
        self.assertEqual(code, 0)

    def test_the_dry_run_names_the_rollback_and_the_health_check(self):
        lines = bot_rollback.describe(
            bot_rollback.read_ledger(self.ledger)[0], self.repo, self.sha
        )
        text = "\n".join(lines)
        self.assertIn(f"recorded rollback SHA: {self.sha}", text)
        self.assertIn("node scripts/promote.cjs --break-glass-rollback " + self.sha, text)
        self.assertIn("node scripts/health.cjs", text)
        self.assertIn(f"paper-live = {self.sha}", text)

    def test_an_unknown_bot_is_reported(self):
        code = bot_rollback.main(
            ["--dry-run", "--bot", "bot9", "--srw-repo", str(self.repo), "--ledger", str(self.ledger)]
        )
        self.assertEqual(code, 1)

    def test_a_missing_ledger_is_reported(self):
        code = bot_rollback.main(
            ["--dry-run", "--srw-repo", str(self.repo), "--ledger", str(self.repo / "missing.json")]
        )
        self.assertEqual(code, 1)

    def test_both_modes_at_once_are_refused(self):
        with self.assertRaises(SystemExit):
            bot_rollback.main(["--dry-run", "--execute"])


class ExecuteTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="bot-rollback-exec-", dir=TMP))
        self.ledger = self.repo / "rollback.json"

    def _write(self, rollback_command, health_command):
        self.ledger.write_text(
            json.dumps(_ledger(_entry(rollbackSha=SHA, liveRef=None,
                                      rollbackCommand=rollback_command,
                                      healthCommand=health_command))),
            encoding="utf-8",
        )

    def test_the_rollback_runs_before_the_health_check(self):
        order = self.repo / "order.txt"
        self._write(
            ["/bin/sh", "-c", f"echo rollback >> {order}"],
            ["/bin/sh", "-c", f"echo health >> {order}"],
        )
        code = bot_rollback.main(
            ["--execute", "--srw-repo", str(self.repo), "--ledger", str(self.ledger)]
        )
        self.assertEqual(code, 0)
        self.assertEqual(order.read_text(encoding="utf-8").split(), ["rollback", "health"])

    def test_a_failed_rollback_stops_the_health_check(self):
        order = self.repo / "order.txt"
        self._write(
            ["/bin/sh", "-c", f"echo rollback >> {order}; exit 3"],
            ["/bin/sh", "-c", f"echo health >> {order}"],
        )
        code = bot_rollback.main(
            ["--execute", "--srw-repo", str(self.repo), "--ledger", str(self.ledger)]
        )
        self.assertEqual(code, 1)
        self.assertEqual(order.read_text(encoding="utf-8").split(), ["rollback"])


if __name__ == "__main__":
    unittest.main()
