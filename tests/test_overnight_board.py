"""Tests for the overnight board's rule about failing checks.

Only an agent check blocks a pull request. Every other check is external:
it stays visible on the item and in the reason, and it never changes the
group or the action.

`overnight` is a script without a .py suffix, so it is loaded by path.
"""
import importlib.util
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERNIGHT = ROOT / "coordinator" / "overnight" / "overnight"

overnight = None


def load_overnight():
    global overnight
    if overnight is not None:
        return overnight
    loader = SourceFileLoader("overnight_board", str(OVERNIGHT))
    spec = importlib.util.spec_from_loader("overnight_board", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    overnight = module
    return module


def status_row(context, state, app=""):
    """One commit status of a pull request, as the rollup carries it."""
    return {
        "__typename": "StatusContext",
        "context": context,
        "state": state,
        "app": {"slug": app} if app else None,
    }


def check_run_row(name, conclusion, app=""):
    """One check run of a pull request, as the rollup carries it."""
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": "COMPLETED",
        "conclusion": conclusion,
        "app": {"slug": app} if app else None,
    }


class CheckRowsTests(unittest.TestCase):
    def setUp(self):
        self.overnight = load_overnight()

    def test_a_failed_status_keeps_its_name_and_state(self):
        rows = self.overnight.check_rows([status_row("Vercel", "FAILURE")])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Vercel")
        self.assertEqual(rows[0]["context"], "Vercel")
        self.assertEqual(rows[0]["state"], "FAILURE")
        self.assertEqual(rows[0]["bucket"], "fail")

    def test_a_failed_check_run_keeps_its_app(self):
        rows = self.overnight.check_rows(
            [check_run_row("Vercel Preview Comments", "failure", "vercel")]
        )
        self.assertEqual(rows[0]["name"], "Vercel Preview Comments")
        self.assertEqual(rows[0]["app"], "vercel")
        self.assertEqual(rows[0]["state"], "FAILURE")
        self.assertEqual(rows[0]["bucket"], "fail")

    def test_a_cancelled_run_is_not_a_failure(self):
        rows = self.overnight.check_rows(
            [check_run_row("a run", "cancelled", "vercel")]
        )
        self.assertEqual(rows[0]["bucket"], "skipping")

    def test_a_pending_status_is_pending(self):
        rows = self.overnight.check_rows([status_row("srw/agent-check", "PENDING")])
        self.assertEqual(rows[0]["bucket"], "pending")


class FailingCheckTests(unittest.TestCase):
    def setUp(self):
        self.overnight = load_overnight()

    def test_only_an_external_failure_does_not_block(self):
        item = {}
        rows = self.overnight.check_rows([status_row("Vercel", "FAILURE")])
        blocked = self.overnight.apply_checks(item, rows, "FFBT")
        self.assertFalse(blocked)
        self.assertEqual(item["checks"]["failed"], [])
        self.assertEqual(item["externalChecks"], ["Vercel"])

    def test_a_failed_agent_check_still_blocks(self):
        item = {}
        rows = self.overnight.check_rows(
            [status_row("srw/agent-check", "FAILURE")]
        )
        blocked = self.overnight.apply_checks(item, rows, "SRW")
        self.assertTrue(blocked)
        self.assertEqual(item["checks"]["failed"], ["srw/agent-check (FAILURE)"])
        self.assertEqual(item["externalChecks"], [])

    def test_a_mixed_failure_blocks_and_keeps_the_external_one_visible(self):
        item = {}
        rows = self.overnight.check_rows(
            [
                status_row("Vercel", "FAILURE"),
                status_row("srw/agent-check", "FAILURE"),
            ]
        )
        blocked = self.overnight.apply_checks(item, rows, "SRW")
        self.assertTrue(blocked)
        self.assertEqual(item["checks"]["failed"], ["srw/agent-check (FAILURE)"])
        self.assertEqual(item["externalChecks"], ["Vercel"])

    def test_a_repository_publisher_app_is_an_agent_check(self):
        rows = self.overnight.check_rows(
            [
                status_row("mo/agent-check", "SUCCESS", "mac-ops-agent-check"),
                check_run_row("a check", "failure", "mac-ops-agent-check"),
            ]
        )
        names = self.overnight.agent_check_names("MO")
        apps = self.overnight.publisher_apps(rows, names)
        self.assertEqual(apps, frozenset({"mac-ops-agent-check"}))
        self.assertTrue(
            self.overnight.is_agent_check(rows[1], names, apps)
        )
        self.assertFalse(
            self.overnight.is_agent_check(
                self.overnight.check_rows([status_row("Vercel", "FAILURE")])[0],
                names,
                apps,
            )
        )

    def test_a_cancelled_check_is_not_a_failure(self):
        rows = self.overnight.check_rows(
            [check_run_row("a run", "cancelled", "vercel")]
        )
        state = self.overnight.check_verdict(rows, "FFBT")
        self.assertEqual(state["failed"], [])
        self.assertEqual(state["external"], [])
        self.assertFalse(state["blocks"])


class PullRequestActionMetricsTests(unittest.TestCase):
    def setUp(self):
        self.overnight = load_overnight()

    def test_states_count_actions_and_choose_oldest_per_state(self):
        rows = [
            {"state": "draft", "action": "finish", "repo": "a/r", "number": 1,
             "head": "h1", "updatedAt": "2026-11-13"},
            {"state": "draft", "action": "finish", "repo": "a/r", "number": 2,
             "head": "h2", "updatedAt": "2026-11-14"},
            {"state": "gate-live", "action": "none", "repo": "a/r", "number": 3,
             "head": "h3", "updatedAt": "2026-11-12"},
        ]
        states, no_action, oldest = self.overnight.pr_state_metrics(rows)
        self.assertEqual(states, {"draft": 2, "gate-live": 1})
        self.assertEqual(no_action, 1)
        self.assertEqual(oldest["draft"]["number"], 1)

    def test_dispatch_runs_only_pull_request_action_commands(self):
        from unittest.mock import patch
        rows = [
            {"kind": "ticket", "action": "start", "actionCommand": "ticket start x"},
            {"kind": "pull-request", "action": "finish", "repo": "a/r", "number": 4,
             "actionCommand": "coordq pr-action finish a/r#4 --head abc"},
            {"kind": "pull-request", "action": "needs-you", "repo": "a/r", "number": 5},
        ]
        with patch.object(self.overnight.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "queued\n"
            self.assertTrue(self.overnight.dispatch_shift_actions(rows, 10**12))
            run.assert_called_once()

    def test_a_passing_agent_check_does_not_block(self):
        rows = self.overnight.check_rows(
            [status_row("srw/agent-check", "SUCCESS")]
        )
        state = self.overnight.check_verdict(rows, "SRW")
        self.assertEqual(state["failed"], [])
        self.assertFalse(state["blocks"])


if __name__ == "__main__":
    unittest.main()
