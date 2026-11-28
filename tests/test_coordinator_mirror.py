"""The coordinator extension mirrors every reply to the phone relay.

The mirror lives in the pi coordinator extension (TypeScript) and in the
relay's CLAUDE.md. The extension is loaded by pi, not imported by Python, so
these tests read the source for the wiring and, when bun is available, run
the exported mirror rules for real.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
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
const paste = Array.from({length: 100}, (_, i) => `line ${i} of the pasted alert block`).join("\\n");
const cases = [
  ["mirror test, reply OK", "OK", undefined],
  ["From Shyam (phone): Testing from phone", "a reply", undefined],
  ["Tick (auto-wake). Run one tick", "NOOP", undefined],
  ["Tick (auto-wake). Run one tick", "ALERT: something", undefined],
  ["what is left?", "", undefined],
  ["what is left?", "line one\\n- bullet\\n| a | b |", undefined],
  ["short typed message", "reply to it", undefined],
  [paste, "reply to the paste", undefined],
  ["", "reply to an event run", "GitHub bot note"],
  ["", "reply to a run with no custom message", undefined],
];
console.log(JSON.stringify(cases.map(([p, r, c]) => mirrorText(p, r, c))));
"""

# The event probe drives the extension itself: the mirror handlers are
# registered on a fake pi, the events of a run are delivered by hand, and a
# stub hc records what the extension sends to the relay.
EVENT_PROBE = """
const EXT = process.env.PROBE_EXT!;
const { default: extension, flushMirrors } = await import(EXT);

const handlers: Record<string, Function[]> = {};
const pi: any = {
  on(name: string, handler: Function) {
    (handlers[name] ||= []).push(handler);
  },
  registerCommand() {},
  sendUserMessage() {},
};
extension(pi);

const tui: any = { mode: "tui", isIdle: () => true, hasPendingMessages: () => false, ui: { notify() {} } };
const headless: any = { mode: "print" };

async function emit(name: string, event: any, ctx: any) {
  for (const handler of handlers[name] || []) await handler(event, ctx);
}
function assistant(text: string) {
  return { message: { role: "assistant", content: [{ type: "text", text }] } };
}

// One run with two text messages and an input that joins the run.
await emit("input", { text: "first question", source: "interactive" }, tui);
await emit("before_agent_start", { messageType: "user", prompt: "first question" }, tui);
await emit("message_end", assistant("answer one"), tui);
await emit("input", { text: "and lane 4 as well", source: "interactive" }, tui);
await emit("message_end", assistant("answer two"), tui);
await emit("agent_settled", {}, tui);

// A phone turn is mirrored too, labelled phone, with Shyam's own words.
await emit("input", { text: "From Shyam (phone): Okay so what's left", source: "interactive" }, tui);
await emit("before_agent_start", { messageType: "user", prompt: "From Shyam (phone): Okay so what's left" }, tui);
await emit("message_end", assistant("phone answer"), tui);
await emit("agent_settled", {}, tui);

// A run with no prompt of its own is mirrored too, labelled event.
await emit("before_agent_start", { messageType: "custom", message: { content: [{ type: "text", text: "GitHub bot note" }] } }, tui);
await emit("message_end", assistant("event answer"), tui);
await emit("agent_settled", {}, tui);

// A NOOP tick says nothing on the phone.
await emit("input", { text: "Tick (auto-wake). Run one tick", source: "extension" }, tui);
await emit("before_agent_start", { messageType: "user", prompt: "Tick (auto-wake). Run one tick" }, tui);
await emit("message_end", assistant("NOOP"), tui);
await emit("agent_settled", {}, tui);

// A headless run never mirrors.
await emit("input", { text: "headless question", source: "interactive" }, headless);
await emit("before_agent_start", { messageType: "user", prompt: "headless question" }, headless);
await emit("message_end", assistant("headless answer"), headless);

// A relay that is down costs that mirror and nothing else.
await emit("input", { text: "relay down", source: "interactive" }, tui);
await emit("before_agent_start", { messageType: "user", prompt: "relay down" }, tui);
await emit("message_end", assistant("relay down please"), tui);
await emit("input", { text: "after the relay failed", source: "interactive" }, tui);
await emit("message_end", assistant("still mirrored"), tui);

await flushMirrors();
console.log("SENDS " + JSON.stringify(fs.readFileSync(process.env.PROBE_LOG!, "utf8")));
"""

