import argparse
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HILLCLIMB = ROOT / "coordinator/evals/hillclimb"
sys.path[:0] = [str(ROOT), str(HILLCLIMB)]

import burst
import daily3
import install_coordinator

LABEL_KEYS = (
    "id", "kind", "item_text", "options", "answer", "recommended", "agree",
    "ts", "source", "reason",
)


class Recorder:
    def __init__(self, guesses):
        self.guesses = guesses
        self.text = ""
        self.checked = False
        self.three_before_print = False

    def write(self, chunk):
        if not self.checked:
            self.checked = True
            self.three_before_print = len(self.guesses.read_text().splitlines()) == 3
        self.text += chunk
        return len(chunk)

    def flush(self):
        pass


class DailyPick(unittest.TestCase):
    def pick(self, base):
        decisions = base / "decisions.json"
        items = [
            {
                "id": f"a{n}",
                "kind": "ask",
                "title": f"Merge PR {900 + n} now?",
                "options": [
                    {"label": "merge it", "recommended": True},
                    {"label": "hold it"},
                ],
            }
            for n in range(1, 6)
        ]
        decisions.write_text(json.dumps({"updated": "2026-01-01T00:00:00Z", "items": items}))
        guesses = base / "daily3_guesses.jsonl"
        out = Recorder(guesses)
        with mock.patch.object(daily3, "DECISIONS", decisions), \
                mock.patch.object(daily3, "GUESSES", guesses), \
                mock.patch.object(daily3, "BURST", base / "burst_queue.jsonl"), \
                mock.patch("sys.stdout", out):
            rc = daily3.cmd_pick(argparse.Namespace(n=3))
        rows = [json.loads(line) for line in guesses.read_text().splitlines() if line.strip()]
        return rc, [row["label_id"] for row in rows], out

    def test_pick_writes_three_guesses_before_printing_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            rc, ids, out = self.pick(Path(first).resolve())
            self.assertEqual(rc, 0)
            self.assertEqual(ids, ["a1", "a2", "a3"])
            self.assertTrue(out.three_before_print)
            rc_again, ids_again, _ = self.pick(Path(second).resolve())
            self.assertEqual(rc_again, 0)
            self.assertEqual(ids_again, ids)


class DailyRecord(unittest.TestCase):
    def env(self, base):
        labels = base / "labels.jsonl"
        labels.write_text("")
        split = base / "split.json"
        split.write_text(
            json.dumps({"splits": {"FINAL": [], "DEV": [], "HELDOUT": []}, "counts": {}})
        )
        guesses = base / "daily3_guesses.jsonl"
        guesses.write_text(json.dumps({
            "ts": "2026-01-01T00:00:00Z",
            "label_id": "x1",
            "kind": "merge",
            "item_text": "Merge PR 901 now?",
            "options": ["merge it", "hold it"],
            "guess": "merge it",
            "guess_source": "recorded recommended option",
        }) + "\n")
        return labels, split, guesses

    def record(self, base, labels, split, guesses):
        with mock.patch.object(daily3, "LABELS", labels), \
                mock.patch.object(daily3, "SPLIT", split), \
                mock.patch.object(daily3, "GUESSES", guesses), \
                mock.patch.object(daily3, "BURST", base / "burst_queue.jsonl"), \
                mock.patch.object(daily3, "HARD", base / "hard_set.jsonl"), \
                mock.patch.object(daily3, "DECISIONS", base / "missing_decisions.json"), \
                mock.patch.object(daily3, "relock", return_value=True), \
                redirect_stdout(StringIO()):
            return daily3.main(
                ["record", "--id", "x1", "--choice", "merge it", "--reason", "ok"]
            )

    def test_record_appends_one_label_with_required_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            labels, split, guesses = self.env(base)
            self.assertEqual(self.record(base, labels, split, guesses), 0)
            rows = [json.loads(line) for line in labels.read_text().splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            for key in LABEL_KEYS:
                self.assertIn(key, rows[0])
            self.assertEqual(rows[0]["answer"], "merge it")

    def test_record_refuses_duplicate_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            labels, split, guesses = self.env(base)
            self.assertEqual(self.record(base, labels, split, guesses), 0)
            self.assertEqual(self.record(base, labels, split, guesses), 2)
            self.assertEqual(len([l for l in labels.read_text().splitlines() if l.strip()]), 1)


def panel_row(ts, i, title):
    return {
        "ts": ts, "f": "s.jsonl", "i": i, "title": title,
        "options": ["merge it", "hold it"], "rec": ["merge it"], "kind": "ask",
    }


class BurstMining(unittest.TestCase):
    def test_mines_only_unanswered_thin_kinds_and_is_idempotent(self):
        panel = {
            "m1": [panel_row("2026-01-01T00:00:00Z", 1, "Merge PR 901 now?")],
            "o1": [panel_row("2026-01-02T00:00:00Z", 2, "Which color for the logo?")],
            "b1": [panel_row("2026-01-03T00:00:00Z", 3, "Merge PR 902 now?")],
        }
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            out = base / "burst_queue.jsonl"
            labels = base / "labels.jsonl"
            labels.write_text("")
            with mock.patch.object(burst.B, "load_messages", return_value=[]), \
                    mock.patch.object(burst.B, "load_panel", return_value=panel), \
                    mock.patch.object(burst.B, "load_board", return_value=[{"id": "b1"}]), \
                    mock.patch.object(burst.B, "load_typed", return_value=[]), \
                    mock.patch.object(burst, "OUT", out), \
                    mock.patch.object(burst, "LABELS", labels), \
                    mock.patch.object(burst, "DECISIONS", base / "missing_decisions.json"), \
                    redirect_stdout(StringIO()):
                self.assertEqual(burst.main(), 0)
                first = out.read_bytes()
                self.assertEqual(burst.main(), 0)
                second = out.read_bytes()
            rows = [json.loads(line) for line in first.decode().splitlines() if line.strip()]
            self.assertEqual([row["id"] for row in rows], ["m1"])
            self.assertEqual(rows[0]["answer"], "")
            self.assertEqual(first, second)


class InstallPlan(unittest.TestCase):
    def test_install_changes_list_hillclimb_code_and_no_data_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            home = base / "home"
            home.mkdir()
            coordinator = base / "coordinator"
            coordinator.mkdir()
            with mock.patch.object(install_coordinator, "shim_item", return_value=None):
                pending = install_coordinator.changes(ROOT, home, coordinator)
            root = coordinator / "evals/hillclimb"
            names = {
                target.relative_to(root).as_posix()
                for target, _, _ in pending
                if target.is_relative_to(root)
            }
            for name in (
                "build_labels.py", "daily3.py", "burst.py",
                "arms/plain_agent.py", "README.md",
            ):
                self.assertIn(name, names)
            self.assertEqual(
                [name for name in names if name.endswith(".jsonl") or name == "split.json"],
                [],
            )
