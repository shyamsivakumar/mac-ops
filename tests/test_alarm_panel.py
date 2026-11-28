"""The panel binds an answer to the alarm it was given for.

The panel is a Herdr mod, which Python cannot import, so the rules that
bind an answer live in a module with no imports
(`coordinator/rules/answers.js`) and the mod uses it. These
tests run that module for real, with bun or node, and check the cases
that matter: an answer for an alarm that was replaced is never sent, and
an answer that was never bound to a cause acknowledges nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "coordinator/rules/answers.js"
PANEL = ROOT / "coordinator/mods/coordinator/main.js"
BUN = shutil.which("bun")
NODE = shutil.which("node")

# The probe drives the rules the way the panel does: an answer is built
# from a draft and the cause the board shows now, and it is sent only
# when it is not stale.
PROBE = """
import { answerCause, isStale, restored } from "%(rules)s";

const causeA = "gatekeep failing (last exit code 1)";
const causeB = "gatekeep failing (last exit code 78)";

function decide(draft, shown, typed, saved) {
  const { text, bound } = restored(draft, typed, saved, shown);
  const committed = text ? { kind: "reply", text, cause: bound } : null;
  const answer = committed ? { id: "factory-watchdog", shown, cause: answerCause(committed, shown) } : null;
  const stale = committed ? isStale(committed, shown) : false;
  // The panel acknowledges only an answer that carries a cause and is
  // not stale.
  const acknowledged = answer && answer.cause && !stale ? answer.cause : "";
  return { text, bound, cause: answer ? answer.cause : "", stale, acknowledged, sent: Boolean(committed && !stale) };
}

const out = {
  // A legacy reply for cause A: text, no cause. B has replaced A.
  legacy: decide({ kind: "reply", text: "the fix is in" }, causeB),
  // A bound reply for cause A, sent while B has replaced A.
  boundOther: decide({ kind: "reply", text: "the fix is in", cause: causeA }, causeB),
  // A bound reply for the cause the board shows now.
  boundSame: decide({ kind: "reply", text: "the fix is in", cause: causeB }, causeB),
  // Typing text whose cause was kept, and typing text whose cause was
  // not kept.
  typedKept: decide(null, causeB, "half a th", causeA),
  typedLost: decide(null, causeB, "half a th", undefined),
  // A fresh reply: no draft, no typing.
  fresh: decide(null, causeB, undefined, undefined),
  // An ordinary decision has no cause: a reply to it keeps its text.
  ordinary: decide({ kind: "reply", text: "the fix is in" }, ""),
  ordinaryTyped: decide(null, "", "half a th", undefined),
};
console.log(JSON.stringify(out));
"""


class PanelAlarmTest(unittest.TestCase):
    def setUp(self):
        self.runner = BUN or NODE
        if not self.runner:
            self.skipTest("neither bun nor node is available")

    def run_probe(self):
        with tempfile.TemporaryDirectory() as scratch:
            rules = Path(scratch) / "answers.mjs"
            rules.write_text(RULES.read_text())
            probe = Path(scratch) / "probe.mjs"
            probe.write_text(PROBE % {"rules": rules})
            result = subprocess.run([self.runner, str(probe)], capture_output=True,
                                    text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_a_legacy_reply_for_a_replaced_alarm_is_not_sent(self):
        out = self.run_probe()
        legacy = out["legacy"]
        # The text is not restored, nothing is sent, and no cause is
        # carried, so the alarm that is on the board now is never
        # acknowledged.
        self.assertEqual(legacy["text"], "")
        self.assertFalse(legacy["sent"])
        self.assertEqual(legacy["cause"], "")
        self.assertEqual(legacy["acknowledged"], "")

    def test_a_reply_for_another_cause_is_not_sent(self):
        out = self.run_probe()
        bound = out["boundOther"]
        self.assertEqual(bound["text"], "the fix is in")
        self.assertTrue(bound["stale"])
        self.assertFalse(bound["sent"])
        self.assertEqual(bound["acknowledged"], "")

    def test_a_reply_for_the_alarm_on_the_board_is_sent(self):
        out = self.run_probe()
        bound = out["boundSame"]
        self.assertFalse(bound["stale"])
        self.assertTrue(bound["sent"])
        self.assertEqual(bound["acknowledged"], "gatekeep failing (last exit code 78)")

    def test_typing_text_keeps_its_cause_or_is_dropped(self):
        out = self.run_probe()
        kept = out["typedKept"]
        self.assertEqual(kept["text"], "half a th")
        self.assertEqual(kept["bound"], "gatekeep failing (last exit code 1)")
        # The cause it was typed for is not the one on the board, so the
        # answer is dropped rather than sent for the other alarm.
        self.assertTrue(kept["stale"])
        self.assertFalse(kept["sent"])
        lost = out["typedLost"]
        self.assertEqual(lost["text"], "")
        self.assertFalse(lost["sent"])
        self.assertEqual(lost["acknowledged"], "")

    def test_a_reply_to_an_ordinary_decision_keeps_its_text(self):
        out = self.run_probe()
        # An ordinary decision shows no cause, so a draft with text and
        # no cause is a valid draft and its text is restored.
        ordinary = out["ordinary"]
        self.assertEqual(ordinary["text"], "the fix is in")
        self.assertFalse(ordinary["stale"])
        self.assertTrue(ordinary["sent"])
        # It acknowledges nothing, because an ordinary decision is not
        # an alarm.
        self.assertEqual(ordinary["acknowledged"], "")
        typed = out["ordinaryTyped"]
        self.assertEqual(typed["text"], "half a th")
        self.assertFalse(typed["sent"] is None)

    def test_a_fresh_reply_binds_to_the_alarm_on_the_board(self):
        out = self.run_probe()
        fresh = out["fresh"]
        self.assertEqual(fresh["text"], "")
        self.assertEqual(fresh["bound"], "gatekeep failing (last exit code 78)")

    def test_the_command_acknowledges_one_key_and_no_other(self):
        from coordinator.overnight import alarms

        with tempfile.TemporaryDirectory() as scratch:
            mute = str(Path(scratch) / "mute-state.json")
            original = alarms.MUTE_PATH
            alarms.MUTE_PATH = mute
            try:
                state = alarms.load_state()
                alarms.raised(state, "factory-watchdog", "gatekeep failing (last exit code 1)")
                alarms.raised(state, "factory-watchdog", "gatekeep failing (last exit code 78)")
                alarms.save_state(state)
                # The command takes the id and the cause and quiets that
                # one key.
                self.assertEqual(alarms.main(["ack", "factory-watchdog",
                                               "gatekeep failing (last exit code 1)"]), 0)
                saved = alarms.load_state()
                first = alarms.key_of("factory-watchdog", "gatekeep failing (last exit code 1)")
                second = alarms.key_of("factory-watchdog", "gatekeep failing (last exit code 78)")
                self.assertIn("acked", saved[first])
                self.assertNotIn("acked", saved[second])
            finally:
                alarms.MUTE_PATH = original

    def test_the_panel_uses_the_rules(self):
        source = PANEL.read_text()
        self.assertIn('from "./answers.js"', source)
        self.assertIn("answerCause(draft, a.cause)", source)
        self.assertIn("isStale(draft, shown)", source)
        self.assertIn("restored(draft, typed, saved, shown)", source)


if __name__ == "__main__":
    unittest.main()
