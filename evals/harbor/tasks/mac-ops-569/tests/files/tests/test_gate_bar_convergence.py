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

CONVERGENCE = (
    "Round 1 must list every critical and major found, not just the first.",
    "Round 2 and later: a new major (not raised in an earlier round of this PR) blocks only "
    "with a failing case (a concrete input or sequence with the wrong result) or inside lines "
    "changed since the last review; otherwise it is a minor under 'Left for later'.",
    "Earlier findings: confirm each is fixed; an unfixed earlier major still blocks.",
    "After 3 review rounds without PASS, the PR is re-cut into smaller PRs or brought to Shyam; "
    "no 4th review as is.",
)
SHYAM = ("When a question is for Shyam, start it with 'Shyam,' so the board routes it to "
         "Needs you; otherwise the question goes to the coordinator.")


def flat(text):
    return " ".join(text.split())


class GateBarTests(unittest.TestCase):
    def test_the_bar_carries_every_line_of_the_convergence_rule(self):
        for line in CONVERGENCE:
            self.assertIn(line, gate_bar.GATE_BAR)

    def test_the_gate_brief_carries_the_convergence_rule(self):
        import gate_policy
        brief = gate_policy.build_gate_brief({"key": "MO", "projectId": "fixture"},
                                              "shyamsivakumar/mac-ops", 554, 554,
                                              "a" * 40, publisher=False, base="main")
        for line in CONVERGENCE:
            self.assertIn(line, brief)

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