# The stub records every send with a start and an end marker, so the test
# can see two sends overlapping, and it fails the send that asks for a dead
# relay, so the test can see the queue move on.
MIRROR_STUB_HC = """#!/bin/sh
case "$1" in
  ls)
    printf '%s\\n' '{"terminals":[{"name":"pi-coord-phone","state":"live","address":"t59"}]}'
    ;;
  send)
    printf '<<<START>>>\\n' >> "$PROBE_LOG"
    sleep 0.2
    case "$3" in
      *"relay down"*)
        printf '%s\\n<<<FAIL>>>\\n' "$3" >> "$PROBE_LOG"
        exit 3
        ;;
    esac
    printf '%s\\n<<<END>>>\\n' "$3" >> "$PROBE_LOG"
    ;;
esac
exit 0
"""

DESKTOP, PHONE, NOOP_TICK, TICK, NO_REPLY, MULTILINE, SHORT, BIG_PASTE, EVENT_CUSTOM, EVENT_PLAIN = range(10)

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

    def test_extension_labels_a_phone_turn_and_skips_a_noop_tick(self):
        source = EXTENSION.read_text()
        self.assertIn('const PHONE_MARKER = "From Shyam (phone):"', source)
        self.assertIn('=== "NOOP"', source)

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
        self.assertEqual(
            self.results[DESKTOP],
            "Mirror: you\n> mirror test, reply OK\n\nOK",
        )

    def test_a_phone_turn_is_mirrored_as_phone(self):
        self.assertEqual(
            self.results[PHONE],
            "Mirror: phone\n> Testing from phone\n\na reply",
        )

    def test_a_noop_tick_is_not_mirrored(self):
        self.assertEqual(self.results[NOOP_TICK], "")

    def test_a_tick_with_output_is_mirrored_as_a_tick(self):
        self.assertEqual(self.results[TICK], "Mirror: tick\n\nALERT: something")

    def test_a_turn_without_a_reply_is_not_mirrored(self):
        self.assertEqual(self.results[NO_REPLY], "")

    def test_the_reply_keeps_its_line_breaks_and_bullets(self):
        self.assertEqual(
            self.results[MULTILINE],
            "Mirror: you\n> what is left?\n\nline one\n- bullet\n| a | b |",
        )

    def test_a_short_typed_message_is_quoted_above_the_reply(self):
        self.assertEqual(
            self.results[SHORT],
            "Mirror: you\n> short typed message\n\nreply to it",
        )

    def test_a_long_paste_is_quoted_in_lines_and_cut_at_600_characters(self):
        paste = "\n".join(f"line {i} of the pasted alert block" for i in range(100))
        quoted = "\n".join("> " + line for line in paste[:599].split("\n")) + "…"
        self.assertEqual(
            self.results[BIG_PASTE],
            f"Mirror: you\n{quoted}\n\nreply to the paste",
        )
        self.assertGreater(len(paste), 3000)

    def test_a_run_with_no_prompt_is_mirrored_as_an_event(self):
        self.assertEqual(
            self.results[EVENT_CUSTOM],
            "Mirror: event\n> GitHub bot note\n\nreply to an event run",
        )

    def test_an_event_with_no_custom_message_has_no_quote(self):
        self.assertEqual(
            self.results[EVENT_PLAIN],
            "Mirror: event\n\nreply to a run with no custom message",
        )


