"""Tests for the section heading matcher in the ticket CLI.

The CLI is a script without a .py suffix, so it is loaded by path. The body
fixtures live in tests/fixtures/ticket_start, one per heading variant.
"""
import importlib.util
import json
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "coordinator" / "bin"))


def load_ticket():
    path = ROOT / "coordinator" / "bin" / "ticket"
    loader = SourceFileLoader("ticket_cli", str(path))
    spec = importlib.util.spec_from_loader("ticket_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


ticket = load_ticket()

FIXTURES = ROOT / "tests" / "fixtures" / "ticket_start"
CONFIG = json.loads((ROOT / "coordinator" / "config" / "tickets.json").read_text())
CFG = {"repos": {"shyamsivakumar/mac-ops": {"key": "MO"}}, "template": CONFIG["template"]}
SECTION = "Data/secrets and stop conditions"

# The configured section names and their order, written out so that a change
# to the configuration fails here instead of passing quietly.
CONFIGURED = [
    "Goal and why",
    "Context",
    "Scope and non-goals",
    "Design fit",
    "Blocked by",
    "Acceptance and proof",
    "CI",
    "Must not cause",
    "Data/secrets and stop conditions",
    "Failure behavior",
    "Rollback",
    "Gate",
    "Finish",
]


def body(case):
    return (FIXTURES / case / "body.md").read_text()


class TemplateStatusTest(unittest.TestCase):
    def test_the_comma_label_line_finds_the_configured_section(self):
        self.assertEqual(ticket.template_status(CFG, body("comma"))[SECTION], "ok")

    def test_the_comma_label_line_in_bold_finds_the_configured_section(self):
        text = body("comma").replace(
            "Data, secrets and stop conditions:", "**Data, secrets and stop conditions**:")
        self.assertEqual(ticket.template_status(CFG, text)[SECTION], "ok")

    def test_the_comma_heading_finds_the_configured_section(self):
        text = body("comma").replace(
            "Data, secrets and stop conditions: Repo files and the local ticket config only; no secrets and no network writes.",
            "## Data, secrets and stop conditions\n\nRepo files and the local ticket config only.")
        self.assertEqual(ticket.template_status(CFG, text)[SECTION], "ok")

    def test_a_heading_written_as_markdown_passes_every_section(self):
        status = ticket.template_status(CFG, body("heading"))
        self.assertEqual([s for s, v in status.items() if v != "ok"], [])

    def test_case_and_spacing_do_not_matter(self):
        text = body("comma").replace(
            "Data, secrets and stop conditions:", "DATA/SECRETS   AND stop Conditions:")
        self.assertEqual(ticket.template_status(CFG, text)[SECTION], "ok")

    def test_the_word_and_is_a_separator_between_words(self):
        text = body("comma").replace(
            "Data, secrets and stop conditions:", "Data and secrets and stop conditions:")
        self.assertEqual(ticket.template_status(CFG, text)[SECTION], "ok")

    def test_a_deleted_heading_is_still_missing(self):
        self.assertEqual(ticket.template_status(CFG, body("missing"))[SECTION], "missing")

    def test_the_configured_heading_still_passes(self):
        status = ticket.template_status(CFG, body("slash"))
        self.assertEqual(status[SECTION], "ok")

    def test_every_section_of_a_written_body_is_found(self):
        for case in ("comma", "slash", "heading"):
            status = ticket.template_status(CFG, body(case))
            self.assertEqual([s for s, v in status.items() if v != "ok"], [], case)

    def test_an_unknown_heading_is_missing(self):
        text = body("slash").replace(SECTION, "Data, secrets and stop condition")
        self.assertEqual(ticket.template_status(CFG, text)[SECTION], "missing")

    def test_a_heading_that_names_another_section_is_missing(self):
        text = body("slash").replace(SECTION, "Design context")
        self.assertEqual(ticket.template_status(CFG, text)[SECTION], "missing")

    def test_a_letter_is_not_a_separator(self):
        text = body("slash").replace(SECTION, "Data/secrets and stop conditionsx")
        self.assertEqual(ticket.template_status(CFG, text)[SECTION], "missing")

    def test_a_non_ascii_letter_is_not_a_separator(self):
        text = body("heading").replace("## Context\n", "## Contexté\n")
        self.assertEqual(ticket.template_status(CFG, text)["Context"], "missing")

    def test_a_list_item_is_not_a_section_label(self):
        text = body("comma").replace(
            "Context: The skill writes", "Context:\n- Context: The skill writes")
        self.assertEqual(ticket.template_status(CFG, text)["Context"], "ok")

    def test_the_configured_names_and_their_order_do_not_change(self):
        self.assertEqual(CFG["template"], CONFIGURED)


class TicketStartProofTest(unittest.TestCase):
    """The `ticket start --dry-run` cases, on the real CLI."""

    def test_the_cases(self):
        sys.path.insert(0, str(ROOT))
        spec = importlib.util.spec_from_file_location(
            "ticket_start_proof", ROOT / "tests" / "ticket_start_proof.py")
        proof = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(proof)
        for case, expected in proof.CASES:
            _, result = proof.run_case(case)
            output = result.stdout + result.stderr
            self.assertIn(expected, output, case)


class AssembleBriefResearchSkillTest(unittest.TestCase):
    """Research tickets point builders at the shared research skill after brief_prefix."""

    def _brief(self, task_type, include_type=True):
        item = {
            "url": "https://github.com/shyamsivakumar/mac-ops/issues/1177",
            "reviewerAlias": "astra",
            "body": "Investigate the question.",
        }
        if include_type:
            item["type"] = task_type
        return ticket.assemble_brief(CFG, item, "ticket:shyamsivakumar/mac-ops#1177:a1", {"comments": []})

    def test_research_ticket_includes_shared_research_skill_after_prefix(self):
        prefix = ticket.brief_prefix()
        brief = self._brief("research")
        self.assertTrue(brief.startswith(prefix))
        self.assertNotIn(ticket.RESEARCH_SKILL_PATH, prefix)
        self.assertIn(ticket.RESEARCH_SKILL_PATH, brief[len(prefix):])

    def test_non_research_and_missing_types_omit_research_skill(self):
        for brief in (
            self._brief("standard"),
            self._brief(None),
            self._brief(None, include_type=False),
        ):
            self.assertNotIn(ticket.RESEARCH_SKILL_PATH, brief)


if __name__ == "__main__":
    unittest.main()
