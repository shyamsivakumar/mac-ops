# MO-225 decisions

Overnight runner spec part T14: the first unattended night. The coordinator
does checked work unattended and leaves one morning report.

Run id: `ticket:shyamsivakumar/mac-ops#193:a1`. Refs #193.

## What this ticket does and does not claim

The shift now runs real cycles, unattended, and leaves one morning report a
day. The command is proven against the real board (proof below). The real
overnight run has **not happened yet**: the Mac needs the installer to put
the new job and the new command in place, and then the job runs the shift
every 30 minutes, 24x7, and the first morning report lands in the morning.
Shyam reads that report. This ticket does not claim it has been read.

The branch was rebased onto `origin/main` after the gate's first FAIL, and
the design was reworked against main's revision 3 of the spec
(`c41a3b4`, "Overnight: the shift runs 24x7 and the pi tick is retired"):

- Main retired the night window. The shift runs 24x7, has no 22:30 start,
  no 06:00 deadline, is never armed and never unarmed, and every firing is
  one cycle. The first version of this ticket added a 22:30-to-06:00
  `overnight night` command with its own window. That window is gone: it
  contradicted main, and the shift has no window to work in.
- Main's `cmd_shift` already writes the receipts of every item whose state
  changed, from the board under the policy snapshot. The first version of
  this ticket wrote its own receipts. That code is gone: main's is the one
  that stays, and this ticket does not fork it.
- The tick job was retired. The shift job took over its 30-minute cadence,
  and it runs in dry-run mode. T14 is the part that makes the job do the
  real work.

So "full window" (spec revision 2) now means what main's revision 3 means:
the shift runs the whole time, works the whole backlog, and there is no
item cap and no allowance stop. The morning report is the one thing Shyam
reads.

## What landed

- `coordinator/launchd/dev.coordinator.overnight.plist`: the job runs real
  cycles (`shift`, not `shift --dry-run`). Every 30 minutes the shift reads
  the policy snapshot, reads the whole board, and writes a receipt for every
  item whose state changed.
- `coordinator/overnight/overnight`: the first cycle of the morning writes
  the day's morning report, so a day has one report and Shyam reads one
  thing in the morning. The shift has no window; the report has a time
  (06:00 to 07:29 PT, an hour and a half wide so a Mac that wakes late
  still writes it). `overnight shift --report` writes it on demand, and a
  later morning cycle leaves the day's report alone.
- `coordinator/overnight/overnight`: `run/STOP` still stops the shift at the
  next cycle, and the report still runs when it does. The report then says
  the shift ended with STOP, which is the record of the day.
- `coordinator/overnight/overnight`: the cycle states the count it worked,
  so the report's planned count is the count of the items the report lists.
  The order's own line keeps its per-repository detail: the order counts the
  work items, and the cycle counts every item it saw, including the pull
  requests already in flight and the backlog.
- `coordinator/overnight/overnight`: a pull request whose view cannot be
  read or parsed is no longer treated as a pull request that did not merge.
  The receipt says the view could not be read, so the item is never counted
  as done on a guess. (This was the gate's minor finding about a silently
  swallowed parse error, in main's receipt code.)
- `coordinator/overnight/README.md`: the contract names the real cycles, the
  morning report and the stop switch.
- `tests/test_install_coordinator.py`: the test that pinned the job to
  dry-run mode now pins it to real cycles. The behavior it asserted is the
  behavior this ticket changes; the assertion is as strict as before.
- `evidence/MO-225/shift/`: the proof run's records: `run/policy.json`,
  `run/shift-log.md`, the receipts and the morning report.

Not touched: the merge, push, slot-cap and Ascend rules. The shift reads
the queue's slot cap and never writes it. It starts no builder and runs no
merge and no push: the queue starts the work, under the rules that apply
today, and the shift records what it really saw. No secret is read or
written.

## The proof

The real command, against the real board, with read-only `gh` calls:

```sh
overnight policy --root evidence/MO-225/shift
overnight shift --root evidence/MO-225/shift --report
```

- One cycle, 94 items, 94 receipts, one morning report.
- The report says: "How it ended: UNVERIFIED. Items: 94 planned, 0 done, 0
  ready, 94 stuck, 0 parked." The end line is UNVERIFIED because a 24x7
  shift does not end: the shift log says how it ended only when the shift
  stopped, when everything finished or when it stalled. The stopped case is
  proven separately (below).
- The stop switch is proven by hand: with `run/STOP` in place, the cycle
  stops before it works anything, and the report is still written and says
  "How it ended: STOP".
- A second cycle was run over the same folder: it rewrote only the receipts
  whose state or evidence changed and left the rest alone, and it left the
  day's report alone.

## What is left

1. Install on this Mac: `python3 install_coordinator.py` in `~/Code/mac-ops`,
   so the new `overnight` command and the new job are live.
2. The real run: the job's cycles then run unattended, 24x7, and the first
   morning report lands by 07:29 PT. Shyam reads it in the morning. That is
   T14's acceptance, and it is not met yet.
3. The gate's call on the diff.

## Known limits of main's model, unchanged here

- An item whose builder has not opened a pull request yet is `stuck` in
  main's vocabulary, so a day with a full backlog reads as a day of stuck
  items. That is main's state model, and changing it is a separate ticket.
- The report's window is UNVERIFIED for the same reason the end line is: a
  24x7 shift has no window and no end.

## Rollback

Revert the commit and reinstall. The old job ran `shift --dry-run`, so a
reverted Mac reads the board and writes the cycle's line again.
