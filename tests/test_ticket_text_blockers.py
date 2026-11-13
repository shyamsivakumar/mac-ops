"""Tests for the text blocker checks in the ticket CLI.

The CLI is a script without a .py suffix, so it is loaded by path.
"""
import importlib.util
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_ticket():
    path = ROOT / "coordinator" / "bin" / "ticket"
    loader = SourceFileLoader("ticket_cli", str(path))
    spec = importlib.util.spec_from_loader("ticket_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


ticket = load_ticket()

CFG = {"repos": {"shyamsivakumar/strategy-replay-workbench": {"key": "SRW"}}}
REPO = "shyamsivakumar/strategy-replay-workbench"


def issue(body, comments=None):
    return {"body": body, "comments": comments or []}


class BodySectionTest(unittest.TestCase):
    def test_section_stops_at_the_next_heading(self):
        body = "## Blocked by\nSRW-1018 (#806).\n\n## Acceptance and proof\nnot a blocker\n"
        self.assertEqual(ticket.body_section(body, "Blocked by"), "SRW-1018 (#806).")

    def test_missing_section_is_none(self):
        self.assertIsNone(ticket.body_section("## Goal and why\nx\n", "Blocked by"))

    def test_none_section_passes(self):
        self.assertEqual(ticket.section_blocker_reasons(CFG, REPO, issue("## Blocked by\nNone.\n")), [])


class ApprovalSentenceTest(unittest.TestCase):
    def test_design_review_sentence_is_caught(self):
        sentence = "Build only after the separate Opus design review the design document requires."
        self.assertTrue(ticket.requires_approval(sentence))

    def test_sentence_without_a_keyword_is_not_caught(self):
        self.assertFalse(ticket.requires_approval("Start only after the remaining work has merged."))

    def test_approval_word_alone_is_not_caught(self):
        self.assertFalse(ticket.requires_approval("No build starts before approval."))

    def test_gate_boilerplate_is_not_a_trigger(self):
        body = "## Gate\nFinal line exactly `VERDICT: PASS` or `VERDICT: FAIL`.\n"
        self.assertEqual(ticket.body_sentences(body), ["Final line exactly `VERDICT: PASS` or `VERDICT: FAIL`."])
        self.assertEqual(ticket.approval_reasons(CFG, REPO, issue(body)), [])

    def test_refusal_names_the_sentence(self):
        body = ("## Data/secrets and stop conditions\n"
                "Build only after the separate Opus design review the design document requires.\n")
        reasons = ticket.approval_reasons(CFG, REPO, issue(body))
        self.assertEqual(len(reasons), 1)
        self.assertIn("requires an approval before building", reasons[0])
        self.assertIn("Build only after the separate Opus design review", reasons[0])

    def test_recorded_verdict_clears_the_refusal(self):
        body = "## Data/secrets and stop conditions\nBuild only after the separate Opus design review.\n"
        comments = [{"body": "Opus reviewed it. VERDICT: PASS", "url": "https://github.com/o/r/issues/1#issuecomment-2"}]
        self.assertEqual(ticket.approval_reasons(CFG, REPO, issue(body, comments)), [])

    def test_gate_boilerplate_is_not_a_verdict(self):
        body = ("## Goal\nx\n\n## Gate\nFinal line exactly `VERDICT: PASS` or `VERDICT: FAIL`.\n\n"
                "## Data\nBuild only after the separate Opus design review.\n")
        reasons = ticket.approval_reasons(CFG, REPO, issue(body))
        self.assertEqual(len(reasons), 1)
        self.assertIn("Build only after the separate Opus design review", reasons[0])


class SectionBlockerTest(unittest.TestCase):
    def setUp(self):
        self.states = {("shyamsivakumar/strategy-replay-workbench", 806): "open",
                       ("shyamsivakumar/strategy-replay-workbench", 898): "merged",
                       ("shyamsivakumar/strategy-replay-workbench", 490): "open"}
        self.keys = {("shyamsivakumar/strategy-replay-workbench", "SRW", "1018"): 806,
                     ("shyamsivakumar/strategy-replay-workbench", "SRW", "789"): 490}
        ticket.REF_STATE.clear()
        ticket.KEY_ISSUE.clear()
        ticket.COMMENT_TEXT.clear()
        ticket.reference_state = lambda repo, number: self.states.get((repo, number))
        ticket.resolve_key_issue = lambda repo, key, number: self.keys.get((repo, key, number))

    def test_open_key_reference_is_named_with_its_number(self):
        body = "## Blocked by\nSRW-1018 (#806, still open).\n"
        reasons = ticket.section_blocker_reasons(CFG, REPO, issue(body))
        self.assertEqual(reasons, ["SRW-1018 (#806) is still open"])

    def test_merged_pull_request_passes(self):
        body = "## Blocked by\nB1 #898 is complete.\n"
        self.assertEqual(ticket.section_blocker_reasons(CFG, REPO, issue(body)), [])

    def test_closed_reference_passes(self):
        self.states[("shyamsivakumar/strategy-replay-workbench", 898)] = "closed"
        body = "## Blocked by\nB1 #898 is complete.\n"
        self.assertEqual(ticket.section_blocker_reasons(CFG, REPO, issue(body)), [])

    def test_unresolved_key_is_named(self):
        body = "## Blocked by\nSRW-4242 must merge first.\n"
        reasons = ticket.section_blocker_reasons(CFG, REPO, issue(body))
        self.assertEqual(len(reasons), 1)
        self.assertIn("SRW-4242", reasons[0])

    def test_foreign_keys_are_ignored(self):
        body = "## Blocked by\nPR-905 is merged and JIRA-12 is done.\n"
        self.assertEqual(ticket.section_blocker_reasons(CFG, REPO, issue(body)), [])

    def test_closed_but_unmerged_pull_request_is_refused(self):
        self.states[(REPO, 905)] = "unmerged"
        body = "## Blocked by\nThe part 1 pull request #905 is closed.\n"
        self.assertEqual(ticket.section_blocker_reasons(CFG, REPO, issue(body)),
                         [f"{REPO}#905 is not merged"])

    def test_none_with_prose_passes(self):
        body = "## Blocked by\nNone. This is the frontier ticket and can start immediately.\n"
        self.assertEqual(ticket.section_blocker_reasons(CFG, REPO, issue(body)), [])


TEMPLATE = ["Goal and why", "Context", "Scope and non-goals", "Design fit", "Blocked by",
            "Acceptance and proof", "CI", "Must not cause", "Data/secrets and stop conditions",
            "Rollback", "Gate", "Finish"]

START_CFG = {
    "repos": {"shyamsivakumar/strategy-replay-workbench": {"key": "SRW"}},
    "types": {"standard": "builder", "review": "opus"},
    "models": {"builder": {"selection": {}, "vendor": "one"},
               "opus": {"selection": {}, "vendor": "two"}},
    "labels": {"stage": ["backlog", "todo"], "priority": ["1"], "type": ["standard"]},
    "template": TEMPLATE,
}


def templated_body(sections=None):
    sections = sections or {}
    return "\n".join(f"## {name}\n{sections.get(name, 'x')}\n" for name in TEMPLATE)


def start_issue(body):
    return {
        "id": "I_1", "number": 1, "url": "https://github.com/o/r/issues/1", "title": "SRW-1 · x",
        "state": "OPEN", "body": body, "comments": [],
        "labels": [{"name": "stage:todo"}, {"name": "type:standard"}, {"name": "priority:1"},
                   {"name": "builder:builder"}, {"name": "reviewer:opus"}],
        "blockedBy": {"nodes": [], "totalCount": 0},
    }


class ValidateStartTest(unittest.TestCase):
    def setUp(self):
        self.saved = ticket.text_blocker_reasons
        ticket.text_blocker_reasons = lambda cfg, repo, issue: ["SRW-9 (#9) is still open"]
        self.addCleanup(lambda: setattr(ticket, "text_blocker_reasons", self.saved))

    def test_text_blockers_refuse_the_start(self):
        with self.assertRaises(ticket.Refuse) as caught:
            ticket.validate_start(START_CFG, REPO, start_issue(templated_body()))
        self.assertIn("text blockers: SRW-9 (#9) is still open", str(caught.exception))

    def test_force_skips_the_text_blockers(self):
        started = ticket.validate_start(START_CFG, REPO, start_issue(templated_body()), check_text=False)
        self.assertEqual(started["builderAlias"], "builder")

    def test_native_blocker_refusal_keeps_its_own_text(self):
        issue = start_issue(templated_body())
        issue["blockedBy"] = {"nodes": [{"number": 806, "state": "OPEN", "title": "t",
                                         "url": "https://github.com/shyamsivakumar/strategy-replay-workbench/issues/806"}],
                              "totalCount": 1}
        with self.assertRaises(ticket.Refuse) as caught:
            ticket.validate_start(START_CFG, REPO, issue)
        self.assertTrue(str(caught.exception).startswith("blocked by open "))


if __name__ == "__main__":
    unittest.main()
