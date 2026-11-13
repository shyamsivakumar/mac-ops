# MO-203 decisions

Run id: `ticket:shyamsivakumar/mac-ops#169:a1`. Refs #169.

## What landed

- `coordinator/pi/extensions/coordinator.ts`: the mirror now sends one
  message per assistant message instead of one per run.
  - `mirrorLabel` names the mirror: `phone` for a turn that carries
    `From Shyam (phone):`, `tick` for a tick, otherwise the user's own
    words.
  - `mirrorText` keeps the reply's line breaks, bullets and table rows. The
    label sits on its own first line, the reply follows under it.
  - The mirror is sent at `message_end`, for every assistant message that
    has text, through one promise queue (`enqueueMirror`, `flushMirrors`) so
    two sends never interleave.
  - The label comes from the newest user input seen on the `input` event, so
    a message Shyam types while a run is going labels the reply that answers
    it, not the prompt that started the run.
  - The NOOP-tick skip and the headless (`ctx.mode !== "tui"`) skip stay.
- `tests/test_coordinator_mirror.py`: the rules probe, plus a new event
  probe that drives the extension itself with a stub `hc` in place of the
  relay and reads back every send.

Not touched: the guard rules, the wake code, the relay note
(`coordinator/pi/phone-relay/CLAUDE.md`), the launcher scripts and the
installer. No existing test or check was weakened.

## Decisions

### 1. The mirror happens at `message_end`, not at `agent_settled`

- **When**: revision 1.
- **The decision**: Every assistant message that has text is mirrored when
  that message ends. The `agent_settled` handler no longer mirrors anything.
- **The gap**: The brief said "send each assistant message that has text as
  its own mirror at `message_end`".
- **The reach**: A reply that is cut off by an abort still reaches the phone
  as far as it was written, and a run with three text messages sends three
  mirrors.
- **Verdict**: sound. `agent_settled` fires once per run, which is the whole
  defect: two replies in one run could never both be mirrored.
- **Confidence**: high.

### 2. The label is the newest user input, not the prompt that started the run

