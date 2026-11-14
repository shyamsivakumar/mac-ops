# MO-225 decisions

Overnight runner spec part T14: the first unattended night. The night works
the whole backlog, with no item cap, over the full window, and leaves one
morning report.

Run id: `ticket:shyamsivakumar/mac-ops#193:a1`. Refs #193.

## What this ticket does and does not claim

The command that runs the unattended night now exists and is proven against
the real board (`overnight night`, proof below). The real overnight window
(22:30 to 06:00 PT on the Mac, with nobody watching) has **not run yet**:
the launchd job runs it tonight once the installer has put the new job and
the new command on this Mac. The first real morning report is therefore
Shyam's to read in the morning, and this ticket does not claim it has been
read.

What the night does and does not do:

- It works the whole backlog: every ticket in an allowed repository, minus
  the Ascend work, the holds, the tickets that need Shyam and the tickets
  with an open question in the decisions log. There is no item cap, no
  allowance stop and no allowance read. The board is the list, so there is
  no second queue and no punch-list file.
- It runs no merge, no push and no builder. The queue and the tick do that
  work, under the rules that apply today, and the night records what they
  really did: each item's pull request, its checks, the gate's verdict and
  the merge time. This is the module's own division of labour (the tick
  part, T5, works the board; MO-239, mac-ops #251), and it is why the
  night needs no merge right, no push right and no slot-cap change.
- It refuses a cycle it cannot fully check. A stale board, ticket text it
  could not read or a decisions log it could not read stops the cycle and
  says so in the shift log, rather than reporting from half the truth.
- It reads the policy snapshot first. A night with no contract does no
  work.

## What landed

- `coordinator/overnight/overnight`: a new `night` subcommand in the same
  module as `intake`, `filter`, `order`, `board`, `report`, `shift`,
  `policy` and `attend`. Not a bolt-on: the module already holds the
  board read, the filter, the policy snapshot, the receipts and the report
  code, and the night uses those parts.
  - The window is the spec's: the night starts when it starts and closes
    at 06:00 PT, so a night that starts late still ends at 06:00 PT.
  - The cycle is the tick's cadence, 30 minutes. Each cycle reads the
    whole board again and writes a receipt only when the item's state
    changed.
  - The receipt holds the pull request, the check with its exit code, the
    gate's verdict, the merge time when it merged, and the builder time as
    `UNVERIFIED`, because the night does not know how long a builder ran.
    The night records its own looking time apart from the builder's.
  - `--minutes` and `--cycles` bound a run, so a rehearsal can run
    without the whole night. `--dry-run` reads the board and writes no
    record.
- `coordinator/overnight/overnight`: the shift command's start phase now
  runs the unattended night instead of refusing to start a real shift. The
  report phase is unchanged.
- `coordinator/overnight/overnight`: the report has one new state,
  `waiting`: an item whose builder holds it and has no pull request yet.
  It is not stuck, and it is not a decision for Shyam, so it is listed
  under "Still running" instead of "Decisions for you". Before this, the
  whole backlog without a pull request would have landed in the decisions
  list, which is what the first proof run showed.
- `coordinator/launchd/dev.coordinator.overnight.plist`: the job runs the
  shift for real (`shift`, not `shift --dry-run`). At 22:30 it starts the
  night; at 06:30 it writes the morning report from the same records.
- `coordinator/overnight/README.md`: the contract names the new command,
  the new state and the new job behaviour.
- `evidence/MO-225/night/`: the proof run's records: `run/policy.json`,
  `run/armed`, `run/deadline`, `run/shift-log.md`, 75 receipts and the
  morning report `receipts/morning-2026-11-13.md`.

Not touched: the merge, push, slot-cap and Ascend rules. The night reads
the queue's slot cap (6) and never writes it. No secret is read or
written.

## The proof

The real command, against the real board, with read-only `gh` calls:

```sh
overnight policy --root evidence/MO-225/night
overnight night --root evidence/MO-225/night --minutes 1 --interval 60
```

- 75 items planned, 8 dropped by the filter (with their reasons), 75
  receipts written, 2 cycles, ended: deadline.
- The morning report (`evidence/MO-225/night/receipts/morning-2026-11-13.md`):
  "How it ended: deadline. Items: 75 planned, 0 done, 0 ready, 6 stuck, 0
  parked, 69 waiting." The six stuck items are real: three pull requests
  whose checks fail and three whose gate the shift could not read
  (`UNKNOWN`). The 69 waiting items have no pull request yet.
- The window in the proof was one minute, not the full night, so the run
  fits the turn cap. The full window is the launchd job's window.

## What is left

1. Install on this Mac: `python3 install_coordinator.py` in `~/Code/mac-ops`,
   so the new `overnight` command and the new launchd job are live.
2. The real window: the job starts the night at 22:30 PT, the cycles run
   until 06:00 PT, and the morning report lands by 06:30 PT. Shyam reads
   it in the morning. That is T14's acceptance, and it is not yet met.
3. The gate's call on the diff.

## Rollback

Revert the commit and reinstall. The old job ran `shift --dry-run`, so a
reverted Mac reads the board and writes the morning report again.
