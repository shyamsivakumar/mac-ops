import contextlib
import importlib.util
import io
import json
import shlex
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCORE_PATH = Path(__file__).resolve().parents[1] / "evals" / "ladder" / "score.py"
spec = importlib.util.spec_from_file_location("ladder_score", SCORE_PATH)
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

OPTIONS = ["alpha", "beta", "gamma"]


def label(cid, answer, recommended_option):
    return {
        "id": cid,
        "kind": "choice",
        "item_text": f"item {cid}",
        "recommended": recommended_option,
        "recommended_option": recommended_option,
        "answer": answer,
        "agree": True,
        "ts": "2026-01-01T00:00:00+00:00",
        "source": "test",
        "options": list(OPTIONS),
    }


def write_labels(root):
    root = Path(root)
    rows = [
        label("a", "alpha", "alpha"),
        label("b", "beta", "beta"),
        label("c", "free text answer", "alpha"),
        label("d", "gamma", "gamma"),
    ]
    (root / "labels.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    split = {"final": ["a", "b", "c"], "dev": ["a", "b", "c"], "heldout": ["a", "b", "c"]}
    (root / "split.json").write_text(json.dumps(split))
    return root


class LadderScoreTests(unittest.TestCase):
    def test_read_cases_uses_split_and_counts_unscored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_labels(tmp)
            cases, unscored = score.read_cases(root, "heldout")
            self.assertEqual([c["id"] for c in cases], ["a", "b"])
            self.assertEqual(unscored, 1)

    def test_pick_is_deterministic_and_varies_across_repeats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_labels(tmp)
            cases, _ = score.read_cases(root, "heldout")
            case = cases[0]
            self.assertEqual(score.pick("first-option", None, case, 3), score.pick("first-option", None, case, 3))
            self.assertEqual(score.pick("random", None, case, 5), score.pick("random", None, case, 5))
            firsts = [score.pick("first-option", None, case, r) for r in range(20)]
            self.assertGreaterEqual(len(set(firsts)), 2)

    def test_locked_score_recorded_arm_and_random_determinism(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_labels(tmp)
            result = score.locked_score(root, "heldout", "recorded", None, "first-option", None, 3)
            self.assertEqual([r["arm"] for r in result["repeat_scores"]], [100.0, 100.0, 100.0])
            for key in ("beats_noise", "paired_se", "min_detectable_lift", "unscored", "baseline"):
                self.assertIn(key, result)
            self.assertEqual(result["baseline"], "first-option")
            self.assertEqual(result["unscored"], 1)
            one = score.locked_score(root, "heldout", "random", None, "first-option", None, 3)
            two = score.locked_score(root, "heldout", "random", None, "first-option", None, 3)
            self.assertEqual(one["per_case"], two["per_case"])

    def test_cli_lock_and_locked_detect_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_labels(tmp)
            lock = Path(tmp) / "score.lock"
            out = Path(tmp) / "out.json"
            self.assertEqual(score.main(["lock", "--labels", str(root), "--lock", str(lock)]), 0)
            argv = [
                "locked", "--labels", str(root), "--arm", "recorded",
                "--baseline", "first-option", "--repeats", "2",
                "--lock", str(lock), "--json", str(out),
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(score.main(argv), 0)
            self.assertTrue(out.exists())
            with (root / "labels.jsonl").open("a") as handle:
                handle.write(json.dumps(label("e", "alpha", "alpha")) + "\n")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(score.main(argv), 3)
            split = json.loads((root / "split.json").read_text())
            split["heldout"] = ["a", "b"]
            (root / "split.json").write_text(json.dumps(split))
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(score.main(argv), 3)

    def test_final_log_blocks_within_seven_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_labels(tmp)
            lock = Path(tmp) / "score.lock"
            log = Path(tmp) / "final.jsonl"
            score.main(["lock", "--labels", str(root), "--lock", str(lock)])
            argv = [
                "final", "--labels", str(root), "--arm", "recorded",
                "--baseline", "first-option", "--repeats", "2",
                "--lock", str(lock), "--final-log", str(log),
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(score.main(argv), 0)
            self.assertEqual(len(log.read_text().splitlines()), 1)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(score.main(argv), 5)
            old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            row = {"ts": old, "arm": "recorded", "baseline": "first-option", "lift": 0.0}
            log.write_text(json.dumps(row) + "\n")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(score.main(argv), 0)

    def test_arm_cmd_matches_first_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_labels(tmp)
            code = 'import sys,json;print(json.load(sys.stdin)["options"][0])'
            arm_cmd = "python3 -c " + shlex.quote(code)
            custom = score.locked_score(root, "heldout", "custom", arm_cmd, "first-option", None, 2)
            builtin = score.locked_score(root, "heldout", "first-option", None, "first-option", None, 2)
            self.assertEqual(
                [d["arm"] for d in custom["per_case"]],
                [d["arm"] for d in builtin["per_case"]],
            )


if __name__ == "__main__":
    unittest.main()
