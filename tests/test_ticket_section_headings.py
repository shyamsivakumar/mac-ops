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


def body(case):
    return (FIXTURES / case / "body.md").read_text()


class CanonicalSectionTest(unittest.TestCase):
    def test_the_configured_name_is_its_own_canonical_form(self):
        self.assertEqual(ticket.canonical_section(SECTION), "data secrets stop conditions")

    def test_a_comma_reads_the_same_as_a_slash(self):
        self.assertEqual(ticket.canonical_section("Data, secrets and stop conditions"),
                         ticket.canonical_section(SECTION))

    def test_the_word_and_is_a_separator_between_words(self):
        self.assertEqual(ticket.canonical_section("Data and secrets and stop conditions"),
                         ticket.canonical_section(SECTION))

    def test_case_and_spacing_do_not_matter(self):
        self.assertEqual(ticket.canonical_section("DATA/SECRETS   AND stop Conditions"),
                         ticket.canonical_section(SECTION))

    def test_a_different_name_keeps_a_different_form(self):
        self.assertNotEqual(ticket.canonical_section("Design fit"),
                            ticket.canonical_section(SECTION))


class TemplateStatusTest(unittest.TestCase):
    def test_the_comma_heading_finds_the_configured_section(self):
        status = ticket.template_status(CFG, body("comma"))
        self.assertEqual(status[SECTION], "ok")

    def test_the_comma_label_line_finds_the_configured_section(self):
        text = body("comma").replace(
            "Data, secrets and stop conditions:", "**Data, secrets and stop conditions**:")
        self.assertEqual(ticket.template_status(CFG, text)[SECTION], "ok")

    def test_a_deleted_heading_is_still_missing(self):
        self.assertEqual(ticket.template_status(CFG, body("missing"))[SECTION], "missing")

    def test_the_configured_heading_still_passes(self):
        status = ticket.template_status(CFG, body("slash"))
        self.assertEqual(status[SECTION], "ok")

    def test_every_section_of_a_written_body_is_found(self):
        for case in ("comma", "slash"):
            status = ticket.template_status(CFG, body(case))
            self.assertEqual([s for s, v in status.items() if v != "ok"], [], case)

    def test_an_unknown_heading_is_missing(self):
        text = body("slash").replace(SECTION, "Data, secrets and stop condition")
        self.assertEqual(ticket.template_status(CFG, text)[SECTION], "missing")

    def test_a_heading_that_names_another_section_is_missing(self):
        text = body("slash").replace(SECTION, "Design context")
        self.assertEqual(ticket.template_status(CFG, text)[SECTION], "missing")

    def test_the_configured_names_and_their_order_do_not_change(self):
        self.assertEqual(CFG["template"], CONFIG["template"])


class TicketStartProofTest(unittest.TestCase):
    """The three `ticket start --dry-run` cases, on the real CLI."""

    def test_the_three_cases(self):
        sys.path.insert(0, str(ROOT))
        spec = importlib.util.spec_from_file_location(
            "ticket_start_proof", ROOT / "tests" / "ticket_start_proof.py")
        proof = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(proof)
        for case, expected in proof.CASES:
            _, result = proof.run_case(case)
            output = result.stdout + result.stderr
            self.assertIn(expected, output, case)


if __name__ == "__main__":
    unittest.main()
