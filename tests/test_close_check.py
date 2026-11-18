"""The close checklist that runs before the coordinator closes a ticket."""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "coordinator" / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))


def load(path, name):
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def close_check():
    return load(BIN / "close_check.py", "close_check")


class ScopeTest(unittest.TestCase):
    def test_the_ticket_names_its_files(self):
        check = close_check()
        body = "The fix-check path in lane_driver.py skips herdr/* branches."
        tokens = check.scope_tokens(body)
        self.assertIn("lane_driver.py", tokens)
        self.assertIn("herdr/*", tokens)

    def test_a_named_file_is_in_scope(self):
        check = close_check()
        ok, _ = check.in_scope("coordinator/overnight/lane_driver.py", {"lane_driver.py"})
        self.assertTrue(ok)

    def test_a_named_directory_holds_its_files(self):
        check = close_check()
        ok, _ = check.in_scope("coordinator/bin/ticket", {"coordinator/bin"})
        self.assertTrue(ok)

    def test_a_glob_matches(self):
        check = close_check()
        ok, _ = check.in_scope("coordinator/mods/herdr/x.js", {"coordinator/mods/herdr/*"})
        self.assertTrue(ok)

    def test_a_file_the_ticket_never_names_is_out_of_scope(self):
        check = close_check()
        ok, _ = check.in_scope("coordinator/mods/cockpit/ui.js", {"lane_driver.py"})
        self.assertFalse(ok)

    def test_evidence_travels_with_the_change(self):
        check = close_check()
        ok, _ = check.in_scope("evidence/MO-1077/check-proof.md", set(),
                               evidence="evidence/MO-1077")
        self.assertTrue(ok)

    def test_another_tickets_evidence_is_out_of_scope(self):
        """A pull request adds evidence of its own ticket only.

        A change scoped to one file cannot rewrite another ticket's proof
        file and still pass the scope item, so the automatic allowance is
        the ticket's own evidence directory and nothing wider.
        """
        check = close_check()
        ok, _ = check.in_scope("evidence/MO-521/check-proof.md", set(),
                               evidence="evidence/MO-524")
        self.assertFalse(ok)
        ok, _ = check.in_scope("evidence/MO-524/check-proof.md", set(),
                               evidence="evidence/MO-524")
        self.assertTrue(ok)

    def test_a_ticket_that_names_no_evidence_authorizes_no_evidence_directory(self):
        """With no ticket there is no evidence directory.

        A pull request with no ticket has its proof file at the default
        path, so `evidence/` as a whole is never the ticket's own.
        """
        check = close_check()
        self.assertEqual(check.evidence_dir("evidence/check-proof.md"), "")
        self.assertEqual(check.evidence_dir("evidence/MO-524/check-proof.md"),
                         "evidence/MO-524")
        ok, _ = check.in_scope("evidence/MO-521/check-proof.md", set(), evidence="")
        self.assertFalse(ok)

    def test_a_test_of_a_changed_file_is_in_scope(self):
        check = close_check()
        ok, _ = check.in_scope("tests/test_close_check.py", set(),
                               ["coordinator/bin/close_check.py"])
        self.assertTrue(ok)

    def test_a_test_of_something_else_is_out_of_scope(self):
        check = close_check()
        ok, _ = check.in_scope("tests/test_alarm_panel.py", set(),
                               ["coordinator/bin/close_check.py"])
        self.assertFalse(ok)

    def test_the_ticket_clause_does_not_allow_an_unrelated_test(self):
        """The clause keeps its restriction.

        "Existing tests ... may change only as far as this needs" allows
        the tests that pin what the change changes. A test of something
        else is out of scope even with the clause, and the ticket has to
        name that test for it to be in scope.
        """
        check = close_check()
        ticket = ("The change is in close_check.py. Existing tests that pin it may change "
                  "only as far as this needs.")
        item = check.item_scope(ticket, ["tests/test_alarm_panel.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("tests/test_alarm_panel.py", item["detail"])

    def test_a_ticket_that_names_the_test_puts_it_in_scope(self):
        check = close_check()
        item = check.item_scope("The change is in close_check.py and tests/test_alarm_panel.py.",
                                ["coordinator/bin/close_check.py", "tests/test_alarm_panel.py"])
        self.assertEqual(item["status"], check.PASS)

    def test_a_file_the_ticket_excludes_is_out_of_scope(self):
        """An exclusion is not permission."""
        check = close_check()
        ticket = "Change `close_check.py`. Out of scope: `gate_policy.py`."
        item = check.item_scope(ticket, ["coordinator/bin/close_check.py",
                                         "coordinator/bin/gate_policy.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("coordinator/bin/gate_policy.py", item["detail"])

    def test_an_excluded_file_is_not_a_permission(self):
        check = close_check()
        ticket = "Change `close_check.py`. Out of scope: `gate_policy.py`."
        self.assertEqual(check.scope_tokens(ticket), {"close_check.py"})

    def test_evidence_cannot_authorize_a_test_change(self):
        """A pull request cannot supply the file that ties its own test.

        Adding `evidence/alarm_panel.md` and `tests/test_alarm_panel.py`
        to a change scoped to `close_check.py` must fail: evidence is not
        a source, and the test names nothing the change touches.
        """
        check = close_check()
        ok, _ = check.in_scope("tests/test_alarm_panel.py", {"close_check.py"},
                               ["coordinator/bin/close_check.py", "evidence/alarm_panel.md"])
        self.assertFalse(ok)

    def test_a_test_with_a_similar_name_is_out_of_scope(self):
        """A shared prefix is not a relationship."""
        check = close_check()
        ok, _ = check.in_scope("tests/test_close_window.py", {"close_check.py"},
                               ["coordinator/bin/close_check.py"])
        self.assertFalse(ok)

    def test_a_test_with_the_same_name_is_in_scope(self):
        check = close_check()
        ok, _ = check.in_scope("tests/test_close_check.py", {"close_check.py"},
                               ["coordinator/bin/close_check.py"])
        self.assertTrue(ok)

    def test_a_markdown_list_under_an_exclusion_heading_is_excluded(self):
        """An exclusion holds to the end of its section.

        "Out of scope:" followed by a bullet list excludes every file the
        list names: the list continues the exclusion the heading began.
        """
        check = close_check()
        ticket = "Change `close_check.py`.\n\n## Out of scope:\n- `gate_policy.py`\n- `ticket`\n"
        self.assertNotIn("gate_policy.py", check.scope_tokens(ticket))
        self.assertNotIn("ticket", check.scope_tokens(ticket))
        item = check.item_scope(ticket, ["coordinator/bin/close_check.py",
                                         "coordinator/bin/gate_policy.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("coordinator/bin/gate_policy.py", item["detail"])

    def test_a_heading_ends_an_exclusion(self):
        """The next section states its own intent: permission again."""
        check = close_check()
        ticket = ("## Scope and non-goals\nIn: checklist at close. Out: `gate_policy.py`\n\n"
                  "## Files\n`close_check.py` and `lane_driver.py`.\n")
        self.assertEqual(check.scope_tokens(ticket), {"close_check.py", "lane_driver.py"})
        item = check.item_scope(ticket, ["coordinator/bin/close_check.py",
                                         "coordinator/overnight/lane_driver.py"])
        self.assertEqual(item["status"], check.PASS)

    def test_a_prohibition_phrase_excludes_only_what_it_forbids(self):
        """A phrase that forbids no file excludes no file.

        "builders and gates never file follow-up issues" forbids a
        practice, not a file, so the file the same line names is still
        in scope.
        """
        check = close_check()
        ticket = ("Only coordinator/config/AGENT-RULES.md. Add the missing decision: builders "
                  "and gates never file follow-up issues.")
        self.assertEqual(check.scope_tokens(ticket), {"coordinator/config/AGENT-RULES.md"})

    def test_a_prohibition_of_a_change_excludes_that_change(self):
        check = close_check()
        ticket = "Change close_check.py. Must not change coordinator/bin/gate_policy.py."
        item = check.item_scope(ticket, ["coordinator/bin/close_check.py",
                                         "coordinator/bin/gate_policy.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("coordinator/bin/gate_policy.py", item["detail"])

    def test_a_copied_string_does_not_tie_a_test(self):
        """No string ties a test to a change.

        A pull request can add a value to a file the ticket allows and
        the same value to an unrelated test. The test is still out of
        scope: a test changes when the ticket names it, or when it is the
        test of a file the change touches.
        """
        check = close_check()
        ticket = ("The change is in close_check.py. Existing tests that pin it may change "
                  "only as far as this needs.")
        item = check.item_scope(ticket, ["coordinator/bin/close_check.py",
                                         "tests/test_alarm_panel.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("tests/test_alarm_panel.py", item["detail"])

    def test_a_copied_value_in_an_allowed_file_authorizes_no_test(self):
        """The gate's counterexample, verbatim.

        The ticket names `close_check.py` and allows its existing tests to
        change. The change adds `UNUSED = "alarm-panel-value"` to the
        allowed file, and an unrelated test carries that string. The test
        is still out of scope: a string is not a relationship, whether the
        change introduced it or not.
        """
        check = close_check()
        ticket = ("The change is in close_check.py. Existing tests that pin it may change "
                  "only as far as this needs.")
        item = check.item_scope(ticket, ["coordinator/bin/close_check.py",
                                         "tests/test_alarm_panel.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("tests/test_alarm_panel.py", item["detail"])
        self.assertNotIn("pass", item["status"])

    def test_the_scope_item_fails_and_names_the_file(self):
        check = close_check()
        item = check.item_scope("The change is in lane_driver.py.",
                                ["coordinator/overnight/lane_driver.py",
                                 "coordinator/mods/cockpit/ui.js"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("coordinator/mods/cockpit/ui.js", item["detail"])

    def test_a_ticket_that_names_no_path_cannot_be_judged_and_fails(self):
        check = close_check()
        item = check.item_scope("Nothing here names a file.", ["a.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("cannot be judged", item["detail"])

    def test_the_pull_request_cannot_widen_the_scope(self):
        """The ticket is the only authority for the scope.

        A ticket limited to one file plus a pull request that declares a
        second file must not let that second file through: nothing in the
        pull request is read for the scope, so the change the pull request
        declares is judged against the ticket and fails.
        """
        check = close_check()
        ticket = "The change is in lane_driver.py."
        pull_request = "**Scope.** `coordinator/overnight/lane_driver.py`, `coordinator/unrelated.py`."
        items = check.checklist(ticket, pull_request,
                                ["coordinator/overnight/lane_driver.py", "coordinator/unrelated.py"],
                                "found",
                                "| Check | Command | Result |\n| --- | --- | --- |\n"
                                "| lane selection | `x` | passed |",
                                "evidence/MO-1077/check-proof.md", "absent")
        scope = items[0]
        self.assertEqual(scope["status"], check.FAIL)
        self.assertIn("coordinator/unrelated.py", scope["detail"])
        self.assertNotIn("lane_driver.py, ", scope["detail"])
        self.assertEqual([item["item"] for item in check.blocking(items)], ["scope"])

    def test_a_checklist_reads_the_proof_path_for_the_evidence_it_allows(self):
        """The checklist lets through the evidence of its own ticket only.

        The same pull request with the same diff fails the scope item when
        the diff rewrites the proof file of another ticket.
        """
        check = close_check()
        proof = ("| Check | Command | Result |\n| --- | --- | --- |\n"
                 "| lane selection | `x` | passed |")
        own = check.checklist("The change is in close_check.py.", "",
                              ["coordinator/bin/close_check.py",
                               "evidence/MO-1077/check-proof.md"], "found", proof,
                              "evidence/MO-1077/check-proof.md", "absent")
        self.assertEqual([item["item"] for item in check.blocking(own)], [])
        other = check.checklist("The change is in close_check.py.", "",
                                ["coordinator/bin/close_check.py",
                                 "evidence/MO-521/check-proof.md"], "found", proof,
                                "evidence/MO-1077/check-proof.md", "absent")
        self.assertEqual([item["item"] for item in check.blocking(other)], ["scope"])

    def test_a_home_path_is_not_a_path_in_this_repository(self):
        check = close_check()
        body = "Source: ~/Code/inbox/2026-11-17-ideas.md, requested by Shyam."
        self.assertEqual(check.scope_tokens(body), set())
        item = check.item_scope(body, ["coordinator/bin/close_check.py"])
        self.assertEqual(item["status"], check.FAIL)

    def test_a_ticket_that_names_only_a_directory_cannot_be_judged(self):
        check = close_check()
        item = check.item_scope("The change lands in coordinator/overnight and anthropics/claude-cookbooks.",
                                ["coordinator/bin/close_check.py"])
        self.assertEqual(item["status"], check.FAIL)

    def test_a_ticket_that_names_a_file_in_another_directory_still_judges(self):
        check = close_check()
        item = check.item_scope("The board's state is decisions.json.",
                                ["coordinator/overnight/lane_driver.py"])
        self.assertEqual(item["status"], check.FAIL)


class DiffValuesTest(unittest.TestCase):
    """The values a change sets come from its own added lines."""

    def test_the_proof_rows_carry_the_result(self):
        check = close_check()
        text = ("| Check | Command | Result | Detail |\n"
                "| --- | --- | --- | --- |\n"
                "| lane selection | `python3 x` | passed |  |\n"
                "| heavy help | `python3 y` | failed | boom |\n")
        self.assertEqual(check.proof_rows(text),
                         [("lane selection", "passed"), ("heavy help", "failed")])

    def test_a_row_that_only_looks_like_a_separator_is_a_check(self):
        """A separator is a row of separators, not a row whose name is one.

        A proof file with one passing row and `| - | make check | failed |
        compiler error |` must not read as if the failure were not there.
        """
        check = close_check()
        text = ("| Check | Command | Result | Detail |\n"
                "| --- | --- | --- | --- |\n"
                "| lane selection | `x` | passed | |\n"
                "| - | make check | failed | compiler error |\n")
        item = check.item_checks("found", text)
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("failed", item["detail"])

    def test_a_row_named_check_is_a_check(self):
        """The header is recognized once; a later "check" row is a check.

        A proof file with one passing row and a row named `check` that
        failed must not report that every check passed.
        """
        check = close_check()
        text = ("| Check | Command | Result | Detail |\n"
                "| --- | --- | --- | --- |\n"
                "| lane selection | `x` | passed | |\n"
                "| check | make check | failed | compiler error |\n")
        item = check.item_checks("found", text)
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("failed", item["detail"])

    def test_a_check_row_that_omits_its_result_is_carried(self):
        """An incomplete row is a check, not a line to drop."""
        check = close_check()
        text = ("| Check | Command | Result | Detail |\n"
                "| --- | --- | --- | --- |\n"
                "| lane selection | `python3 x` | passed |  |\n"
                "| heavy help | `python3 y` |\n")
        self.assertEqual(check.proof_rows(text),
                         [("lane selection", "passed"), ("heavy help", "")])
        item = check.item_checks("found", text)
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("heavy help", item["detail"])
        self.assertIn("no result recorded", item["detail"])

    def test_an_empty_result_cell_blocks_the_item(self):
        check = close_check()
        item = check.item_checks("found", "| Check | Command | Result |\n| --- | --- | --- |\n"
                                            "| lane selection | `x` | passed |\n"
                                            "| heavy help | `y` |  |")
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("heavy help", item["detail"])

    def test_a_missing_proof_file_fails_the_item(self):
        check = close_check()
        item = check.item_proof("missing", "evidence/MO-1077/check-proof.md")
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("no proof file", item["detail"])

    def test_a_proof_file_that_cannot_be_read_fails_the_item(self):
        check = close_check()
        item = check.item_proof("unreadable", "evidence/MO-1077/check-proof.md")
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("could not be read", item["detail"])

    def test_every_check_must_have_passed(self):
        check = close_check()
        item = check.item_checks("found", "| Check | Command | Result |\n| --- | --- | --- |\n"
                                            "| lane selection | `x` | passed |")
        self.assertEqual(item["status"], check.PASS)
        item = check.item_checks("found", "| Check | Command | Result |\n| --- | --- | --- |\n"
                                            "| lane selection | `x` | passed |\n"
                                            "| heavy help | `y` | not run |")
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("heavy help", item["detail"])

    def test_a_proof_file_without_a_check_fails(self):
        check = close_check()
        item = check.item_checks("found", "# Check proof\n\nNo table here.\n")
        self.assertEqual(item["status"], check.FAIL)


class CostNoteTest(unittest.TestCase):
    def test_the_item_is_skipped_until_the_report_exists(self):
        check = close_check()
        item = check.item_cost("Cost: 12 minutes", "absent")
        self.assertEqual(item["status"], check.SKIPPED)
        self.assertFalse(item["required"])

    def test_a_lookup_that_did_not_answer_fails_the_item(self):
        check = close_check()
        item = check.item_cost("Cost: 12 minutes", "unknown", "the read timed out")
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("did not answer", item["detail"])

    def test_the_report_makes_the_note_needed(self):
        check = close_check()
        item = check.item_cost("Nothing about cost here.", "exists")
        self.assertEqual(item["status"], check.FAIL)

    def test_a_cost_note_passes_the_item(self):
        check = close_check()
        item = check.item_cost("Cost: 12 minutes, $0.40", "exists")
        self.assertEqual(item["status"], check.PASS)


class ReportLookupTest(unittest.TestCase):
    """The lookup of the cost report has three answers, not two."""

    class Result:
        def __init__(self, returncode, stderr=""):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = stderr

    def lookup(self, result=None, raises=None):
        check = close_check()
        with patch("subprocess.run", side_effect=raises) as runner:
            if result is not None:
                runner.side_effect = None
                runner.return_value = result
            return check.report_state("shyamsivakumar/mac-ops", "a" * 40)

    def test_a_found_report_exists(self):
        state, _ = self.lookup(self.Result(0))
        self.assertEqual(state, "exists")

    def test_a_404_is_a_confirmed_absence(self):
        state, _ = self.lookup(self.Result(1, "gh: Not Found (HTTP 404)"))
        self.assertEqual(state, "absent")

    def test_a_service_error_is_not_a_confirmed_absence(self):
        state, _ = self.lookup(self.Result(1, "gh: could not connect"))
        self.assertEqual(state, "unknown")

    def test_a_timeout_is_not_a_confirmed_absence(self):
        state, _ = self.lookup(raises=subprocess.TimeoutExpired("gh", 60))
        self.assertEqual(state, "unknown")


class ChecklistTest(unittest.TestCase):
    def test_the_checklist_reads_four_items_in_order(self):
        check = close_check()
        items = check.checklist("The change is in close_check.py.", "Cost: 1 minute",
                                ["coordinator/bin/close_check.py"], "found",
                                "| Check | Command | Result |\n| --- | --- | --- |\n"
                                "| lane selection | `x` | passed |",
                                "evidence/MO-1077/check-proof.md", "absent")
        self.assertEqual([item["item"] for item in items],
                         ["scope", "proof file", "checks", "cost note"])
        self.assertEqual(check.failures(items), [])
        self.assertEqual(check.blocking(items), [])

    def test_a_scope_that_cannot_be_judged_stops_the_close(self):
        check = close_check()
        items = check.checklist("Nothing here names a file.", "",
                                ["a.py"], "found",
                                "| Check | Command | Result |\n| --- | --- | --- |\n"
                                "| lane selection | `x` | passed |",
                                "evidence/MO-1077/check-proof.md", "absent")
        self.assertEqual([item["item"] for item in check.blocking(items)], ["scope"])

    def test_a_cost_note_before_the_report_does_not_stop_the_close(self):
        check = close_check()
        items = check.checklist("The change is in close_check.py.", "",
                                ["coordinator/bin/close_check.py"], "found",
                                "| Check | Command | Result |\n| --- | --- | --- |\n"
                                "| lane selection | `x` | passed |",
                                "evidence/MO-1077/check-proof.md", "absent")
        self.assertEqual(check.blocking(items), [])

    def test_the_report_ends_with_the_result(self):
        check = close_check()
        items = check.checklist("nothing", "nothing", ["a.py"], "missing", None,
                                "evidence/MO-1077/check-proof.md", "absent")
        text = check.report(items, "shyamsivakumar/mac-ops#524")
        self.assertIn("proof file: fail", text)
        self.assertTrue(text.endswith("RESULT: FAIL shyamsivakumar/mac-ops#524"))

    def test_the_issue_of_a_pull_request_body(self):
        check = close_check()
        self.assertEqual(check.issue_of("Refs #524\n"), 524)
        self.assertIsNone(check.issue_of("no issue here"))

    def test_the_ticket_key_of_a_title(self):
        check = close_check()
        self.assertEqual(check.ticket_key("MO-1077 · Evaluator checklist"), "MO")


class CloseStepTest(unittest.TestCase):
    """The ticket CLI closes only when the checklist passes."""

    def setUp(self):
        self.check = close_check()
        sys.modules["close_check"] = self.check
        self.ticket = load(BIN / "ticket", "ticket")

    def close(self, items, expect_refuse=True):
        head = "b" * 40
        calls = []

        def fake_gh(args, stdin=None):
            calls.append(args)
            return ""

        def fake_gh_json(args):
            return {"state": "MERGED", "headRefOid": head, "body": "Refs #524",
                    "mergeCommit": {"oid": "c" * 40}}

        def fake_t3_call(tool, args):
            return {"items": [{"type": "assistant_message",
                               "text": f"PROVIDES: PASS {head}\nCHECK: PASS {head}\nVERDICT: PASS"}]}

        args = SimpleNamespace(ref="shyamsivakumar/mac-ops#524", pr=12, head=head,
                               gate_thread="gate-thread")
        with patch.object(self.ticket, "gh", fake_gh), \
             patch.object(self.ticket, "gh_json", fake_gh_json), \
             patch.object(self.ticket, "t3_call", fake_t3_call), \
             patch.object(self.check, "run_check", lambda *a, **k: {"items": items}):
            if expect_refuse:
                with self.assertRaises(self.ticket.Refuse):
                    self.ticket.cmd_close(args)
            else:
                self.ticket.cmd_close(args)
        return calls

    def test_a_passing_checklist_closes_the_ticket(self):
        items = [{"item": "proof file", "status": "pass", "detail": "present"}]
        calls = self.close(items, expect_refuse=False)
        self.assertTrue(any(args[:2] == ["issue", "close"] for args in calls))

    def test_a_failing_checklist_leaves_the_ticket_open(self):
        items = [{"item": "proof file", "status": "fail",
                  "detail": "the pull request carries no proof file at evidence/MO-524/check-proof.md"}]
        calls = self.close(items)
        self.assertFalse(any(args[:2] == ["issue", "close"] for args in calls))
        self.assertTrue(any(args[:2] == ["issue", "comment"] for args in calls))


class GateBriefTest(unittest.TestCase):
    def test_the_gate_brief_runs_the_checklist_before_the_close(self):
        gate_policy = load(BIN / "gate_policy.py", "gate_policy")
        brief = gate_policy.build_gate_brief({"key": "MO"}, "shyamsivakumar/mac-ops", 524, 12,
                                             "a" * 40, False)
        self.assertIn("close_check.py", brief)
        self.assertLess(brief.index("close_check.py"), brief.index("gh issue close"))


if __name__ == "__main__":
    unittest.main()
