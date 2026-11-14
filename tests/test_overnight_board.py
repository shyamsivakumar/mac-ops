"""Tests for the overnight board's rule about failing checks.

Only an agent check blocks a pull request. Every other check is external:
it stays visible on the item and in the reason, and it never changes the
group or the action.

`overnight` is a script without a .py suffix, so it is loaded by path.
"""
import importlib.util
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

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


class PullRequestActionTests(unittest.TestCase):
    """Every open pull request is an item with the one action it needs.

    The board reads the checks with the pull request listing, so the
    listing is the only read a test has to stub.
    """

    REPO = "shyamsivakumar/mac-ops"

    def setUp(self):
        self.overnight = load_overnight()
        self.overnight_issues = [
            {
                "repo": self.REPO,
                "number": 1,
                "key": "MO-1",
                "title": "a ticket",
                "stage": "todo",
                "priority": None,
                "problems": [],
            },
            {
                "repo": self.REPO,
                "number": 2,
                "key": "MO-2",
                "title": "a dropped ticket",
                "stage": "todo",
                "priority": None,
                "problems": [],
            },
            {
                "repo": self.REPO,
                "number": 3,
                "key": "MO-3",
                "title": "a held ticket",
                "stage": "todo",
                "priority": None,
                "problems": [],
            },
        ]

    def pull(self, number, head, body, checks=(), draft=False):
        return {
            "number": number,
            "title": f"pull {number}",
            "url": f"https://example/{number}",
            "isDraft": draft,
            "headRefName": f"t3/{number}",
            "headRefOid": head,
            "updatedAt": "2026-11-14T00:00:00Z",
            "body": body,
            "statusCheckRollup": list(checks),
        }

    def collect(self, rows, receipts=None, gated=(), fixed=(), drops=()):
        deadline = time.monotonic() + 60
        queue = {
            "gatedHeads": {f"gate:{self.REPO}#{number}:{head}" for number, head in gated},
            "queuedTickets": set(),
            "fixedHeads": {
                f"fix:{self.REPO}#{number}:{head}": 1 for number, head in fixed
            },
            "error": "",
        }
        with patch.object(
            self.overnight, "read_pull_requests", return_value=(rows, False)
        ), patch.object(
            self.overnight, "read_closed_issues", return_value=([], set(), "")
        ), patch.object(
            self.overnight, "read_queue_state", return_value=queue
        ), patch.object(
            self.overnight,
            "read_live_threads",
            return_value={"ids": set(), "keys": set(), "error": ""},
        ), patch.object(
            self.overnight, "read_gate_report", return_value=("", "", "")
        ):
            return self.overnight.collect_items(
                deadline,
                [(self.REPO, "MO")],
                self.overnight_issues,
                {},
                {},
                list(drops),
                receipts or {},
                None,
                frozenset(),
            )

    def items(self, result):
        found = {}
        for name in ("failing", "gate_pass", "in_flight"):
            for item in result[name]:
                if item["kind"] == "pull-request":
                    found[item["number"]] = item
        return found

    def test_a_check_line_that_says_fail_is_a_fix(
        self,
    ):
        head = "a" * 40
        result = self.collect(
            [self.pull(10, head, f"Refs #1\nBuilder check: FAIL {head}")]
        )
        item = self.items(result)[10]
        self.assertEqual(item["action"], "fix")
        self.assertEqual(item["actionReason"], "its Builder check says FAIL")

    def test_a_check_line_that_says_pending_is_a_fix(self):
        head = "b" * 40
        result = self.collect(
            [self.pull(11, head, f"Refs #1\nBuilder check: PENDING {head}")]
        )
        self.assertEqual(self.items(result)[11]["action"], "fix")

    def test_a_missing_check_line_is_a_fix(self):
        result = self.collect([self.pull(12, "c" * 40, "Refs #1")])
        item = self.items(result)[12]
        self.assertEqual(item["action"], "fix")
        self.assertEqual(
            item["actionReason"],
            "its description carries no Builder check line",
        )

    def test_a_check_line_for_another_head_is_a_fix(self):
        head, other = "d" * 40, "e" * 40
        result = self.collect(
            [self.pull(13, head, f"Refs #1\nBuilder check: PASS {other}")]
        )
        item = self.items(result)[13]
        self.assertEqual(item["action"], "fix")
        self.assertEqual(
            item["actionReason"], "its Builder check does not name this head"
        )

    def test_a_passing_check_line_with_no_gate_receipt_is_a_gate(self):
        head = "f" * 40
        result = self.collect(
            [self.pull(14, head, f"Refs #1\nBuilder check: PASS {head}")]
        )
        item = self.items(result)[14]
        self.assertEqual(item["action"], "gate")
        self.assertEqual(item["actionCommand"], f"coordq gate {self.REPO}#14")

    def test_a_passing_agent_check_on_the_head_is_a_gate(self):
        head = "1" * 40
        checks = [
            {
                "__typename": "StatusContext",
                "context": "srw/agent-check",
                "state": "SUCCESS",
            }
        ]
        result = self.collect([self.pull(15, head, "Refs #1", checks)])
        self.assertEqual(self.items(result)[15]["action"], "gate")

    def test_a_failed_check_on_the_head_is_a_fix(self):
        checks = [
            {
                "__typename": "StatusContext",
                "context": "srw/agent-check",
                "state": "FAILURE",
            }
        ]
        result = self.collect(
            [self.pull(16, "2" * 40, f"Refs #1\nBuilder check: PASS {'2' * 40}", checks)]
        )
        item = self.items(result)[16]
        self.assertEqual(item["action"], "fix")
        self.assertIn("the check on this head failed", item["actionReason"])

    def test_a_head_already_on_its_way_needs_nothing(self):
        head = "3" * 40
        result = self.collect(
            [self.pull(17, head, f"Refs #1\nBuilder check: PASS {head}")],
            gated=[(17, head)],
        )
        self.assertEqual(self.items(result)[17]["action"], "none")

    def test_findings_already_sent_need_nothing(self):
        checks = [
            {
                "__typename": "StatusContext",
                "context": "srw/agent-check",
                "state": "FAILURE",
            }
        ]
        head = "4" * 40
        result = self.collect(
            [self.pull(18, head, f"Refs #1\nBuilder check: FAIL {head}", checks)],
            fixed=[(18, head)],
        )
        item = self.items(result)[18]
        self.assertEqual(item["action"], "none")
        self.assertEqual(
            item["actionReason"], "the findings for this head were already sent"
        )

    def test_a_dropped_ticket_keeps_its_pull_request_and_its_action(self):
        head = "5" * 40
        drops = [(self.overnight_issues[1], "open item in the decisions log: parked")]
        result = self.collect(
            [self.pull(19, head, f"Refs #2\nBuilder check: FAIL {head}")],
            drops=drops,
        )
        item = self.items(result)[19]
        self.assertEqual(item["action"], "fix")
        self.assertEqual(item["key"], "MO-2")
        self.assertIn("open item", item["ticketDropped"])

    def test_a_held_ticket_keeps_its_pull_request_and_no_action(self):
        head = "6" * 40
        drops = [(self.overnight_issues[2], "marked hold: HOLD MO-3")]
        result = self.collect(
            [self.pull(20, head, f"Refs #3\nBuilder check: FAIL {head}")],
            drops=drops,
        )
        item = self.items(result)[20]
        self.assertEqual(item["action"], "none")
        self.assertEqual(item["actionReason"], "its ticket is dropped: marked hold: HOLD MO-3")

    def test_the_count_is_the_open_pull_requests_and_not_the_drafts(self):
        groups = (
            (
                "in-flight",
                [
                    {"kind": "pull-request", "number": 1},
                    {"kind": "pull-request", "number": 2, "isDraft": True},
                    {"kind": "ticket", "number": 3},
                ],
            ),
        )
        self.assertEqual(self.overnight.open_pull_requests(groups), 1)


if __name__ == "__main__":
    unittest.main()
