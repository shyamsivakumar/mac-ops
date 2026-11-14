# MO-211 decisions

Overnight runner spec part T4, as revision 3 changed it: the shift runs
24x7 and is never unarmed. What is left of the arm step is the policy
snapshot the shift reads on every cycle.

Run id: `ticket:shyamsivakumar/mac-ops#179:a1`. Refs #179.

## What this ticket does and does not claim

The spec's T4 was "arm, deadline and policy snapshot", and the acceptance
was "arm twice; the second arm refuses". Revision 3 (Shyam, 2026-11-13:
"don't use the tick then. just run the shift 24x7") removes the night
window, the deadline and the arm: the shift is always armed, it has no
deadline, and `run/STOP` still stops it at the next cycle. There is no arm
left to refuse a second time, so this ticket builds the part of T4 that
revision 3 keeps: `overnight policy` writes `run/policy.json`, and the
shift reads that snapshot on every cycle.

The board work itself (the shift picking items and running builders) is
part T5 and is out of scope here, so a real cycle still refuses and says
so. The schedule and the retirement of the pi tick are out of scope too
(MO-240), so the launchd job still fires at the hours it fired at, and
the shift still does nothing outside the two windows it has today.

## What landed

- `coordinator/overnight/overnight`: a new `policy` subcommand in the same
  module as `intake`, `filter`, `order`, `report`, `shift` and `attend`.
  - It writes `run/policy.json` in the folder the shift keeps its records
    in (the runtime folder, or `--root` for a rehearsal).
  - The snapshot holds the allow list (the board config's repositories),
    the queue's slot cap (read only, from the coordq config, never
    raised), the stall cap, the retry cap and the verify level.
  - It has no item cap and no allowance stop. The whole backlog is in
    scope and model use is never a stop condition.
  - It writes no `run/armed` and no `run/deadline`, and it never writes
    the queue's config. Writing it again replaces it with the same
    contract, so it can run on every boot. The write is atomic, so a
    cycle that reads during a rewrite reads the old snapshot or the new
    one, never half of one.
  - It refuses to write a snapshot at all when the queue's slot cap
    cannot be read: a contract without the cap is not a contract.
- `coordinator/overnight/overnight`: the shift reads the snapshot on every
  cycle.
  - The cycle works under the snapshot's allow list, so the board is read
    under the contract and not under a second list of its own.
  - The Ascend rule still wins over the snapshot. The cycle reads the
    repositories the snapshot names, minus the ones the merge gate would
    refuse, so a hand-edited snapshot cannot make the shift read Ascend
    work.
  - A cycle that would work the board and finds no snapshot refuses and
    says so. A snapshot that is missing one of the five contract fields,
    or that holds the wrong kind of value, is not a contract, and the
    cycle refuses it too. A dry run reads the board without one and says
    that it did.
  - `run/STOP` stops the next working cycle. The morning report still
    runs: it is the record of the night, and it says that the night ended
    with STOP.
  - The working cycle never reads `run/armed` and never reads
    `run/deadline`. There is no arm to wait for and no clock to end on.
    The morning report still reads both, for the window of the attended
    rehearsal, and writes the window as UNVERIFIED when there is none.
- `coordinator/overnight/overnight`: the attended first night (T13,
  `#192`) writes its policy snapshot through the same writer, so there is
  one shape of snapshot in the module. It keeps its own `run/armed` and
  `run/deadline` because it is a rehearsal with a human in it and its
  report reads its window; the shift itself has neither.
- `coordinator/overnight/README.md`: the contract names the new command,
  the fields of the snapshot, what the shift reads on every cycle, and
  that there is no item cap and no allowance stop.
- `evidence/MO-211/`: the proof runs. `policy-run-1.log` and
  `policy-run-2.log` (the command run twice, against the live runtime
  folder), `policy.json` (the snapshot it wrote), `shift-cycle.log` (a
  cycle that read it) and `policy-proof.log` (the refusals and the STOP).

Not touched: the merge, push and slot-cap rules, the Ascend rules, the
coordq queue, the launchd job and its hours, the pi tick, and every
existing test or check. No existing test or check was weakened, and no new
test file was added: the ticket says to prove by running the real command.

## Decisions

### 1. The snapshot has no item cap and no allowance stop, and it says so

- **The decision**: the snapshot holds the allow list, the slot cap, the
  stall cap, the retry cap and the verify level. It holds no item cap and
  no allowance field at all, and the command prints "No item cap and no
  allowance stop: the whole backlog is in scope and model use is never a
  stop condition".
- **The gap**: revision 2's snapshot had a budget percent and an
  allowance stop. Revision 3 keeps the whole backlog in scope, so a cap
  field that says `null` would look like a cap of zero and a stop that
  never fires would look like a rule. A reader that looks for a cap on
  the items or on the model must find none.
- **The reach**: the shape of the snapshot is one function
  (`build_policy`) and one writer (`write_policy`), so the attended night
  cannot write a second shape by accident.
- **Verdict**: sound. The proof run shows the snapshot with exactly the
  five contract fields and a timestamp, and no cap on items and no
  allowance stop anywhere in it.

