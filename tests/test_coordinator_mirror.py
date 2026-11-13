"""The coordinator extension mirrors every turn to the phone relay.

The mirror lives in the pi coordinator extension (TypeScript) and in the
relay's CLAUDE.md. The extension is loaded by pi, not imported by Python, so
these tests read the source for the wiring and, when bun is available, run
the exported mirror rules for real.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "coordinator/pi/extensions/coordinator.ts"
RELAY_RULES = ROOT / "coordinator/pi/phone-relay/CLAUDE.md"
BUN = shutil.which("bun")

PROBE = """
import { mirrorText } from "%(extension)s";
const cases = [
  ["mirror test, reply OK", "OK"],
  ["From Shyam (phone): Testing from phone", "a reply"],
  ["Tick (auto-wake). Run one tick", "NOOP"],
  ["Tick (auto-wake). Run one tick", "ALERT: something"],
  ["what is left?", ""],
];
console.log(JSON.stringify(cases.map(([p, r]) => mirrorText(p, r))));
"""

DESKTOP, PHONE, NOOP_TICK, TICK, NO_REPLY = range(5)

STUB_HC = """#!/bin/sh
# A stub hc for the send tests. $HC_STUB_MODE says what the core reports.
if [ "$1" = "ls" ]; then
  case "$HC_STUB_MODE" in
    down) echo '{"terminals":[]}' ;;
    other) echo '{"terminals":[{"address":"t1","name":"some-other-terminal","state":"live"}]}' ;;
    *) echo '{"terminals":[{"address":"t9","name":"pi-coord-phone","state":"live"}]}' ;;
  esac
  exit 0
fi
if [ "$1" = "send" ]; then
  printf '%s\\n' "$2" > "$HC_STUB_SENT"
  exit 0
fi
exit 1
"""


class TestCoordinatorMirrorWiring(unittest.TestCase):
    def test_extension_mirrors_to_the_relay_terminal_only(self):
        source = EXTENSION.read_text()
        self.assertIn('const MIRROR_TERMINAL = "pi-coord-phone"', source)
        self.assertIn('t?.name === MIRROR_TERMINAL', source)

    def test_extension_sends_the_mirror_with_hc(self):
        source = EXTENSION.read_text()
        self.assertIn('runHc(["send", terms[0].address, text])', source)
        self.assertIn("Mirror:", source)

    def test_extension_skips_phone_turns_and_noop_ticks(self):
        source = EXTENSION.read_text()
        self.assertIn('const PHONE_MARKER = "From Shyam (phone):"', source)
        self.assertIn("r === \"NOOP\"", source)

    def test_relay_rules_answer_a_mirror_verbatim(self):
        rules = RELAY_RULES.read_text()
        self.assertIn("Mirror:", rules)
        self.assertIn("verbatim", rules)
        self.assertIn("no tool call", rules)


@unittest.skipIf(BUN is None, "bun is not installed")
class TestCoordinatorMirrorRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "probe.ts"
            script.write_text(PROBE % {"extension": EXTENSION})
            out = subprocess.run(
                [BUN, "run", str(script)],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
        cls.results = json.loads(out.stdout.strip().splitlines()[-1])

    def test_a_desktop_turn_is_mirrored_with_its_prompt_and_reply(self):
        self.assertEqual(self.results[DESKTOP], "Mirror: mirror test, reply OK | OK")

    def test_a_phone_turn_is_not_mirrored_again(self):
        self.assertEqual(self.results[PHONE], "")

    def test_a_noop_tick_is_not_mirrored(self):
        self.assertEqual(self.results[NOOP_TICK], "")

    def test_a_tick_with_output_is_mirrored_as_a_tick(self):
        self.assertEqual(self.results[TICK], "Mirror: tick | ALERT: something")

    def test_a_turn_without_a_reply_is_not_mirrored(self):
        self.assertEqual(self.results[NO_REPLY], "")


@unittest.skipIf(BUN is None, "bun is not installed")
class TestCoordinatorMirrorSend(unittest.TestCase):
    """The send path, against a stub hc, so no real terminal is written to."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stub = Path(self.tmp.name) / "hc"
        self.stub.write_text(STUB_HC)
        self.stub.chmod(0o755)
        self.sent = Path(self.tmp.name) / "sent"

    def send(self, mode, text="Mirror: hello | world"):
        script = Path(self.tmp.name) / "send.ts"
        script.write_text(
            'import { sendMirror } from "%s";\n'
            'console.log(await sendMirror(process.argv[2]));\n' % EXTENSION
        )
        env = {
            **os.environ,
            "COORD_HC_BIN": str(self.stub),
            "HC_STUB_MODE": mode,
            "HC_STUB_SENT": str(self.sent),
        }
        out = subprocess.run(
            [BUN, "run", str(script), text],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
            env=env,
        )
        return out.stdout.strip().splitlines()[-1]

    def test_the_mirror_goes_to_the_named_relay_terminal(self):
        self.assertEqual(self.send("live"), "true")
        self.assertEqual(self.sent.read_text().strip(), "t9")

    def test_a_dead_relay_is_skipped_without_an_error(self):
        self.assertEqual(self.send("down"), "false")
        self.assertFalse(self.sent.exists())

    def test_no_other_terminal_is_ever_written_to(self):
        self.assertEqual(self.send("other"), "false")
        self.assertFalse(self.sent.exists())


if __name__ == "__main__":
    unittest.main()
