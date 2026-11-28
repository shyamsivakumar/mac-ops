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

    def test_a_passing_agent_check_does_not_block(self):
        rows = self.overnight.check_rows(
            [status_row("srw/agent-check", "SUCCESS")]
        )
        state = self.overnight.check_verdict(rows, "SRW")
        self.assertEqual(state["failed"], [])
        self.assertFalse(state["blocks"])


class T3ProjectListPaginationTest(unittest.TestCase):
    def _load(self, name, relpath):
        spec = importlib.util.spec_from_file_location(name, str(ROOT / relpath))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_turn_cap_paginates_and_guards_loops(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        tc = self._load("turn_cap_under_test", "coordinator/overnight/turn_cap.py")
        calls = []

        def fake_call(cli, tool, args):
            calls.append((cli, tool, dict(args)))
            if "cursor" not in args:
                return {"projects": [{"id": f"mcp:p{i}"} for i in range(20)], "nextCursor": 20}
            return {"projects": [{"id": f"mcp:p{i}"} for i in range(20, 26)], "nextCursor": None}

        tools_out = SimpleNamespace(stdout="t3_project_list t3_thread_list\n")
        with patch.object(tc.subprocess, "run", return_value=tools_out), patch.object(tc, "call", side_effect=fake_call):
            ids = tc.t3_project_ids()
        self.assertEqual((len(ids), ids[-1]), (26, "mcp:p25"))
        self.assertEqual(calls, [("t3mcp", "t3_project_list", {"limit": 100}), ("t3mcp", "t3_project_list", {"limit": 100, "cursor": 20})])

        loop_calls = []
        with patch.object(tc.subprocess, "run", return_value=tools_out), patch.object(
            tc, "call", side_effect=lambda c, t, a: loop_calls.append(dict(a)) or {"projects": [{"id": "mcp:x"}], "nextCursor": 20}
        ):
            self.assertEqual(tc.t3_project_ids(), ["mcp:x", "mcp:x"])
        self.assertEqual(len(loop_calls), 2)

        with patch.object(tc.subprocess, "run", return_value=SimpleNamespace(stdout="t3_thread_list\n")):
            self.assertEqual(tc.t3_project_ids(), tc.T3_FALLBACK_PROJECTS)

    def test_settle_finished_paginates_and_fails_on_bad_page(self):
        from unittest.mock import patch

        sf = self._load("settle_finished_under_test", "scripts/settle_finished.py")
        calls = []

        def fake_t3(tool, args):
            calls.append((tool, dict(args)))
            if "cursor" not in args:
                return {"projects": [{"id": f"mcp:p{i}", "title": f"p{i}", "workspaceRoot": f"/w/{i}"} for i in range(20)], "nextCursor": 20}
            return {"projects": [{"id": "mcp:alpha", "title": "alpha-trader", "workspaceRoot": "/w/alpha"}], "nextCursor": None}

        with patch.object(sf.lane, "t3", side_effect=fake_t3):
            roots = sf.project_roots()
        self.assertEqual((len(roots), roots["mcp:alpha"]), (21, "alpha-trader /w/alpha"))
        self.assertEqual(calls, [("t3_project_list", {"limit": 100}), ("t3_project_list", {"limit": 100, "cursor": 20})])

        with patch.object(sf.lane, "t3", return_value={"projects": None}), self.assertRaises(SystemExit) as exc:
            sf.project_roots()
        self.assertIn("T3 project list", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
