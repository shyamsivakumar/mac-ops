# MO-217 decisions

Run id: `ticket:shyamsivakumar/mac-ops#185:a1`. Refs #185.

## What landed

The overnight shift now has a per-item builder-time budget and a retry
cap (spec part T8a).

- `coordinator/overnight/overnight`: the budget rule, the policy fields,
  the fix-try count, the receipt and board wiring, and the `budget`
  command.
- `coordinator/overnight/README.md`: the budget section and the two new
  policy fields.
- `evidence/MO-217/fixture-over-hard-budget.json`: the fixture the proof
  runs on.

Nothing else changed. The merge, push, slot cap and Ascend rules are
untouched, no test file was added, and no existing test or check was
edited or weakened.

## The rule

Every item has a soft budget, a hard budget and a retry cap. The numbers
live in the policy snapshot (`soft_budget_minutes`, `hard_budget_minutes`
and the existing `retry_cap`), so the snapshot stays the whole contract.

| Case | What the shift does |
| --- | --- |
| Under the soft budget | Nothing. The item keeps its state. |
| Over the soft budget | The receipt says the builder must wrap up. The item keeps its state. |
| Over the hard budget | The item is stopped and written up: the receipt says `parked` and why, and the morning report lists it under "Decisions for you". |
| Out of fix tries | The item is parked, and the board proposes no further fix for it. |

The rule lives in one function (`budget_verdict`), and the receipt
writer, the board and the `budget` command all read it, so they cannot
disagree about when an item stops.

## Why these numbers

The spec gives 15 and 30 minutes, but revision 2 keeps the time limits
inside the ten-minute turn cap that the coordinator's own turncap job
enforces (`loop/turn_cap.py`, `CAP_SECONDS = 600`). A budget above the
turn cap could never be enforced, because the turn would end first. So
the soft budget is 5 minutes and the hard budget is 8: the builder has
most of the turn, and two minutes are left for the shift to stop the item
and write it up.

The ticket's scope is exactly this: "Soft and hard builder-time budget
per item (within the 10-minute turn cap the turncap job enforces) and at
most 2 fix tries; then park."

## Why the fix tries come from the queue

The queue writes one entry per fix it sent, under the head it sent it
for (`fix:<repo>#<pr>:<head>` in `queue.json`). One entry is one fix
try, so the count is the queue's own record. The shift keeps no count of
its own, which is the rule the whole module follows: the board is the
list, and the queue is the queue.

## Why the builder time is the sum of the thread's runs

The receipt's `Time used` was the minutes between a builder thread's
created and updated times. That number carries the idle time between two
runs: a builder that was sent its findings a day later showed a day of
"builder time" it never spent. The budget is measured against the sum of
the thread's own runs (start to end, and to now for a run that is still
going), so the number is the builder's own work and not the wall clock
between two messages.

The change also keeps the budget from parking the whole backlog. A pull
request whose builder ran for two hours and whose gate passed keeps the
state `ready`, because the work is finished and the budget stops work, not
history. Only an unfinished item is parked.

## Why the snapshot may leave the budget out

A snapshot that names a budget above the turn cap is refused: the budget
can never outlive the turn. A snapshot that names no budget at all keeps
working, because the shift falls back to the turn cap's budget. The
alternative (making the two fields required) would have stopped the live
24x7 shift at the next install, because the snapshot on the Mac was
written before this part. The fallback is stated in the README and in the
policy's own output, so it is never a silent default.

## Proof

The fixture is over its hard budget (9 min of an 8 min hard budget), and
the command is the real one.

```
$ python3 coordinator/overnight/overnight budget \
    --fixture evidence/MO-217/fixture-over-hard-budget.json --dry-run
Overnight budget - fixture (read only)
Item: MO-999 a fixture item over its hard budget
Repo: shyamsivakumar/mac-ops
Number: 217
Builder time: 9 min
Soft budget: 5 min
Hard budget: 8 min
Fix tries: 0 of 2
Verdict: over the hard budget
The receipt would hold:
- State: parked
- Stopped because: the builder used 9 min of its 8 min hard budget, so the item was stopped and parked
- Next: Shyam decides whether to give the item more time, to split it into a 5-minute part or to close it

A dry run writes no receipt.
```

The same rule through the real receipt writer, in a scratch folder (the
live records were not touched):

```
$ python3 coordinator/overnight/overnight receipt \
    --fixture evidence/MO-217/fixture-over-hard-budget.json --root "$SCRATCH"
overnight: wrote the receipt of the fixture item (wrote)
# MO-999

- Item: MO-999 a fixture item over its hard budget
- Repo: shyamsivakumar/mac-ops
- Ticket: MO-999 (#217)
- State: parked
- Gate: UNKNOWN
- Files: 0
- Time used: 9 min
- Observed: 0 s
- Stopped because: the builder used 9 min of its 8 min hard budget, so the item was stopped and parked
- Next: Shyam decides whether to give the item more time, to split it into a 5-minute part or to close it
```

The three other verdicts, on the same command with a changed fixture:
3 min gives `within the budget`, 6 min gives `over the soft budget` and
the item keeps its state, and 2 fix tries gives `out of fix tries` with
the item parked.

The live board, read only, in a scratch folder: `overnight receipt
--items 40` wrote 41 receipts and parked nothing, because no unfinished
item on the board had spent its budget. One item (SRW-1122) had a
builder that ran 118 minutes, and it kept its state `ready`, because its
work is finished and the budget stops work rather than history.

The policy snapshot the shift reads now carries the budget:

```
$ python3 coordinator/overnight/overnight policy --root "$SCRATCH"
Allow list: 12 repositories (...)
Slot cap: 6 (read only, from the coordq config; never raised)
Stall cap: 3 cycles with no new work
Retry cap: 2 fix tries per item, then it is parked
Builder-time budget: soft 5 min, hard 8 min (inside the 10 minute turn cap)
Verify level: balanced
```

## Check

`python3 scripts/mac_ops_fast_check.py` and the full local check through
`heavy` pass at the head of this branch. The builder check line is in
the pull request body.

## Rollback

Revert the commit and reinstall. The snapshot's two new fields are
optional, so the shift keeps working on a snapshot written before this
part.
