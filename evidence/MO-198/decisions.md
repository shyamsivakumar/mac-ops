# MO-198 decisions

Run: `ticket:shyamsivakumar/mac-ops#158:a1`. Refs #158.

## What landed

- `coordinator/pi/extensions/coordinator.ts`: the coordinator extension now
  mirrors every coordinator turn to the phone relay. It captures the prompt
  that started the turn (`before_agent_start`), the reply the coordinator
  produced (`message_end`), and on `agent_settled` sends one message
  `Mirror: <prompt> | <reply>` to the `pi-coord-phone` terminal with `hc
  send`. The relay is looked up by name in `hc ls --json` and only a live
  one is written to, so no other terminal is ever a target.
- `coordinator/pi/phone-relay/CLAUDE.md`: one new rule. A message whose text
  starts with `Mirror:` is a mirror of a coordinator turn, not a request from
  Shyam: the relay replies with the text from `Mirror:` onward, verbatim, and
  makes no tool call.
- `tests/test_coordinator_mirror.py`: the mirror rules, run for real through
  bun when it is installed, plus the wiring checks.

No new process and no new file in the coordinator itself: the hook sits next
to the extension's other event handlers and the rule sits in the relay note
that already exists.

## Decisions

### 1. The mirror lives in the extension, not in a daemon

- **When**: revision 1.
- **The decision**: The `agent_settled` handler of the existing extension
  sends the mirror. No separate watcher, no queue file, no launchd job.
- **The gap**: The brief allowed a separate daemon and asked for a stop if
  one were the only way.
- **The reach**: The mirror stops when the coordinator session stops. That is
  the same lifetime the coordinator itself has.
- **Verdict**: sound. The daemon would have been a new process to keep alive
  and a new failure mode, for a job the extension can do in one call.
- **Confidence**: high.

### 2. The prompt comes from `before_agent_start`, the reply from `message_end`

- **When**: revision 1.
- **The decision**: `before_agent_start` gives the prompt that started the
  run (both typed input and `pi.sendUserMessage`, so `/tick` and the
  auto-wake tick are covered). `message_end` gives the assistant text of the
  run. The session entries are not read: they can lag the turn.
- **The gap**: The brief said "Shyam's prompt for that turn and the
  coordinator's final reply text" without naming the events.
- **The reach**: A future mirror that needs the full tool trace reads the
  session entries instead.
- **Verdict**: sound.
- **Confidence**: high.

### 3. A tick is labelled `tick`, and a NOOP tick is not mirrored

- **When**: revision 1.
- **The decision**: A prompt that starts with `Tick (` is mirrored as
  `Mirror: tick | <reply>`, so the phone does not get the whole tick
  prompt. A tick whose reply is exactly `NOOP` is not mirrored at all.
- **The gap**: The brief says "auto-wake ticks whose final reply is exactly
  `NOOP`" are not mirrored and that the mirror holds the prompt "or tick".
- **The reach**: A tick that finds work shows `tick` on the phone, and the
  reply carries what it found.
- **Verdict**: sound.
- **Confidence**: high.

### 4. A phone turn is not mirrored

- **When**: revision 1.
- **The decision**: A prompt that carries `From Shyam (phone):` is not
  mirrored. The relay already shows that turn and the reply to it.
- **The gap**: The brief says "turns whose prompt came from the phone ...
  already show there".
- **The reach**: The phone marker is what `coord-ask` writes, so the rule
  holds for every phone message and no other.
- **Verdict**: sound.
- **Confidence**: high.

### 5. A dead relay costs the mirror and nothing else

- **When**: revision 1.
- **The decision**: The mirror is fired and forgotten. `hc ls --json` finds
  the relay by name; if no live `pi-coord-phone` exists, the mirror is
  dropped for that turn with no retry. `hc` runs with a 15 second timeout
  and every failure is swallowed.
- **The gap**: The brief asks for "skipped silently ... no retry queue" and
  that the coordinator never hangs.
- **The reach**: A turn that ends while the relay is down loses that mirror.
  The next turn mirrors again.
- **Verdict**: sound.
- **Confidence**: high.

### 6. The mirror text is one line

- **When**: revision 1.
- **The decision**: The prompt and the reply are flattened to one line, and
  the mirror reads `Mirror: <prompt> | <reply>`.
- **The gap**: The brief names the two parts and the `Mirror:` prefix, not
  the format between them.
- **The reach**: A reply with lists loses its line breaks on the phone. The
  relay still shows the text verbatim.
- **Verdict**: sound. `hc send` pastes text and presses enter, so a newline
  in the payload would submit the message early.
- **Confidence**: medium.

### 7. The mirror only leaves an interactive session

- **When**: revision 1.
- **The decision**: The handler returns when `ctx.mode` is not `tui`. The
  headless launchd tick (`coord-tick`, `pi -p`) is not a turn Shyam is
  watching, and it already delivers its own alerts.
- **The gap**: The brief does not mention the headless tick.
- **The reach**: A headless run never mirrors. The interactive coordinator
  session is the one the phone follows.
- **Verdict**: sound.
- **Confidence**: medium.

## Proof

1. **Rules.** `python3 -m unittest tests.test_coordinator_mirror` runs the
   exported `mirrorText` under bun: a desktop turn mirrors as
   `Mirror: mirror test, reply OK | OK`, a phone turn mirrors as nothing, a
   `NOOP` tick mirrors as nothing, a tick with output mirrors as
   `Mirror: tick | ALERT: something`, and a turn without a reply mirrors as
   nothing.
2. **The send path, under the coordinator sandbox.**
   `/usr/bin/sandbox-exec -f ~/.pi/agent-coordinator/coordinator.sb bun run
   <probe>` listed the terminals, found `pi-coord-phone` as the only live
   relay (`t59`), and sent a mirror message to a scratch terminal, which
   wrote `Mirror: scratch probe` to its file. The sandbox does not block
   `hc`.
3. **The send path, against a stub `hc`.** `tests/test_coordinator_mirror.py`
   points `COORD_HC_BIN` at a stub: the mirror goes to the terminal named
   `pi-coord-phone`, a dead relay is skipped with no error and no send, and
   a terminal with any other name is never written to.
4. **The relay note.** `coordinator/pi/phone-relay/CLAUDE.md` answers a
   `Mirror:` message with its text and no tool call.

## Live proof in the coordinator tab

After `./install.sh coordinator` and `/reload` in the "Pi - Coordinator"
tab, with the relay live:

1. **A desktop turn is mirrored.** `hc send t56 "mirror test, reply OK"`
   produced `Mirror: mirror test, reply OK | OK` in `pi-coord-phone`, and
   the relay answered it with the same text and no tool call.
2. **A phone turn is not mirrored again.**
   `hc send t56 "From Shyam (phone): phone test, reply OK"` produced no new
   `Mirror:` line in `pi-coord-phone`.
3. **A tick is mirrored as a tick.** `/tick` that had work to do produced
   `Mirror: tick | ALERT: ...` in `pi-coord-phone`. The `NOOP` tick is
   covered by the unit test in point 1; the live tick in this tab had alerts
   to report, so it mirrored.
4. **A dead relay costs only the mirror.** The send path swallows every
   `hc` failure and the stub test in point 3 covers the dead relay and the
   wrong-terminal cases.

## Rollback

Revert the squash commit, rerun `./install.sh coordinator`, and `/reload` in
the coordinator tab.

## Known gap, out of scope here

The mirror carries the prompt and the reply as one line. A long coordinator
reply reaches the phone whole, but as one paragraph.
