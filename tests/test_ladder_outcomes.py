import importlib.util
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

LADDER = Path(__file__).resolve().parents[1] / "evals" / "ladder"


def load(name):
    spec = importlib.util.spec_from_file_location(name, LADDER / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


outcomes, score = load("outcomes"), load("score")
REPO = "shyamsivakumar/strategy-replay-workbench"
LABEL_TS = "2026-11-15T00:00:00.000Z"
MERGED = {"state": "MERGED", "mergedAt": "2026-11-15T01:00:00Z", "mergeCommit": {"oid": "abc123"}, "title": "t"}


def fake_gh(view=MERGED, commits=(), statuses=()):
    def gh(args):
        if args[0] == "pr":
            return view
        if "--slurp" in args:
            return [[{"sha": f"r{i}", "commit": {"message": m}} for i, m in enumerate(commits)]]
        return {"statuses": [{"context": c, "state": s} for c, s in statuses]}
    return gh


class OutcomeFixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.journal = self.dir / "journal"
        self.journal.mkdir()
        self.labels = self.dir / "labels"
        self.labels.mkdir()

    def write_labels(self, *labels):
        (self.labels / "labels.jsonl").write_text("".join(json.dumps(l) + "\n" for l in labels))
        (self.labels / "split.json").write_text(json.dumps({"heldout": [l["id"] for l in labels]}))

    def write_journal(self, *events):
        (self.journal / "events-2026-11.jsonl").write_text("not json\n" + "".join(json.dumps(e) + "\n" for e in events))

    def fetch(self, gh, answer="yes", **label):
        self.write_labels({"id": "c1", "item_text": f"merge PR #7 in {REPO}?", "answer": answer, "options": ["yes", "no"], "ts": LABEL_TS, **label})
        now = datetime(2026, 11, 22, tzinfo=timezone.utc)
        return outcomes.fetch(self.labels, self.dir / "outcomes.jsonl", self.journal, gh=gh, now=now)[0]


class FetchChecks(OutcomeFixture):
    def test_revert_found(self):
        row = self.fetch(fake_gh(commits=['Revert "x"\n\nThis reverts commit abc123.']))
        self.assertIs(row["reverted"], True)
        self.assertEqual(row["pr"], 7)

    def test_main_broke_uses_only_mac_statuses(self):
        row = self.fetch(fake_gh(statuses=[("srw/agent-check", "failure"), ("Vercel", "success")]))
        self.assertIs(row["main_broke"], True)
        row = self.fetch(fake_gh(statuses=[("Vercel", "failure")]))
        self.assertIsNone(row["main_broke"])

    def test_rollback_event(self):
        later = datetime(2026, 11, 16, tzinfo=timezone.utc).timestamp()
        self.write_journal({"event": "rollback", "repo": REPO, "pr": 7, "ts": later})
        self.assertIs(self.fetch(fake_gh())["rollback_or_incident"], True)

    def test_recut_event_and_re_cut_answer(self):
        later = datetime(2026, 11, 16, tzinfo=timezone.utc).timestamp()
        self.write_journal({"event": "recut", "repo": REPO, "pr": 7, "ts": later})
        self.assertIs(self.fetch(fake_gh())["recut"], True)
        self.assertIsNone(self.fetch(fake_gh(), answer="Re-cut it")["recut"])

    def test_all_unknown(self):
        row = self.fetch(fake_gh(view=None))
        self.assertEqual([row[k] for k in score.OUTCOME_CHECKS], [None] * 4)

    def test_label_without_subject_gets_no_row(self):
        self.write_labels({"id": "c2", "item_text": "Should I restart?", "answer": "yes", "ts": LABEL_TS})
        self.assertEqual(outcomes.fetch(self.labels, self.dir / "o.jsonl", self.journal, gh=fake_gh()), [])


class Scoring(OutcomeFixture):
    def test_option_mapping(self):
        bad, good, unknown = {"reverted": True}, {"reverted": False}, {k: None for k in score.OUTCOME_CHECKS}
        merge = {"item_text": "Merge PR #7?", "answer": "yes"}
        self.assertFalse(score.outcome_correct("yes", bad, merge))
        self.assertTrue(score.outcome_correct("yes", good, merge))
        self.assertTrue(score.outcome_correct("no", bad, merge))
        self.assertFalse(score.outcome_correct("no", good, merge))
        self.assertIsNone(score.outcome_correct("yes", unknown, merge))
        recut = {"item_text": "Re-cut PR #7?", "answer": "yes, merge"}
        self.assertIsNone(score.outcome_correct("Re-cut it into smaller pull requests", bad, recut))

    def test_yes_polarity_follows_the_question(self):
        self.assertEqual(score.stance("yes", {"item_text": "Should I merge PR #7?"}), "approve")
        self.assertEqual(score.stance("yes", {"item_text": "Should I hold PR #7?"}), "reject")
        self.assertEqual(score.stance("no", {"item_text": "Should I hold PR #7?"}), "approve")
        self.assertIsNone(score.stance("yes", {"item_text": "Should I restart the tab?"}))

    def test_held_pr_is_unscored_for_every_arm(self):
        held = {"item_text": "Merge PR #7?", "answer": "no"}
        good = {"reverted": False, "main_broke": False}
        self.assertIsNone(score.outcome_correct("yes", good, held))
        self.assertIsNone(score.outcome_correct("no", good, held))
        hold_question = {"item_text": "Hold PR #7?", "answer": "yes"}
        self.assertIsNone(score.outcome_correct("yes", good, hold_question))

    def test_malformed_outcomes_line_fails_with_line_number(self):
        self.write_labels({"id": "c1", "item_text": "x", "answer": "yes", "options": ["yes", "no"], "ts": LABEL_TS})
        (self.labels / "outcomes.jsonl").write_text('{"id": "c1"}\nnot json\n')
        with self.assertRaisesRegex(ValueError, r"outcomes.jsonl:2"):
            score.read_outcomes(self.labels)

    def test_lock_includes_outcomes_when_present(self):
        self.write_labels({"id": "c1", "item_text": "x", "answer": "yes", "options": ["yes", "no"], "ts": LABEL_TS})
        self.assertNotIn("outcomes", score.lock_hashes(self.labels))
        (self.labels / "outcomes.jsonl").write_text("{}\n")
        first = score.lock_hashes(self.labels)["outcomes"]
        (self.labels / "outcomes.jsonl").write_text('{"id": "c1"}\n')
        self.assertNotEqual(first, score.lock_hashes(self.labels)["outcomes"])

    def test_scoring_makes_no_network_call(self):
        self.write_labels({"id": "c1", "item_text": "Merge PR #7?", "answer": "yes", "options": ["yes", "no"], "ts": LABEL_TS, "recommended_option": "yes"})
        (self.labels / "outcomes.jsonl").write_text(json.dumps({"id": "c1", "reverted": True, "main_broke": None, "rollback_or_incident": None, "recut": None}) + "\n")
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("network")):
            result = score.locked_score(self.labels, "heldout", "recorded", None, "recorded", None, 1)
        self.assertEqual(result["outcome_correct"]["arm"], {"scored": 1, "correct": 0, "rate": 0.0})
        self.assertEqual(result["outcome_correct"]["cases_with_outcome"], 1)


if __name__ == "__main__":
    unittest.main()
