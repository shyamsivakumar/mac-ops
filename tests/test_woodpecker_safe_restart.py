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
        self.assertIn("--hold-file", text)
        self.assertIn('wait_agents_ready "$target"', text)
        drain_idx = text.index('--hold-file "$hold_file"')
        run_idx = text.index('"$@"')
        ready_idx = text.index('wait_agents_ready "$target"')
        resume_idx = text.index('"$drain" --resume')
        self.assertLess(drain_idx, run_idx)
        self.assertLess(run_idx, ready_idx)
        self.assertLess(ready_idx, resume_idx)

    def test_drain_writes_hold_file_at_pause_claim(self):
        text = (WP / "drain-agent.sh").read_text(encoding="utf-8")
        self.assertIn("--hold-file", text)
        claim = text.index("claim_pause_txn")
        hold_write = text.index('printf \'%s\\n\' "$opid" >"$HOLD_FILE"', claim)
        idle = text.index("wait_agents_idle", claim)
        self.assertLess(hold_write, idle)

    def test_watchdog_rechecks_idle_when_reusing_held_drain(self):
        path = WP / "watchdog.sh"
        text = path.read_text(encoding="utf-8")
        self.assertIn("watchdog-drain-opid", text)
        self.assertIn("persist_held_drain_opid", text)
        self.assertIn("resume_held_drain_if_ready", text)
        self.assertIn("wait_agents_ready", text)
        self.assertIn("ensure_idle_before_colima_kick", text)
        self.assertIn("wait_agents_idle", text)
        self.assertIn("Reusing held drain", text)
        self.assertIn('--hold-file "$DRAIN_HOLD_FILE"', text)
        self.assertNotRegex(text, r"compose\s+[^\n]*force-recreate")
        restart_fn = text.index("restart_colima()")
        reuse = text.index("Reusing held drain", restart_fn)
        idle_gate = text.index("ensure_idle_before_colima_kick", restart_fn)
        kick = text.index(
            'kickstart -k "$DOMAIN/com.shyamsivakumar.colima-woodpecker"', restart_fn
        )
        self.assertLess(reuse, idle_gate)
        self.assertLess(idle_gate, kick)
        hold_arg = text.index('--hold-file "$DRAIN_HOLD_FILE"', restart_fn)
        self.assertLess(hold_arg, kick)

    def test_common_exports_wait_helpers(self):
        text = (WP / "common.sh").read_text(encoding="utf-8")
        self.assertIn("wait_agents_ready()", text)
        self.assertIn("wait_agents_idle()", text)
        self.assertIn("agents_contact_fresh", text)
        self.assertIn("target_process_ready", text)
        self.assertIn("last_contact", text)
        self.assertIn("srw_deploy_running", text)

    def test_install_to_m1_ships_safe_restart(self):
        text = (WP / "install-to-m1.sh").read_text(encoding="utf-8")
        self.assertIn("safe-restart.sh", text)
        self.assertIn("drain-agent.sh", text)


if __name__ == "__main__":
    unittest.main()
