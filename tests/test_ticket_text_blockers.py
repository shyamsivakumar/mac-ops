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

    def test_labelled_section_is_read(self):
        self.assertEqual(ticket.blocked_by_section("Blocked by: SRW-1018 (#806).\n"), "SRW-1018 (#806).")

    def test_bold_labelled_section_is_read(self):
        self.assertEqual(ticket.blocked_by_section("**Blocked by**: None.\n"), "None.")

    def test_labelled_section_is_read_when_there_is_no_heading(self):
        body = "Goal and why: x\nBlocked by: SRW-1018 (#806).\nAcceptance: y\n"
        self.assertEqual(ticket.blocked_by_section(body), "SRW-1018 (#806).")

    def test_heading_wins_over_a_labelled_line(self):
        body = "Blocked by: SRW-1018 (#806).\n\n## Blocked by\nSRW-789 (#490).\n"
        self.assertEqual(ticket.blocked_by_section(body), "SRW-789 (#490).")

    def test_preserved_contract_is_not_the_section(self):
        body = ("## Scope and non-goals\n<details><summary>Preserved original contract</summary>\n\n"
                "Blocked by: #49, #51, #52\n\n</details>\n")
        self.assertIsNone(ticket.blocked_by_section(body))


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
                       ("shyamsivakumar/strategy-replay-workbench", 816): "open",
                       ("shyamsivakumar/strategy-replay-workbench", 898): "merged",
                       ("shyamsivakumar/strategy-replay-workbench", 490): "open"}
        self.keys = {("shyamsivakumar/strategy-replay-workbench", "SRW", "1018"): 806,
                     ("shyamsivakumar/strategy-replay-workbench", "SRW", "789"): 490}
        ticket.REF_STATE.clear()
        ticket.KEY_ISSUE.clear()
        ticket.COMMENT_TEXT.clear()
        saved_state = ticket.reference_state
        saved_key = ticket.resolve_key_issue
        self.addCleanup(lambda: setattr(ticket, "reference_state", saved_state))
        self.addCleanup(lambda: setattr(ticket, "resolve_key_issue", saved_key))
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

    def test_labelled_section_names_an_open_key(self):
        body = "Blocked by: SRW-1018, SRW-1019.\n"
        self.keys[("shyamsivakumar/strategy-replay-workbench", "SRW", "1019")] = 816
        reasons = ticket.section_blocker_reasons(CFG, REPO, issue(body))
        self.assertEqual(reasons, ["SRW-1018 (#806) is still open", "SRW-1019 (#816) is still open"])

    def test_labelled_none_passes(self):
        self.assertEqual(ticket.section_blocker_reasons(CFG, REPO, issue("Blocked by: none.\n")), [])

    def test_preserved_contract_does_not_block(self):
        body = ("## Scope and non-goals\n<details><summary>Preserved contract</summary>\n\n"
                "Blocked by: #806\n\n</details>\n")
        self.assertEqual(ticket.section_blocker_reasons(CFG, REPO, issue(body)), [])


class ResolveKeyIssueTest(unittest.TestCase):
    def setUp(self):
        ticket.KEY_ISSUE.clear()
        self.saved = ticket.gh_json
        self.titles = []
        self.addCleanup(lambda: setattr(ticket, "gh_json", self.saved))

    def fake(self, args):
        return {"items": [{"number": 900 + i, "title": title} for i, title in enumerate(self.titles)]}

    def resolve(self, titles, number):
        self.titles = titles
        ticket.gh_json = self.fake
        return ticket.resolve_key_issue(REPO, "SRW", number)

    def test_middle_dot_title_resolves(self):
        self.assertEqual(self.resolve(["SRW-1119 · Hash-route tabs"], 1119), 900)

    def test_colon_title_resolves(self):
        self.assertEqual(self.resolve(["SRW-1119: Hash-route tabs"], 1119), 900)

    def test_a_longer_number_does_not_resolve(self):
        self.assertIsNone(self.resolve(["SRW-11190 · Something else"], 1119))

    def test_another_ticket_does_not_resolve(self):
        self.assertIsNone(self.resolve(["SRW-1118 · Something else"], 1119))


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
        self.saved_pulls = ticket.referencing_pulls
        ticket.referencing_pulls = lambda repo, number: []
        self.addCleanup(lambda: setattr(ticket, "referencing_pulls", self.saved_pulls))

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

    def test_an_open_pull_request_refuses_the_start(self):
        ticket.referencing_pulls = lambda repo, number: [
            {"number": 195, "state": "open", "merged": False, "mergedAt": None,
             "createdAt": "2026-11-13T10:00:00Z"}]
        with self.assertRaises(ticket.Refuse) as caught:
            ticket.validate_start(START_CFG, REPO, start_issue(templated_body()))
        self.assertIn("open pull request #195", str(caught.exception))

    def test_a_merged_pull_request_refuses_the_start(self):
        ticket.referencing_pulls = lambda repo, number: [
            {"number": 190, "state": "closed", "merged": True, "mergedAt": "2026-11-13T10:00:00Z",
             "createdAt": "2026-11-13T09:00:00Z"}]
        with self.assertRaises(ticket.Refuse) as caught:
            ticket.validate_start(START_CFG, REPO, start_issue(templated_body()))
        self.assertIn("already merged via #190; close the issue", str(caught.exception))