### 2. The slot cap is read from the coordq config and never written

- **The decision**: the snapshot's `slot_cap` is read from the file
  coordq reads its cap from (`$COORDQ_DIR/config.json`, which is
  `~/Code/coordinator/queue/config.json` by default), and the module
  never writes that file. The command refuses to write a snapshot when
  the cap cannot be read.
- **The gap**: the module used to build that path by hand, so a coordq
  run with `COORDQ_DIR` pointed somewhere else would have had the shift
  read a cap the queue is not using. Reading the same path coordq reads
  keeps the shift and the queue on one number. A snapshot written without
  the cap would be a contract with a hole in it.
- **The reach**: the proof run read `6`, the value in the live
  `~/Code/coordinator/queue/config.json`, and the diff holds no write to
  that file. The proof log shows the command refusing (exit 1) when the
  cap cannot be read.
- **Verdict**: sound. The cap is read only, and a contract without it is
  never written and never read.

### 3. A cycle without a contract does no work

- **The decision**: a cycle that would work the board and finds no
  snapshot refuses and exits non-zero with the path it looked for. A
  snapshot that is missing one of the five contract fields, or that holds
  the wrong kind of value, is refused the same way. A dry run reads the
  board without a contract and says on stderr that it did.
- **The gap**: revision 3 leaves the snapshot as the shift's only
  contract. A cycle that quietly worked the board under no contract, or
  under half a contract, would be a shift that works under rules nobody
  wrote down, and the dry run that the launchd job still fires must keep
  working before the shift does any work at all.
- **The reach**: `evidence/MO-211/policy-proof.log` shows the refusal
  (the line and `exit=1`), the dry run's warning, and the refusal of a
  snapshot with a field removed.
- **Verdict**: sound. The failure is loud and names the command that
  fixes it.

### 4. STOP stops the work, and the report still runs

- **The decision**: `run/STOP` ends the next working cycle. The morning
  report still runs with the STOP file in place.
- **The gap**: the report's own rule (T11) is that "STOP needs the STOP
  file" before it says the night ended with STOP. A STOP that also
  blocked the report would delete the record of the night it stopped.
- **The reach**: the proof log shows the working cycle stopping on STOP
  and the report still writing its file.
- **Verdict**: sound.

### 5. The Ascend rule is applied where the snapshot is read

- **The decision**: the cycle reads the repositories the snapshot names,
  minus the ones the merge gate would refuse (the module's own Ascend
  rule, the same one the filter and `check-pr` use). The cycle says how
  many it dropped.
- **The gap**: a snapshot is a file on disk. A hand-edited snapshot that
  named an Ascend repository would have made the cycle read that
  repository's pull requests, and T5 will build its work on this path.
- **The reach**: the proof run shows "The snapshot names 1 Ascend
  repository, and the shift never reads Ascend work", and the cycle then
  reads 14 repositories instead of 15. The snapshot still holds the
  board config's own list; the Ascend rule is a rule about what the
  shift touches, and it lives in one place.
- **Verdict**: sound. The Ascend rule itself is unchanged; this is where
  it is applied.

### 6. The schedule stays as it is

- **The decision**: the launchd job still fires at 22:30 and 06:30, and
  the shift still picks its part from the local clock. The README and
  the module's docstring say that the 24x7 rule is revision 3's rule and
  that the hours change with the schedule work (MO-240).
- **The gap**: revision 3 says the shift runs 24x7 on a fixed interval,
  but the ticket puts the schedule out of scope (MO-240 and the
  retirement of the pi tick). Changing the hours here would change the
  launchd job that T12 owns. A reader must not come away thinking the
  shift already runs around the clock.
- **The reach**: the diff holds no change to the plist and no change to
  the windows, and both the README and the docstring name the limit.
- **Verdict**: sound, and the limit is named here rather than hidden.

## Proof

```
$ python3 coordinator/overnight/overnight policy
overnight: wrote /Users/shyamsivakumar/Code/coordinator/.overnight/run/policy.json
Allow list: 15 repositories (digitized/Concerning, shyamsivakumar/CineJar, ...)
Slot cap: 6 (read only, from the coordq config; never raised)
Stall cap: 3 cycles with no new work
Retry cap: 2 fix tries per item, then it is parked
Verify level: balanced
No item cap and no allowance stop: the whole backlog is in scope and model use is never a stop condition.
The shift reads this snapshot on every cycle. It is never unarmed, it has no deadline, and run/STOP still stops it at the next cycle.
```

The command was run twice against the live runtime folder
(`evidence/MO-211/policy-run-1.log` and `evidence/MO-211/policy-run-2.log`)
and wrote the same contract both times; the snapshot is
`evidence/MO-211/policy.json`:

```json
{
  "allow": [
    "digitized/Concerning",
    "shyamsivakumar/CineJar",
    "shyamsivakumar/cairn",
    "shyamsivakumar/catalouge",
    "shyamsivakumar/fantasy-football-toolkit",
    "shyamsivakumar/mac-ops",
    "shyamsivakumar/openscan",
    "shyamsivakumar/qabot",
    "shyamsivakumar/recoup",
    "shyamsivakumar/sams-llm-wiki",
    "shyamsivakumar/scrapers",
    "shyamsivakumar/scripture-scroll",
    "shyamsivakumar/strata",
    "shyamsivakumar/strategy-replay-workbench",
    "shyamsivakumar/tunerise"
  ],
  "slot_cap": 6,
  "stall_cap": 3,
  "retry_cap": 2,
  "verify_level": "balanced",
  "written_at": "2026-11-13 23:32 PST"
}
```

