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
        # Command runs only after a successful drain with an opid.
        drain_idx = text.index('"$drain" "$target"')
        run_idx = text.index('"$@"')
        resume_idx = text.index('"$drain" --resume')
        self.assertLess(drain_idx, run_idx)
        self.assertLess(run_idx, resume_idx)

    def test_watchdog_drains_before_colima_kickstart_k(self):
        path = WP / "watchdog.sh"
        text = path.read_text(encoding="utf-8")
        self.assertIn("drain-agent.sh", text)
        self.assertIn("kickstart -k", text)
        self.assertIn("safe-restart.sh", text)
        self.assertIn("--no-recreate", text)
        self.assertNotRegex(text, r"compose\s+[^\n]*force-recreate")
        # Drain must appear in the Colima recovery path before kickstart -k.
        restart_fn = text.index("restart_colima()")
        drain_call = text.index('"$drain" all', restart_fn)
        kick = text.index(
            'kickstart -k "$DOMAIN/com.shyamsivakumar.colima-woodpecker"', restart_fn
        )
        self.assertLess(drain_call, kick)
        # Resume happens after compose services are started (call site, not def).
        resume = text.index('"$drain" --resume "$WATCHDOG_DRAIN_OPID"')
        start_missing_call = text.index("\nstart_missing_services\n")
        self.assertLess(start_missing_call, resume)

    def test_install_to_m1_ships_safe_restart(self):
        text = (WP / "install-to-m1.sh").read_text(encoding="utf-8")
        self.assertIn("safe-restart.sh", text)
        self.assertIn("drain-agent.sh", text)


if __name__ == "__main__":
    unittest.main()
