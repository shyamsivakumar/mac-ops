"""MO-121: drain-before-restart contracts for Woodpecker helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WP = ROOT / "scripts" / "woodpecker-ci"


class WoodpeckerSafeRestartTests(unittest.TestCase):
    def test_safe_restart_script_exists_and_drains_first(self):
        path = WP / "safe-restart.sh"
        self.assertTrue(path.is_file(), path)
        text = path.read_text(encoding="utf-8")
        self.assertIn("drain-agent.sh", text)
        self.assertIn("DRAIN_OPID", text)
        self.assertIn("--resume", text)
        self.assertIn('"$drain" "$target"', text)
        self.assertIn("wait_agents_ready", text)
        # Command runs only after a successful drain with an opid.
        drain_idx = text.index('"$drain" "$target"')
        run_idx = text.index('"$@"')
        ready_idx = text.index('wait_agents_ready "$target"')
        resume_idx = text.index('"$drain" --resume')
        self.assertLess(drain_idx, run_idx)
        self.assertLess(run_idx, ready_idx)
        self.assertLess(ready_idx, resume_idx)

    def test_watchdog_persists_drain_and_retries_resume(self):
        path = WP / "watchdog.sh"
        text = path.read_text(encoding="utf-8")
        self.assertIn("drain-agent.sh", text)
        self.assertIn("kickstart -k", text)
        self.assertIn("safe-restart.sh", text)
        self.assertIn("--no-recreate", text)
        self.assertIn("watchdog-drain-opid", text)
        self.assertIn("persist_held_drain_opid", text)
        self.assertIn("resume_held_drain_if_ready", text)
        self.assertIn("wait_agents_ready", text)
        self.assertIn("Reusing held drain", text)
        self.assertNotRegex(text, r"compose\s+[^\n]*force-recreate")
        # Drain must appear in the Colima recovery path before kickstart -k.
        restart_fn = text.index("restart_colima()")
        drain_call = text.index('"$drain" all', restart_fn)
        kick = text.index(
            'kickstart -k "$DOMAIN/com.shyamsivakumar.colima-woodpecker"', restart_fn
        )
        self.assertLess(drain_call, kick)
        # Persist happens before kickstart; resume helper runs at end of pass.
        persist = text.index("persist_held_drain_opid", restart_fn)
        self.assertLess(persist, kick)
        resume_helper = text.index("\nresume_held_drain_if_ready\n")
        start_missing_call = text.rindex("\nstart_missing_services\n")
        self.assertLess(start_missing_call, resume_helper)

    def test_common_exports_wait_agents_ready(self):
        text = (WP / "common.sh").read_text(encoding="utf-8")
        self.assertIn("wait_agents_ready()", text)
        self.assertIn("agents_contact_fresh", text)
        self.assertIn("target_process_ready", text)
        self.assertIn("last_contact", text)

    def test_install_to_m1_ships_safe_restart(self):
        text = (WP / "install-to-m1.sh").read_text(encoding="utf-8")
        self.assertIn("safe-restart.sh", text)
        self.assertIn("drain-agent.sh", text)


if __name__ == "__main__":
    unittest.main()
