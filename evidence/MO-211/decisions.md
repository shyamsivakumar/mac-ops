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
(MO-240), so the launchd job still fires at the hours it fired at.

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
    contract, so it can run on every boot.
- `coordinator/overnight/overnight`: the shift reads the snapshot on every
  cycle.
  - The cycle works under the snapshot's allow list, so the board is read
    under the contract and not under a second list of its own.
  - A cycle that would work the board and finds no snapshot refuses and
    says so. A dry run reads the board without one and says that it did.
  - `run/STOP` stops the next working cycle. The morning report still
    runs: it is the record of the night, and it says that the night ended
    with STOP.
  - The shift never reads `run/armed` and never reads `run/deadline`.
    There is no arm to wait for and no clock to end on.
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
  cycle that read it) and `policy-proof.log` (a cycle with no snapshot, a
  dry cycle without one, and `run/STOP`).

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
  never writes that file.
- **The gap**: the module used to build that path by hand, so a coordq
  run with `COORDQ_DIR` pointed somewhere else would have had the shift
  read a cap the queue is not using. Reading the same path coordq reads
  keeps the shift and the queue on one number.
- **The reach**: the proof run read `6`, the value in the live
  `~/Code/coordinator/queue/config.json`, and the diff holds no write to
  that file.
- **Verdict**: sound. The cap is read only, and it is `null` with a
  printed "unknown" when the file cannot be read, so a missing cap is
  never a cap of zero.

### 3. A cycle without a contract does no work

- **The decision**: a cycle that would work the board and finds no
  snapshot refuses and exits non-zero with the path it looked for. A dry
  run reads the board without a snapshot and says on stderr that it did.
- **The gap**: revision 3 leaves the snapshot as the shift's only
  contract. A cycle that quietly worked the board under no contract would
  be a shift that works under rules nobody wrote down, and the dry run
  that the launchd job still fires must keep working before the shift
  does any work at all.
- **The reach**: `evidence/MO-211/policy-proof.log` shows the refusal
  (exit 1, the path it looked for), the dry run's warning, and the cycle
  that reads the snapshot.
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

### 5. The schedule stays as it is

- **The decision**: the launchd job still fires at 22:30 and 06:30, and
  the shift still picks its part from the local clock.
- **The gap**: revision 3 says the shift runs 24x7 on a fixed interval,
  but the ticket puts the schedule out of scope (MO-240 and the
  retirement of the pi tick). Changing the hours here would change the
  launchd job that T12 owns.
- **The reach**: the diff holds no change to the plist and no change to
  the windows.
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
  "written_at": "2026-11-13 17:14 PST"
}
```

A shift cycle against the same live folder read the snapshot and worked
under its allow list (`evidence/MO-211/shift-cycle.log`):

```
$ python3 coordinator/overnight/overnight shift --at start --dry-run
overnight: 2026-11-13 17:12 PST shift cycle under /Users/shyamsivakumar/Code/coordinator/.overnight/run/policy.json
Allow list: 15 repositories (...)
Slot cap: 6 (read only, from the coordq config; never raised)
...
Overnight intake - dry run (read only)
Board: 110 tickets
```

The refusals and the STOP are in `evidence/MO-211/policy-proof.log`:

```
== a fresh folder, no snapshot: a real cycle refuses ==
overnight: the shift has no policy snapshot: .../run/policy.json does not exist. Run `overnight policy` to write it.
exit=1
== run/STOP stops the next working cycle ==
overnight: 2026-11-13 17:14 PST run/STOP exists, so the shift stops at this cycle
exit=0
== the report still runs with STOP in place ==
overnight: 2026-11-13 17:14 PST morning report
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
Ran 190 tests in 3.042s

OK
```

## The reviewer round

One in-session reviewer round read `git diff origin/main...HEAD`. Its
verdict and any fixes are recorded here.
