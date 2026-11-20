"""The gate bar carries the convergence rule, and the prompts carry the rule.

The convergence rule (Shyam, 2026-11-18) is one text: the merge bar that
both gate brief builders read carries it, so the brief a reviewer gets
carries it too. The question rule for Shyam is one sentence as well, and
the builder rules, the reviewer prompt and the gate bar all carry it.
"""

import sys
import unittest
from pathlib import Path

from coordinator.bin import gate_bar

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "coordinator" / "bin"
# `gate_policy` imports its neighbours by bare name, the way it runs from
# the installed bin directory.
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

ROUND_ONE = "List every critical and major, not only the first."
LATER_ROUNDS = (
    "A major blocks only when it is an open prior finding, sits in lines changed since the previous "
    "reviewed head, or is a regression the repair caused (state the causal path). Every other new "
    "finding is minor.",
)
SEVERITY = (
    "a bug at file:line that is likely in this fleet's real use or hard to undo",
    "an attacker inside our own agents",
    "Minors never fail a PR",
    "A critical blocks in any round and anywhere in the code, but only with a concrete trigger and evidence.",
)
SHYAM = ("When a question is for Shyam, start it with 'Shyam,' so the board routes it to "
         "Needs you; otherwise the question goes to the coordinator.")


def flat(text):
    return " ".join(text.split())


class GateBarTests(unittest.TestCase):
    def test_the_round_brief_carries_the_convergence_rule(self):
        import gate_policy
        first = gate_policy.round_brief(None, "a" * 40)
        later = gate_policy.round_brief({"round": 2, "previous": "b" * 40, "open": "", "next": 1}, "a" * 40)
        self.assertIn(ROUND_ONE, first)
        for text in (first, later):
            self.assertIn(gate_policy.ROUND_CAP_RULE, text)
        for line in LATER_ROUNDS:
            self.assertIn(line, later)

    def test_the_gate_brief_carries_the_bar(self):
        import gate_policy
        brief = gate_policy.build_gate_brief({"key": "MO", "projectId": "fixture"},
                                              "shyamsivakumar/mac-ops", 554, 554,
                                              "a" * 40, publisher=False, base="main")
        self.assertIn(gate_bar.REVIEW_BAR, brief)
        self.assertIn(ROUND_ONE, brief)

    def test_the_bar_carries_the_severity_bar(self):
        for line in SEVERITY:
            self.assertIn(line, gate_bar.REVIEW_BAR)

    def test_the_reviewer_prompt_carries_the_severity_bar(self):
        prompt = flat((ROOT / "coordinator" / "config" / "agents" / "code-reviewer.md").read_text())
        for phrase in ("likely to happen in this fleet's real use",
                       "State in one sentence how it happens in practice",
                       "an attacker inside our own agents",
                       "they never fail a PR",
                       "since the previous reviewed head",
                       "a report with only minors passes"):
            self.assertIn(phrase, prompt)

    def test_the_bar_carries_the_question_rule_for_shyam(self):
        self.assertIn(SHYAM, gate_bar.GATE_BAR)

    def test_the_builder_rules_carry_the_question_rule_for_shyam(self):
        rules = (ROOT / "coordinator" / "config" / "AGENT-RULES.md").read_text()
        self.assertIn(SHYAM, rules)

    def test_the_reviewer_prompt_carries_the_question_rule_for_shyam(self):
        prompt = (ROOT / "coordinator" / "config" / "agents" / "code-reviewer.md").read_text()
        self.assertIn(flat(SHYAM), flat(prompt))


if __name__ == "__main__":
    unittest.main()