A shift cycle against the same live folder read the snapshot and worked
under its allow list (`evidence/MO-211/shift-cycle.log`):

```
$ python3 coordinator/overnight/overnight shift --at start --dry-run
overnight: 2026-11-13 23:32 PST shift cycle under /Users/shyamsivakumar/Code/coordinator/.overnight/run/policy.json
Allow list: 15 repositories (...)
Slot cap: 6 (read only, from the coordq config; never raised)
...
The snapshot names 1 Ascend repository, and the shift never reads Ascend work.
overnight: 2026-11-13 23:32 PST shift start (dry run, read only)
Overnight intake - dry run (read only)
Board: 110 tickets
Allowed repositories: 14
```

The refusals and the STOP are in `evidence/MO-211/policy-proof.log`, which
holds every line of every command, stderr included:

```
== 1. a fresh folder, no snapshot: a real cycle refuses ==
overnight: the shift has no usable policy snapshot: .../run/policy.json does not exist. Run `overnight policy` to write it.
exit=1
...
== 4. a snapshot with a field removed is not a contract ==
overnight: .../run/policy.json is not a contract: its slot cap is not a number; a dry run reads the board only
...
== 5. the snapshot is written again, and the cap cannot be read ==
overnight: wrote .../run/policy.json
overnight: the queue's slot cap cannot be read from .../no-queue/config.json, so the shift's contract cannot be written without it
exit=1
...
== 6. run/STOP stops the next working cycle ==
overnight: 2026-11-13 23:32 PST run/STOP exists, so the shift stops at this cycle
exit=0
...
== 7. the report still runs with STOP in place ==
overnight: wrote .../receipts/morning-2026-11-13.md
exit=0
```

No secret was read or written: the snapshot holds repository names, the
queue's cap and three numbers, and the proof files hold nothing else.

## Checks

```
$ python3 scripts/mac_ops_fast_check.py
fast-check: passed; selected checks are not the full suite

$ ~/.local/bin/heavy python3 -m unittest discover -s tests -t .
Ran 190 tests in 2.916s

OK
```

## The reviewer round

One in-session reviewer round (Opus, `claude-opus-5-5`) read
`git diff origin/main...HEAD` and returned `VERDICT: FAIL`: one major
finding and eight smaller ones. Nine findings, nine fixes, and no code
change that the reviewer did not ask for.

1. **Major: the proof log did not hold the line the decisions quoted.**
   The log was written without stderr, so it held only `exit=1` under
   the refusal heading, while the decisions quoted the refusal line
   itself. Every `die()` exits 1, so the file did not prove which
   refusal fired. **Fixed**: the log is captured again with stderr and
   with no truncated sections, and the decisions quote only lines the
   file holds.
2. **Minor: the README and the docstring read as if the shift already
   runs 24x7**, while the code still has the two windows. **Fixed**:
   both say that the 24x7 rule is revision 3's rule and that the hours
   change with the schedule work (MO-240), and decision 6 says the same.
3. **Minor: "the shift never reads `run/armed` and `run/deadline`" was
   true of the working cycle only**; the morning report reads both for
   the window. **Fixed**: the sentence names the working cycle, and the
   README's report table says the window is UNVERIFIED when there is
   none.
4. **Minor (safety): the cycle trusted the snapshot's allow list as
   written**, so a hand-edited snapshot could make it read Ascend work.
   **Fixed**: the Ascend rule is applied where the snapshot is read
   (decision 5), and the cycle says how many repositories it dropped.
5. **Minor: a snapshot missing one of its five fields was accepted.**
   **Fixed**: the contract is checked field by field, and the command
   refuses to write a snapshot when the slot cap cannot be read
   (decisions 2 and 3).
6. **Minor (name shadowing): the new `COORDQ_DIR` constant was
   redefined later in the module as a string.** **Fixed**: the new
   constant is `COORDQ_QUEUE_DIR` and the older name is left alone.
7. **Nit: the report part loaded the snapshot and never used it.**
   **Fixed**: the snapshot is loaded in the working cycle, which is the
   part that uses it.
8. **Nit: the stall cap and the retry cap were never checked when the
   snapshot was read.** **Fixed**: the contract check covers both.
9. **Nit: the snapshot was not written atomically.** **Fixed**: the
   write goes to a temporary file and is renamed into place.

The reviewer's points with no finding: the scope is what the ticket asks
and nothing more; no merge, push, slot cap or Ascend rule changed; the
intake, filter, order, report and attend commands behave as before; the
attended night writes through `build_policy` and keeps the report's
UNVERIFIED rule for model use; nothing writes the coordq config, merges,
pushes, answers a dialog or reads a secret; and the acceptance proof
agrees with what the commands print.
