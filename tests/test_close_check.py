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
        body = "In: the fix-check path in lane_driver.py skips herdr/* branches."
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
        ticket = ("In: close_check.py. Existing tests that pin it may change "
                  "only as far as this needs.")
        item = check.item_scope(ticket, ["tests/test_alarm_panel.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("tests/test_alarm_panel.py", item["detail"])

    def test_a_ticket_that_names_the_test_puts_it_in_scope(self):
        check = close_check()
        item = check.item_scope("In: close_check.py and tests/test_alarm_panel.py.",
                                ["coordinator/bin/close_check.py", "tests/test_alarm_panel.py"])
        self.assertEqual(item["status"], check.PASS)

    def test_a_file_the_ticket_excludes_is_out_of_scope(self):
        """An exclusion is not permission."""
        check = close_check()
        ticket = "In: `close_check.py`. Out of scope: `gate_policy.py`."
        item = check.item_scope(ticket, ["coordinator/bin/close_check.py",
                                         "coordinator/bin/gate_policy.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("coordinator/bin/gate_policy.py", item["detail"])

    def test_an_excluded_file_is_not_a_permission(self):
        check = close_check()
        ticket = "In: `close_check.py`. Out of scope: `gate_policy.py`."
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

    def test_a_heading_does_not_widen_a_declared_scope(self):
        """A later section is background once the ticket declares its scope.

        The ticket declares its scope, so the declaration is the
        permission: a file named in a later section is a reference, not a
        permission.
        """
        check = close_check()
        ticket = ("## Scope and non-goals\nIn: `close_check.py`. Out: `gate_policy.py`\n\n"
                  "## Files\n`close_check.py` and `lane_driver.py`.\n")
        self.assertEqual(check.scope_tokens(ticket), {"close_check.py"})
        item = check.item_scope(ticket, ["coordinator/bin/close_check.py",
                                         "coordinator/overnight/lane_driver.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("coordinator/overnight/lane_driver.py", item["detail"])

    def test_a_background_reference_is_not_a_permission(self):
        """The gate's counterexample: the context names another file."""
        check = close_check()
        ticket = "In: src/parser.py\n\n## Context\nsrc/legacy.py calls the parser\n"
        self.assertEqual(check.scope_tokens(ticket), {"src/parser.py"})
        item = check.item_scope(ticket, ["src/parser.py", "src/legacy.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("src/legacy.py", item["detail"])

    def test_a_top_level_directory_declaration_bounds_the_scope(self):
        """A top-level directory is a declaration too.

        "In: src/" has no component after the slash, and it still bounds
        every path under it.
        """
        check = close_check()
        ticket = "In: src/\n"
        self.assertEqual(check.scope_tokens(ticket), {"src/"})
        item = check.item_scope(ticket, ["src/parser.py"])
        self.assertEqual(item["status"], check.PASS)
        outside = check.item_scope(ticket, ["src/parser.py", "srcfoo/other.py"])
        self.assertEqual(outside["status"], check.FAIL)
        self.assertIn("srcfoo/other.py", outside["detail"])

    def test_the_files_of_a_rename_carry_both_paths(self):
        check = close_check()
        entries = [{"filename": "src/new.py", "previous_filename": "legacy/old.py"},
                   {"filename": "src/other.py"}]
        with patch.object(check, "gh_json", return_value=entries):
            changed, scope, error = check.fetch_files("a/b", 12)
        self.assertEqual(error, "")
        self.assertEqual(changed, ["src/new.py", "src/other.py"])
        self.assertEqual(scope, ["src/new.py", "legacy/old.py", "src/other.py"])

    def test_the_files_are_read_past_the_first_page(self):
        """A pull request with more files than a page holds is read whole."""
        check = close_check()
        first = [{"filename": f"src/file{index}.py"} for index in range(100)]
        second = [{"filename": "src/last.py"}]
        with patch.object(check, "gh_json", side_effect=[first, second]) as reader:
            changed, scope, error = check.fetch_files("a/b", 12)
        self.assertEqual(error, "")
        self.assertEqual(len(changed), 101)
        self.assertIn("src/last.py", scope)
        self.assertEqual(reader.call_count, 2)

    def test_the_files_read_are_compared_with_the_files_the_pull_request_changes(self):
        """The pages that end early are not the whole diff.

        A pull request that changes more files than the pages hold has a
        diff nobody read, so the scope cannot be judged.
        """
        check = close_check()
        page = [{"filename": f"src/file{index}.py"} for index in range(100)]
        with patch.object(check, "gh_json", side_effect=[page, []]):
            changed, scope, error = check.fetch_files("a/b", 12, expected=101)
        self.assertNotEqual(error, "")
        self.assertIn("101", error)
        item = check.item_scope("In: src/", scope, "evidence/MO-524", error)
        self.assertEqual(item["status"], check.FAIL)

    def test_a_page_that_cannot_be_read_fails_the_scope(self):
        """The diff is not known when its pages are not read to the end.

        A page that times out must not read as the end of the diff, or a
        file on the page that was not read would never be judged.
        """
        check = close_check()
        first = [{"filename": f"src/file{index}.py"} for index in range(100)]
        with patch.object(check, "gh_json", side_effect=[first, RuntimeError("the read timed out")]):
            changed, scope, error = check.fetch_files("a/b", 12)
        self.assertNotEqual(error, "")
        item = check.item_scope("In: src/", scope, "evidence/MO-524", error)
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("not read to the end", item["detail"])

    def test_a_rename_is_judged_on_both_paths(self):
        """A rename cannot carry an out-of-scope file into scope.

        The file a rename came from is judged as well as the file it is
        now.
        """
        check = close_check()
        ticket = "In: src/new.py\n\n## Out of scope\nlegacy/old.py\n"
        item = check.item_scope(ticket, ["src/new.py", "legacy/old.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("legacy/old.py", item["detail"])

    def test_a_declared_directory_bounds_the_scope(self):
        """A declared directory of the repository says where the change is."""
        check = close_check()
        ticket = "In: coordinator/bin/\n"
        self.assertEqual(check.scope_tokens(ticket), {"coordinator/bin/"})
        item = check.item_scope(ticket, ["coordinator/bin/ticket"])
        self.assertEqual(item["status"], check.PASS)
        outside = check.item_scope(ticket, ["coordinator/bin/ticket",
                                            "coordinator/overnight/lane_driver.py"])
        self.assertEqual(outside["status"], check.FAIL)
        self.assertIn("coordinator/overnight/lane_driver.py", outside["detail"])

    def test_a_prohibition_phrase_excludes_only_what_it_forbids(self):
        """A phrase that forbids no file excludes no file.

        "builders and gates never file follow-up issues" forbids a
        practice, not a file, so the file the same line names is still
        in scope.
        """
        check = close_check()
        ticket = ("In: coordinator/config/AGENT-RULES.md. Add the missing decision: builders "
                  "and gates never file follow-up issues.")
        self.assertEqual(check.scope_tokens(ticket), {"coordinator/config/AGENT-RULES.md"})

    def test_a_prohibition_of_a_change_excludes_that_change(self):
        check = close_check()
        ticket = "Change close_check.py. Must not change coordinator/bin/gate_policy.py."
        item = check.item_scope(ticket, ["coordinator/bin/close_check.py",
                                         "coordinator/bin/gate_policy.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("coordinator/bin/gate_policy.py", item["detail"])

    def test_a_without_clause_excludes_from_without_on(self):
        check = close_check()
        ticket = "In:\n- `src/a.py`: move it without changing its behavior.\n"
        item = check.item_scope(ticket, ["src/a.py"])
        self.assertEqual(item["status"], check.PASS)

    def test_a_without_clause_excludes_only_what_it_names(self):
        check = close_check()
        ticket = "In: Change src/a.py without changing src/b.py."
        self.assertEqual(check.scope_tokens(ticket), {"src/a.py"})

    def test_a_prohibition_before_a_without_clause_still_excludes(self):
        check = close_check()
        for ticket in ("In: src/b.py. src/a.py must not change.",
                       "In: src/b.py. Do not touch src/a.py."):
            self.assertEqual(check.scope_tokens(ticket), {"src/b.py"})

    def test_a_without_clause_inside_an_out_section_stays_excluded(self):
        check = close_check()
        ticket = "In: src/a.py.\n\n## Out of scope\n- src/b.py, without changing src/c.py.\n"
        permission, exclusion = check.scope_texts(ticket)
        self.assertEqual(check.exclusion_tokens(exclusion), {"src/b.py", "src/c.py"})
        self.assertEqual(check.scope_tokens(ticket), {"src/a.py"})

    def test_a_copied_string_does_not_tie_a_test(self):
        """No string ties a test to a change.

        A pull request can add a value to a file the ticket allows and
        the same value to an unrelated test. The test is still out of
        scope: a test changes when the ticket names it, or when it is the
        test of a file the change touches.
        """
        check = close_check()
        ticket = ("In: close_check.py. Existing tests that pin it may change "
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
        ticket = ("In: close_check.py. Existing tests that pin it may change "
                  "only as far as this needs.")
        item = check.item_scope(ticket, ["coordinator/bin/close_check.py",
                                         "tests/test_alarm_panel.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("tests/test_alarm_panel.py", item["detail"])
        self.assertNotIn("pass", item["status"])

    def test_an_inline_exclusion_survives_a_child_heading(self):
        """An exclusion written inline holds under a heading beneath it.

        "Out of scope:" inside "## Scope" excludes what follows, and the
        "### Protected files" heading under it does not end that.
        """
        check = close_check()
        ticket = ("## Scope\nIn: src/\nOut of scope:\n### Protected files\n"
                  "src/private.py\n")
        item = check.item_scope(ticket, ["src/parser.py", "src/private.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("src/private.py", item["detail"])

    def test_an_inline_marker_does_not_lift_the_enclosing_exclusion(self):
        """An "In:" bullet under an exclusion does not permit the file.

        The exclusion holds throughout its section: a marker written
        inside it cannot turn the file it names into a permission.
        """
        check = close_check()
        ticket = "In: src/\n## Out of scope\n- In: legacy/config.py\n"
        item = check.item_scope(ticket, ["src/parser.py", "legacy/config.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("legacy/config.py", item["detail"])

    def test_a_nested_scope_heading_does_not_lift_the_exclusion(self):
        """A heading under an exclusion cannot permit what it holds.

        "### Scope" inside "## Out of scope" does not make the files
        beneath it permitted: the exclusion holds until a sibling or a
        higher heading ends it.
        """
        check = close_check()
        ticket = ("In: src/\n## Out of scope\n### Scope\nsrc/legacy.py\n")
        item = check.item_scope(ticket, ["src/parser.py", "src/legacy.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("src/legacy.py", item["detail"])

    def test_the_inferred_test_allowance_reaches_test_files_only(self):
        """A fixture that carries the name of a source is not its test."""
        check = close_check()
        ok, _ = check.in_scope("tests/fixtures/close_check.json", {"close_check.py"},
                               ["src/close_check.py"])
        self.assertFalse(ok)
        ok, _ = check.in_scope("tests/test_close_check.py", {"close_check.py"},
                               ["src/close_check.py"])
        self.assertTrue(ok)

    def test_a_sibling_heading_restores_the_enclosing_exclusion(self):
        """A subsection does not take the enclosing section's intent away.

        "### Non-goals" and "### Protected files" are siblings inside
        "## Out of scope", so the second one is still excluded.
        """
        check = close_check()
        ticket = ("In: src/\n## Out of scope\n### Non-goals\nsrc/old.py\n"
                  "### Protected files\nsrc/legacy.py\n")
        item = check.item_scope(ticket, ["src/parser.py", "src/legacy.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("src/legacy.py", item["detail"])

    def test_a_nested_heading_keeps_the_enclosing_exclusion(self):
        """A heading under a section belongs to that section.

        "### Protected files" sits inside "## Out of scope", so the file
        it names stays excluded even though the declared directory would
        otherwise cover it.
        """
        check = close_check()
        ticket = ("## Scope\nIn: coordinator/bin/\n## Out of scope\n### Protected files\n"
                  "coordinator/bin/gate_policy.py\n")
        item = check.item_scope(ticket, ["coordinator/bin/ticket",
                                         "coordinator/bin/gate_policy.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("coordinator/bin/gate_policy.py", item["detail"])

    def test_a_scope_heading_declares_the_scope(self):
        """The gate's counterexample: the scope is declared by a heading.

        A ticket that declares its scope under a heading is judged by
        that section, so a file named in the context section is a
        reference and not a permission.
        """
        check = close_check()
        ticket = ("## Scope\nOnly src/parser.py.\n\n## Context\nsrc/legacy.py calls the parser.\n")
        self.assertEqual(check.scope_tokens(ticket), {"src/parser.py"})
        item = check.item_scope(ticket, ["src/parser.py", "src/legacy.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("src/legacy.py", item["detail"])

    def test_a_ticket_without_a_declaration_fails_closed(self):
        """A ticket that declares no scope cannot be judged, so it fails."""
        check = close_check()
        item = check.item_scope("## Context\nsrc/legacy.py calls the parser.\n",
                                ["src/legacy.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("cannot be judged", item["detail"])

    def test_the_scope_item_fails_and_names_the_file(self):
        check = close_check()
        item = check.item_scope("In: lane_driver.py.",
                                ["coordinator/overnight/lane_driver.py",
                                 "coordinator/mods/cockpit/ui.js"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("coordinator/mods/cockpit/ui.js", item["detail"])

    def test_a_ticket_that_names_no_path_cannot_be_judged_and_fails(self):
        check = close_check()
        item = check.item_scope("Nothing here names a file.", ["a.py"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("cannot be judged", item["detail"])

    def test_a_qualified_exclusion_does_not_reach_another_directory(self):
        """A qualified exclusion names one file, not every file of its name.

        A ticket that permits `src/config.py` and excludes
        `legacy/config.py` keeps its permission: the two paths differ, so
        the exclusion reaches only the file it names.
        """
        check = close_check()
        item = check.item_scope("In: src/config.py. Out: legacy/config.py.",
                               ["src/config.py"])
        self.assertEqual(item["status"], check.PASS, item["detail"])
        item = check.item_scope("In: src/config.py. Out: legacy/config.py.",
                               ["legacy/config.py"])
        self.assertEqual(item["status"], check.FAIL)

    def test_a_bare_exclusion_still_reaches_a_qualified_path(self):
        """A bare name carries no directory, so it names every file of it."""
        check = close_check()
        item = check.item_scope("In: src/config.py. Out: config.py.",
                               ["src/config.py"])
        self.assertEqual(item["status"], check.FAIL)

    def test_the_pull_request_cannot_widen_the_scope(self):
        """The ticket is the only authority for the scope.

        A ticket limited to one file plus a pull request that declares a
        second file must not let that second file through: nothing in the
        pull request is read for the scope, so the change the pull request
        declares is judged against the ticket and fails.
        """
        check = close_check()
        ticket = "In: lane_driver.py."
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
        own = check.checklist("In: close_check.py.", "",
                              ["coordinator/bin/close_check.py",
                               "evidence/MO-1077/check-proof.md"], "found", proof,
                              "evidence/MO-1077/check-proof.md", "absent")
        self.assertEqual([item["item"] for item in check.blocking(own)], [])
        other = check.checklist("In: close_check.py.", "",
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

    def test_a_dockerfile_variant_is_a_file_token(self):
        check = close_check()
        body = "In: the dashboard image copies the new module. Files: Dockerfile.dashboard"
        tokens = check.scope_tokens(body)
        self.assertIn("Dockerfile.dashboard", tokens)
        ok, _ = check.in_scope("Dockerfile.dashboard", tokens)
        self.assertTrue(ok)
        self.assertTrue(check.names_a_scope(tokens))

    def test_the_base_dockerfile_does_not_cover_a_variant(self):
        check = close_check()
        ok, _ = check.in_scope("Dockerfile.dashboard", {"Dockerfile"})
        self.assertFalse(ok)

    def test_an_excluded_dockerfile_variant_is_not_a_permission(self):
        check = close_check()
        ticket = "In: `close_check.py`. Out of scope: `Dockerfile.dashboard`."
        self.assertNotIn("Dockerfile.dashboard", check.scope_tokens(ticket))

    def test_a_dockerfile_path_stays_one_path(self):
        check = close_check()
        self.assertEqual(check.scope_tokens("In: docker/Dockerfile.web"),
                         {"docker/Dockerfile.web"})

    def test_a_name_that_ends_in_dockerfile_is_untouched(self):
        check = close_check()
        self.assertEqual(check.scope_tokens("In: MyDockerfile.py"), {"MyDockerfile.py"})

    def test_a_ticket_can_name_a_swift_file(self):
        # The shape of the ticket that found this: an iOS ticket declares the
        # component it changes by its bare name, and the changed path carries
        # the package directory in front of it.
        check = close_check()
        ticket = ("## Scope and non-goals\n\n"
                  "Change only the platform option list in TRSourceImportSheet.swift and record "
                  "the deliberate Studio departure in docs/DESIGN.md.")
        tokens = check.scope_tokens(ticket)
        self.assertIn("TRSourceImportSheet.swift", tokens)
        self.assertTrue(check.names_a_scope(tokens))
        path = ("Packages/TuneriseDesign/Sources/TuneriseDesign/Components/"
                "TRSourceImportSheet.swift")
        ok, why = check.in_scope(path, tokens)
        self.assertTrue(ok, why)

    def test_a_swift_file_the_ticket_never_names_stays_out(self):
        check = close_check()
        item = check.item_scope("In: the add-source sheet: TRSourceImportSheet.swift.",
                                ["App/Shared/HomeView.swift", "TRSourceImportSheet.swift"])
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("App/Shared/HomeView.swift", item["detail"])

    def test_an_excluded_swift_file_is_not_a_permission(self):
        check = close_check()
        ticket = "In: the sheet: TRSourceImportSheet.swift. Out: HomeView.swift."
        self.assertEqual(check.scope_tokens(ticket), {"TRSourceImportSheet.swift"})
        self.assertNotIn("HomeView.swift", check.scope_tokens(ticket))


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

    def test_a_headerless_proof_keeps_its_failed_row(self):
        """The header is the whole header row, so a first row that is not
        one is a check.

        A proof file with no header, whose first row reads
        `| check | command | failed | compiler error |`, records a
        failure. It must not be read as a header and dropped.
        """
        check = close_check()
        text = ("| check | command | failed | compiler error |\n"
                "| lint  | make lint | passed | |\n")
        item = check.item_checks("found", text)
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("failed", item["detail"])

    def test_a_row_that_only_starts_like_the_header_is_a_check(self):
        """Every header cell counts, the detail cell too.

        A proof file with no header, whose first row reads
        `| check | command | result | compiler error |`, records a check
        whose result is not passed. It must not be read as a header and
        dropped, which would report that every check passed.
        """
        check = close_check()
        text = ("| check | command | result | compiler error |\n"
                "| lint  | make lint | passed | |\n")
        item = check.item_checks("found", text)
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("check", item["detail"])

    def test_an_escaped_pipe_stays_in_the_command(self):
        """A command can hold a pipe, and the result column is the third.

        `make build \| tee build.log` is one command cell, so the row
        reads as a passing check rather than as a check whose result is
        "tee build.log".
        """
        check = close_check()
        text = ("| Check | Command | Result | Detail |\n"
                "| --- | --- | --- | --- |\n"
                "| build | make build \\| tee build.log | passed | |\n")
        item = check.item_checks("found", text)
        self.assertEqual(item["status"], check.PASS)

    def test_a_row_without_its_outer_pipes_is_a_row(self):
        """A Markdown row does not have to carry its outer pipes.

        A row that starts `build | make build | failed | compiler error`
        records a failure, and the table cannot lose it because the row
        has no leading pipe.
        """
        check = close_check()
        text = ("| Check | Command | Result | Detail |\n"
                "| --- | --- | --- | --- |\n"
                "| lint | make lint | passed | |\n"
                "build | make build | failed | compiler error\n")
        item = check.item_checks("found", text)
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("failed", item["detail"])

    def test_a_line_inside_the_table_that_is_not_a_row_blocks_the_close(self):
        check = close_check()
        text = ("| Check | Command | Result | Detail |\n"
                "| --- | --- | --- | --- |\n"
                "| lint | make lint | passed | |\n"
                "the build failed\n")
        item = check.item_checks("found", text)
        self.assertEqual(item["status"], check.FAIL)

    def test_a_proof_file_the_pull_request_does_not_change_is_not_accepted(self):
        """A proof file on the base branch is an earlier run's proof.

        The checklist reads the proof of the change in front of it, so the
        proof path has to be among the files the pull request changes.
        """
        check = close_check()
        path = "evidence/MO-524/check-proof.md"
        self.assertFalse(check.changed_proof(["coordinator/bin/close_check.py"], path))
        self.assertTrue(check.changed_proof(["coordinator/bin/close_check.py", path], path))
        item = check.item_proof(check.proof_file.MISSING, path,
                                f"the proof file at {path} is not part of this change")
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("not part of this change", item["detail"])

    def test_an_empty_cost_note_waives_nothing(self):
        """A cost note carries a value; the label alone is not a note."""
        check = close_check()
        self.assertEqual(check.item_cost("Cost:", "exists")["status"], check.FAIL)
        self.assertEqual(check.item_cost("Cost: 12 minutes", "exists")["status"], check.PASS)

    def test_a_failure_written_outside_the_table_still_fails(self):
        """A result outside the table is a check too."""
        check = close_check()
        text = ("| Check | Command | Result | Detail |\n"
                "| --- | --- | --- | --- |\n"
                "| lane selection | `x` | passed | |\n"
                "heavy help: failed\n")
        item = check.item_checks("found", text)
        self.assertEqual(item["status"], check.FAIL)
        self.assertIn("failed", item["detail"])

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
        items = check.checklist("In: close_check.py.", "Cost: 1 minute",
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
        items = check.checklist("In: close_check.py.", "",
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
        brief = gate_policy.build_gate_brief({"key": "MO"}, "shyamsivakumar/fixture", 524, 12,
                                             "a" * 40, False)
        self.assertIn("close_check.py", brief)
        self.assertLess(brief.index("close_check.py"), brief.index("gh issue close"))


if __name__ == "__main__":
    unittest.main()
