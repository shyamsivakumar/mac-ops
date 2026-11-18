"""The answer format for a question to Shyam, in every agent prompt.

The board's Needs-you cards read this format as buttons, so the builder
brief, the gate brief and the reviewer prompt have to carry the same
wording. The text lives once in `coordinator/bin/answer_format.py`; the
reviewer prompt is Markdown and cannot import it, so that copy is
asserted here instead.
"""
import sys
import unittest
from pathlib import Path

from tests.test_gatekeep_backstop_reviewer import load_coordq
from tests.test_check_proof import load

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "coordinator" / "bin"
REVIEWER_PROMPT = ROOT / "coordinator" / "config" / "agents" / "code-reviewer.md"
# `ticket` and `gate_policy` import their neighbours by bare name, the way
# they run from the installed bin directory.
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))
RECOMMENDED = "(Recommended: <option text word for word>)"
OPTION_ONE = "`1. <option>`"


def flat(text):
    return " ".join(text.split())


class AnswerFormatTests(unittest.TestCase):
    def setUp(self):
        self.answer_format = load(BIN / "answer_format.py", "answer_format").ANSWER_FORMAT
        self.ticket = load(BIN / "ticket", "ticket")

    def test_the_rule_carries_the_approved_shape(self):
        self.assertIn(OPTION_ONE, self.answer_format)
        self.assertIn(RECOMMENDED, self.answer_format)
        self.assertIn("2 to 4 options", self.answer_format)

    def test_the_builder_brief_carries_the_rule(self):
        brief = self.ticket.assemble_brief({"types": {"review": "gate"}},
                                           {"body": "Do the work.", "url": "https://fixture/1"},
                                           "fixture-run", {"comments": []})
        self.assertIn(self.answer_format, brief)

    def test_the_gate_brief_carries_the_rule(self):
        message = load_coordq().gate_args({"key": "MO", "projectId": "P"},
                                          "shyamsivakumar/mac-ops", 539, 540,
                                          "a" * 40, publisher=False, model={})["message"]
        self.assertIn(self.answer_format, message)

    def test_the_reviewer_prompt_carries_the_same_sentence(self):
        self.assertIn(flat(self.answer_format), flat(REVIEWER_PROMPT.read_text()))