class ReferenceWordTest(unittest.TestCase):
    def test_refs_is_a_reference(self):
        self.assertTrue(ticket.references_issue("Refs #160", 160))

    def test_fixes_is_a_reference(self):
        self.assertTrue(ticket.references_issue("Fixes #160", 160))

    def test_closes_is_a_reference(self):
        self.assertTrue(ticket.references_issue("Closes #160", 160))

    def test_the_reference_is_case_insensitive(self):
        self.assertTrue(ticket.references_issue("refs #160", 160))

    def test_another_number_is_not_a_reference(self):
        self.assertFalse(ticket.references_issue("Refs #161", 160))

    def test_a_bare_number_is_not_a_reference(self):
        self.assertFalse(ticket.references_issue("see #160 for the details", 160))

    def test_a_number_without_the_keyword_is_not_a_reference(self):
        self.assertFalse(ticket.references_issue("the coordinator wrote `Refs #<n>` in the brief", 160))

    def test_a_second_number_on_the_line_counts(self):
        self.assertTrue(ticket.references_issue("Refs #161, #160", 160))

    def test_a_number_on_another_line_does_not_count(self):
        self.assertFalse(ticket.references_issue("Fixes #12.\nAlso mentions #160.", 160))

    def test_a_qualified_reference_counts_in_the_same_repository(self):
        self.assertTrue(ticket.references_issue("Refs shyamsivakumar/mac-ops#160", 160, "shyamsivakumar/mac-ops"))

    def test_a_qualified_reference_from_another_repository_does_not_count(self):
        self.assertFalse(ticket.references_issue("Refs shyamsivakumar/other#160", 160, "shyamsivakumar/mac-ops"))


class RestartCommentTest(unittest.TestCase):
    def test_a_coordinator_comment_that_says_the_work_starts_again_is_a_restart(self):
        self.assertTrue(ticket.is_restart_comment("Coordinator: the merge missed the last rule, redo it."))

    def test_a_coordinator_comment_that_closes_is_not_a_restart(self):
        self.assertFalse(ticket.is_restart_comment("Coordinator: verified the merge, closing the issue."))

    def test_a_comment_that_does_not_open_with_coordinator_is_not_a_restart(self):
        self.assertFalse(ticket.is_restart_comment("the merge missed the last rule, redo it."))


class PullGuardTest(unittest.TestCase):
    def setUp(self):
        self.saved = ticket.referencing_pulls
        self.addCleanup(lambda: setattr(ticket, "referencing_pulls", self.saved))
        self.pulls = []
        ticket.referencing_pulls = lambda repo, number: self.pulls

    def pull(self, number, state="open", merged=False, merged_at=None, created_at="2026-11-13T10:00:00Z"):
        return {"number": number, "state": state, "merged": merged, "mergedAt": merged_at,
                "createdAt": created_at}

    def guard(self, comments=None):
        return ticket.pull_guard_reasons(REPO, {"number": 1, "comments": comments or []})

    def test_no_pull_request_passes(self):
        self.assertEqual(self.guard(), [])

    def test_an_open_pull_request_names_the_pull_request(self):
        self.pulls = [self.pull(195)]
        self.assertEqual(self.guard(), ["open pull request #195 already references this issue"])

    def test_the_newest_open_pull_request_is_named(self):
        self.pulls = [self.pull(190, created_at="2026-11-13T10:00:00Z"),
                      self.pull(195, created_at="2026-11-13T11:00:00Z")]
        self.assertEqual(self.guard(), ["open pull request #195 already references this issue"])

    def test_a_merged_pull_request_names_the_merge(self):
        self.pulls = [self.pull(190, state="closed", merged=True, merged_at="2026-11-13T12:00:00Z")]
        self.assertEqual(self.guard(), ["already merged via #190; close the issue"])

    def test_a_restart_after_the_merge_allows_the_start(self):
        self.pulls = [self.pull(190, state="closed", merged=True, merged_at="2026-11-13T12:00:00Z")]
        comments = [{"createdAt": "2026-11-13T13:00:00Z",
                     "body": "Coordinator: the merge missed the last rule, redo it."}]
        self.assertEqual(self.guard(comments), [])

    def test_an_intent_comment_is_not_a_restart(self):
        self.pulls = [self.pull(190, state="closed", merged=True, merged_at="2026-11-13T12:00:00Z")]
        comments = [{"createdAt": "2026-11-13T13:00:00Z",
                     "body": "Starting SRW-1 attempt 2.\n\n<!-- coordinator-ticket "
                             "{\"kind\":\"intent\",\"attempt\":2} -->"}]
        self.assertEqual(self.guard(comments), ["already merged via #190; close the issue"])

    def test_a_coordinator_comment_that_closes_is_not_a_restart(self):
        self.pulls = [self.pull(190, state="closed", merged=True, merged_at="2026-11-13T12:00:00Z")]
        comments = [{"createdAt": "2026-11-13T13:00:00Z",
                     "body": "Coordinator: verified the merge, closing the issue."}]
        self.assertEqual(self.guard(comments), ["already merged via #190; close the issue"])

    def test_a_receipt_is_not_a_restart(self):
        self.pulls = [self.pull(190, state="closed", merged=True, merged_at="2026-11-13T12:00:00Z")]
        comments = [{"createdAt": "2026-11-13T13:00:00Z",
                     "body": "SRW-1 attempt 1: coordq says \"queued #7\".\n\n<!-- coordinator-ticket "
                             "{\"kind\":\"receipt\",\"attempt\":1} -->"}]
        self.assertEqual(self.guard(comments), ["already merged via #190; close the issue"])

    def test_a_closed_unmerged_pull_request_does_not_block(self):
        self.pulls = [self.pull(190, state="closed", merged=False)]
        self.assertEqual(self.guard(), [])


if __name__ == "__main__":
    unittest.main()