- **When**: revision 1.
- **The decision**: `latestInput` is set on the `input` event and on
  `before_agent_start` (the run's own prompt). The label of a mirror is
  `latestInput` when there is one, and the run prompt otherwise.
- **The gap**: The brief said "labelled with the latest user input seen via
  the `input` event".
- **The reach**: A message Shyam types while a run is going (`stream` or
  `followUp`) becomes the label of the reply that answers it. The label of a
  reply that was already being written when the input arrived is that input
  too, because the label is read at `message_end`.
- **Verdict**: sound, and it is the only event that sees a mid-run input.
  `before_agent_start` fires once per run, so it cannot name a steer.
- **Confidence**: high.

### 3. A phone turn is mirrored, labelled `phone`

- **When**: revision 1.
- **The decision**: `mirrorLabel` returns `phone` for an input that carries
  `From Shyam (phone):`, and the reply is mirrored.
- **The gap**: MO-198 skipped a phone turn, on the assumption that the relay
  already shows the reply. It does not: the relay forwards Shyam's message
  and never sees the coordinator's answer.
- **The reach**: The phone shows the label `phone` and the reply under it.
  The relay answers a `Mirror:` message verbatim, so the label travels with
  the text. Changing that is a relay change and out of scope here.
- **Verdict**: sound. The old rule is the reason "Okay so what's left" got
  no answer.
- **Confidence**: high.

### 4. One queue for every send

- **When**: revision 1.
- **The decision**: `enqueueMirror` chains each send on the previous
  promise. The handler never awaits the send, so a turn never waits on the
  relay.
- **The gap**: The brief asked for "one promise queue so sends never
  interleave".
- **The reach**: Two mirrors can never be half-written at once in the relay.
  A dead relay still costs only the mirror: `hc` has a 15 second timeout and
  `sendMirror` swallows every failure, and the queue moves on.
- **Verdict**: sound.
- **Confidence**: high.

### 5. The reply keeps its line breaks; the label sits on its own first line

- **When**: revision 2, after the scope add (Shyam by phone, 2026-11-12:
  "Also the formatting is really bad. Just a huge paragraph of text").
- **The decision**: `mirrorText` no longer flattens the reply. It drops the
  trailing blank lines and keeps every line break, bullet and table row. The
  mirror reads `Mirror: <label>` on the first line and the reply under it.
  The label itself is still flattened to one line, because a label is a
  name.
- **The gap**: MO-198 flattened the whole mirror to one line, because
  `hc send` pastes text and presses Enter, and a newline in the payload
  could submit the message early.
- **The reach**: The phone reads a reply the way the coordinator wrote it.
  A reply with a code block keeps its indentation.
- **Verdict**: sound, and proven against the live relay (proof 3 below).
- **Confidence**: high.

### 6. `hc send` delivers a multi-line mirror as one message

- **When**: revision 2.
- **The decision**: No paste mode or extra option is needed. `hc send`
  writes the whole text to the terminal in one write and then sends the
  Enter separately, so the relay's input takes the whole block as one
  message.
- **The gap**: The scope asked for this to be checked, and for the paste
  mode to be used if the plain send could not do it.
- **The reach**: Any TUI that reads a burst of text as one paste (Claude
  Code, pi) takes the block whole. A program that reads one line at a time
  would see one line per call, which is the normal behaviour of a terminal.
- **Verdict**: sound, and measured (proof 2 and 3 below).
- **Confidence**: high.

### 7. The `agent_settled` handler keeps only the activity touch

- **When**: revision 1.
- **The decision**: `agent_settled` still updates the idle timer and the
  session context, and no longer mirrors.
- **The gap**: The old handler also cleared `turnPrompt` and skipped
  aborted runs.
- **The reach**: Nothing else in the file reads `turnPrompt`.
- **Verdict**: sound.
- **Confidence**: high.

## Proof

1. **Rules.** `python3 -m unittest tests.test_coordinator_mirror` runs the
   exported `mirrorText` under bun: a desktop turn mirrors as
   `Mirror: mirror test, reply OK` plus `OK` on the next line, a phone turn
   as `Mirror: phone` plus its reply, a `NOOP` tick as nothing, a tick with
   output as `Mirror: tick` plus the alert, a turn without a reply as
   nothing, and a reply with a bullet and a table row keeps both.
2. **The send path, with a stub hc.** The new event probe loads the
   extension, hands it the events of a run and reads the sends back from a
   stub `hc`: two text messages and a mid-run input give two sends in order
   (`Mirror: first question` / `answer one`, then `Mirror: and lane 4 as
   well` / `answer two`), a phone turn gives `Mirror: phone` / `phone
   answer`, a `NOOP` tick gives nothing, and a headless run gives nothing.
3. **Multi-line text is one message.** A scratch terminal running a raw
   stdin reader got the whole block in one read
   (`b'Mirror: phone\nline one\n- bullet one\n- bullet two\n| a | b |\nlast
   line'`) and the Enter as a separate `\r`. The live relay `t59`
   (`pi-coord-phone`) got the same treatment: `hc read t59` shows one user
   message with four lines and one reply, so no line was submitted early.
4. **Checks.** `python3 scripts/mac_ops_fast_check.py` → passed, and the
   same command through `heavy` → passed.

## After the merge

```sh
cd <mac-ops checkout on merged main> && python3 install_coordinator.py
shasum -a 256 ~/.pi/agent-coordinator/extensions/coordinator.ts
```

Then the coordinator asks Shyam for `/reload` in the "Pi - Coordinator" tab.

## Rollback

Revert the merge commit, run `python3 install_coordinator.py` again and
`/reload` in the coordinator tab.

## Known gap, out of scope here

The relay answers a `Mirror:` message with the text from `Mirror:` onward,
verbatim, so the phone shows the label line as well. A relay that answered
with the body only would need a change in
`coordinator/pi/phone-relay/CLAUDE.md`, which this ticket does not cover.
