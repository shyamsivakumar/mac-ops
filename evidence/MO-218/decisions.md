# MO-218 decisions

Run id: `ticket:shyamsivakumar/mac-ops#186:a2`. Refs #186.

## What landed

The overnight shift now has the stall rule (spec part T8b).

- `coordinator/overnight/overnight`: the stall count, the item park, the
  board stall line, the sweep and the alert, and the `stall` command.
- `coordinator/overnight/README.md`: the stall section, the `stall` row of
  the command table, the `stall_cap` meaning and the `run/progress.json`
  record.
- `evidence/MO-218/fixture-three-idle-ticks.json`: three idle ticks over
  two items (the item park, the board stall and the alert).
- `evidence/MO-218/fixture-progress-resumes.json`: one idle item and one
  moving item (the count resets, the board is not a stall, no alert).

Nothing else changed. No new test file, and no existing test or check was
edited or weakened. Merge, push, the coordq slot cap and the Ascend rules
are untouched, and nothing here writes a secret: every record still goes
through `write_record`, `append_record` and `emit`.

## The rule

| Case | What the shift does |
| --- | --- |
| An item in play with new evidence | Its count drops back to one tick. |
| An item in play with no new commit and no new receipt for the stall cap | Its receipt says `parked` and why, a `stall <item>` line goes in the shift log, the shift moves on. |
| Every item in play still for the stall cap | A `stall` line goes in the shift log, the board sweep runs again under the same snapshot, and Shyam is alerted. The cycle carries on. |
| The board moves again | The board count resets and the next stall alerts again. |

A tick is one `overnight shift` cycle, because the tick job is retired:
the launchd job fires the cycle every five minutes, so a cycle is the look
at the board a tick used to be.

The count lives in `run/progress.json`: one entry per item in play (the
evidence it showed and how many ticks that evidence stayed the same) and
the board's own count. It is not a second queue. It names no work, sets no
order and decides nothing, it is pruned to the items the cycle saw, it is
written atomically, and a record that cannot be read starts a new count
and says so instead of stopping the cycle. The board and the queue stay
the only sources of truth, as the design fit requires.

The rule lives in one place (`advance_tick`), and the cycle and the
`stall` command both read it, so the proof is the code the cycle runs.

## Why only an item in play is counted

The ticket says "an item with no new commit or receipt for 3 ticks is
parked as 'stall'". Read literally over the whole board, a backlog ticket
nobody has started has no commit and no new receipt, so the entire todo
list would be parked in fifteen minutes and the night would "finish" by
parking work it never began. That cannot be the intent of a rule whose
point is to notice work that stopped moving.

So the count covers an item **in play**: an item with an open pull request
or a builder thread. A board with no item in play is never a stall. The
README states this, and the fixtures show both sides.

## Why the stall does not end the shift

The ticket is explicit: "The shift keeps running until every item is done
or parked." So the board stall writes the line, sweeps the board again and
alerts, and the shift keeps cycling. The morning report still says
`How it ended: stall` when the shift log holds a stall line, because a
report that said "all done" over a board nobody could move would be the
one lie the report must not tell. That is the existing `parse_shift_log`
rule, unchanged.

## The alert

Three things: the shift log names the line, `inbox/parking-lot.md` holds
the decision with a default and a recommendation so the morning report
puts it under "Decisions for you", and a best-effort desktop notification
(`osascript`) tries to reach Shyam now. The notification is reported and
never fails the cycle, because a headless job may not be allowed to post
one; the two records stand either way. Nothing here adds a merge, a push
or a slot-cap right.

## Proof

Both proofs are the real command on the real rule.

```
$ python3 coordinator/overnight/overnight stall \
    --fixture evidence/MO-218/fixture-three-idle-ticks.json
Overnight stall - fixture (read only), cap 3 ticks
Tick 1: board idle 1 of 3 | MO-1000 idle 1 of 3 | MO-999 idle 1 of 3
Tick 2: board idle 2 of 3 | MO-1000 idle 2 of 3 | MO-999 idle 2 of 3
Tick 3: board idle 3 of 3 | MO-1000 idle 3 of 3, parked as a stall | MO-999 idle 3 of 3, parked as a stall

stall MO-1000 | no new commit and no new receipt in 3 of 3 ticks | parked, the shift moves on
stall MO-999 | no new commit and no new receipt in 3 of 3 ticks | parked, the shift moves on
stall | the whole board showed no progress in 3 of 3 ticks | the board sweep runs again and Shyam is alerted
overnight: the board sweep would run again under the same policy snapshot, and Shyam would be alerted: a desktop notification, the parking lot and the shift log

This command writes nothing: the cycle writes the record.
```

```
$ python3 coordinator/overnight/overnight stall \
    --fixture evidence/MO-218/fixture-progress-resumes.json
Tick 1: board idle 1 of 3 | MO-1000 idle 1 of 3 | MO-999 idle 1 of 3
Tick 2: board idle 1 of 3 | MO-1000 idle 1 of 3 | MO-999 idle 2 of 3
Tick 3: board idle 1 of 3 | MO-1000 idle 1 of 3 | MO-999 idle 3 of 3, parked as a stall

stall MO-999 | no new commit and no new receipt in 3 of 3 ticks | parked, the shift moves on
the board moved inside the cap, so it is not a stall: no sweep and no alert
```

The cycle path was then run for real against the live board, read only, in
a scratch root (`--root "$SCRATCH"`, the live records were not touched):

1. `overnight policy --root "$SCRATCH"`, then three real `overnight shift`
   cycles (about a minute each, 70 items read, 70 receipts written).
   Cycle 1 wrote `run/progress.json` with `board idle 1 of 3`, 28 items in
   play, and cycle 2 counted the same evidence up (`idle 2`), so the
   ledger really carries the count between cycles.
2. The third cycle was seeded to `cap - 1` on the real path (a fixture on
   the ledger, not a code change) and it parked every item in play:
   `MO-263 | parked | wrote | state stuck -> parked`, with the receipt
   line `Stopped because: no new commit and no new receipt in 3 ticks (the
   stall cap is 3), so the item was parked as a stall`.
3. The same cycle wrote:

```
overnight: 2026-11-14 08:36 PST stall | the whole board showed no progress in 3 of 3 ticks | the board sweep runs again and Shyam is alerted
overnight: the stall sweep read the board again and it shows 69 items
overnight: alerted Shyam: a desktop notification, the parking lot and the shift log
```

   and the scratch `inbox/parking-lot.md` holds the decision, the shift log
   holds `stall sweep: the board shows 69 items`, and
   `overnight report --root "$SCRATCH" --dry-run` reads it back as
   `How it ended: stall. ... 27 parked` with the decision listed first.

## Check

`python3 scripts/mac_ops_fast_check.py` passes at this branch head
(`fast-check: passed; selected checks are not the full suite`) and the
`overnight --help` and `overnight stall --help` commands run.

The full local check through `heavy` was started and aborted by the
runner before it reported, so it is not claimed as run. That is the one
piece of the CI line this run did not finish; the next run must run
`~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` and put its
result in the pull request body.

## Rollback

Revert the commit and reinstall. `run/progress.json` is optional: a cycle
that finds none starts a new count, so an older record is never read as a
contract.