@unittest.skipIf(BUN is None, "bun is not installed")
class TestCoordinatorMirrorEvents(unittest.TestCase):
    """The extension's own events, with a stub hc in place of the relay."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        cls.log = tmp / "sends.log"
        stub = tmp / "hc"
        stub.write_text(MIRROR_STUB_HC)
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        script = tmp / "events.ts"
        script.write_text("import fs from \"node:fs\";\n" + EVENT_PROBE)
        env = {
            **os.environ,
            "PROBE_EXT": str(EXTENSION),
            "PROBE_LOG": str(cls.log),
            "COORD_HC_BIN": str(stub),
        }
        out = subprocess.run(
            [BUN, "run", str(script)],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
            env=env,
        )
        line = [l for l in out.stdout.splitlines() if l.startswith("SENDS ")][-1]
        raw = json.loads(line[len("SENDS "):])
        records = []
        for chunk in raw.split("<<<START>>>\n")[1:]:
            if chunk.endswith("\n<<<END>>>\n"):
                records.append(("ok", chunk[: -len("\n<<<END>>>\n")]))
            elif chunk.endswith("\n<<<FAIL>>>\n"):
                records.append(("fail", chunk[: -len("\n<<<FAIL>>>\n")]))
            else:
                # A send that is still open when the next one starts: two
                # sends overlapped.
                records.append(("open", chunk))
        cls.records = records
        cls.sends = [text for status, text in records if status == "ok"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_text_message_is_mirrored_in_order(self):
        self.assertEqual(
            self.sends,
            [
                "Mirror: you\n> first question\n\nanswer one",
                "Mirror: you\n> and lane 4 as well\n\nanswer two",
                "Mirror: phone\n> Okay so what's left\n\nphone answer",
                "Mirror: event\n> GitHub bot note\n\nevent answer",
                "Mirror: you\n> after the relay failed\n\nstill mirrored",
            ],
        )

    def test_a_phone_turn_is_mirrored_with_the_phone_label(self):
        self.assertIn("Mirror: phone\n> Okay so what's left\n\nphone answer", self.sends)

    def test_a_run_with_no_prompt_is_mirrored_as_an_event(self):
        self.assertIn("Mirror: event\n> GitHub bot note\n\nevent answer", self.sends)

    def test_a_noop_tick_and_a_headless_run_are_not_mirrored(self):
        self.assertNotIn("NOOP", "\n".join(self.sends))
        self.assertNotIn("headless", "\n".join(self.sends))

    def test_two_sends_never_overlap(self):
        self.assertNotIn("open", [status for status, _ in self.records])

    def test_a_dead_relay_costs_that_mirror_and_nothing_else(self):
        self.assertEqual(
            [status for status, _ in self.records],
            ["ok", "ok", "ok", "ok", "fail", "ok"],
        )


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


class CoordPiLauncherTest(unittest.TestCase):
    def test_coord_pi_exports_claude_max_default_and_honors_override(self):
        launcher = ROOT / "coordinator/pi/bin/coord-pi"
        text = launcher.read_text()
        export_line = 'export PI_CLAUDE_CLI_COMMAND="${PI_CLAUDE_CLI_COMMAND:-$HOME/.local/bin/claude-max}"'
        self.assertIn(export_line, text)
        probe = export_line + '; printf %s "$PI_CLAUDE_CLI_COMMAND"'
        env = {k: v for k, v in os.environ.items() if k != "PI_CLAUDE_CLI_COMMAND"}
        default_out = subprocess.run(
            ["/bin/zsh", "-c", probe],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        self.assertEqual(default_out.stdout, os.path.expanduser("~/.local/bin/claude-max"))
        override_out = subprocess.run(
            ["/bin/zsh", "-c", probe],
            capture_output=True,
            text=True,
            check=True,
            env={**env, "PI_CLAUDE_CLI_COMMAND": "/custom/claude"},
        )
        self.assertEqual(override_out.stdout, "/custom/claude")


if __name__ == "__main__":
    unittest.main()
