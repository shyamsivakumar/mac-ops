# MO-218 decisions

Run id: `ticket:shyamsivakumar/mac-ops#186:a3`. Refs #186.

Spec: the overnight runner spec, revision 2, section 10 (budgets and the
stall cap) and the ticket's own brief for part T8b.

## The review round

One reviewer round ran in-session (Codex, `gpt-6.1-sol`, high effort) over
`git diff origin/main...HEAD`. It returned FAIL with five major findings
and one minor. All six are fixed in this revision, and the fixes are
covered by the `stall` eval.

| Finding | The fix |
| --- | --- |
| The cached board snapshot was counted as an idle observation, so an item could be parked on a stale head. | A tick that could park an item or stall the board reads the board again first (`stall.pending`, `stall.board_pending`, `board_snapshot(force=True)`). The fresh head decides. |
| A draft pull request was measured, so the shift could park work it never does. | Drafts are not measured. |
| `unstick` ignored the stall state, so a parked issue could be recovered on a later tick. | A parked item is not recovered either. |
| Dispatch receipt attempts were compared as strings, so `a10` looked older than `a9` and new receipts stopped counting as progress. | The attempts are compared as numbers. |
| A board where new work arrived every tick still counted as no progress. | New work arriving on the board is progress; the board's first tick is its baseline. |
| The shift log said "Shyam was alerted" even when the alert could not be written. | The log claims the alert only after the alert was written. |

The reviewer raised no objection to the state file's home, to the report's
end reason, or to the isolation of the `start-routing` eval, and found no
weakened assertion and no change to merge authority, the push rules, the
slot cap or the Ascend rules.

## What landed

- `coordinator/overnight/stall.py` (new): the stall rule, and only the rule.
  `observe` decides one item, `board` decides the board, `moved` says
  whether an item's marker changed, `alert` writes the alert on the
  coordinator's board. Every function is pure except the alert.
- `coordinator/overnight/lane_driver.py`: the pass measures every item it
  works against the state the shift kept, prints the stall events, skips a
  parked item, and sweeps the board again when the whole board stopped
  moving.
- `coordinator/overnight/overnight`: the shift loads and saves the stall
  state around the pass, writes the records of the stall events (the
  receipt of a parked item, the lines in the shift log, the alert), and
  gains the command `overnight stall` that runs the rule over a fixture or
  shows the shift's own state.
- `coordinator/overnight/selftest.py`: the `stall` eval, with its negative
  control. It covers the idle count, the progress that resets it, the
  board's baseline, the fresh read before a park, the draft that is not
  measured, the parked item that is not recovered, and the parked item the
  lane skips.
- `coordinator/overnight/README.md`: the rule, the state file and the
  command.
- `evidence/MO-218/stall-fixture.json`: the fixture with three idle ticks.

Not touched: the merge rules, the push rules, the queue's slot cap, the
Ascend rules, the parking lot (spec part T10), the morning report's own
rules (spec part T11). No existing test or check was weakened.

## Proof

The fixture has three idle ticks of one item: the item's commit and its
newest dispatch receipt do not change.

```
$ python3 coordinator/overnight/overnight stall \
    --fixture evidence/MO-218/stall-fixture.json --root /tmp/mo218proof
STALL shyamsivakumar/mac-ops#218: no new commit or receipt for 3 ticks; parked, the shift moves on
STALL board: no board progress for 3 ticks; the board is swept again
wrote /tmp/mo218proof/receipts/MO-218.md (wrote)
wrote /tmp/mo218proof/decisions.json
```

The records the run wrote:

```
$ cat /tmp/mo218proof/run/shift-log.md
2026-11-16 05:42 AM PT | stall: shyamsivakumar/mac-ops#218 parked, no new commit or receipt for 3 ticks; the shift moves on
2026-11-16 05:42 AM PT | stall: no board progress for 3 ticks; the board was swept again and Shyam was alerted

$ cat /tmp/mo218proof/receipts/MO-218.md
# MO-218

- Item: Overnight T8b: Stall detection
- Repo: shyamsivakumar/mac-ops
- Ticket: MO-218 (#218)
- State: parked
- Time used: 0 min
- Observed: 0 s
- Stopped because: stall: no new commit or receipt for 3 ticks
- Next: Shyam re-cuts the item or hands it back to the shift

$ cat /tmp/mo218proof/decisions.json
{
 "items": [
  {
   "id": "factory-overnight-stall",
   "group": "Coordinator",
   "kind": "action",
   "title": "Overnight shift stalled: no board progress for 3 ticks",
   "why": "The overnight shift saw no board progress for 3 ticks. The board was swept again and the shift keeps running until every item is done or parked."
  }
 ],
 "updated": "2026-11-16T13:42:37Z"
}
```

The fixture run wrote nothing outside the folder it was given.

The registered evals:

```
$ python3 coordinator/overnight/overnight selftest
PASS send-integrity
PASS consolidation-guard
PASS script-results
PASS start-routing
PASS gate-pipeline
PASS no-parking
PASS turncap
PASS watchdog
PASS zero-merge
PASS board-integrity
PASS api-budget
PASS ff-drift
PASS stall
```

The repository check:

```
$ ~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py
...
fast-check: passed; selected checks are not the full suite
```

The installer picks the new module up with the rest:

```
$ python3 install_coordinator.py install --dry-run
{
  "action": "coordinator",
  "would_write": [
    ...
    "/Users/shyamsivakumar/.local/bin/stall.py",
    ...
  ],
```

Nothing was installed and no live service was touched: the run above is a
preview, and the proof runs wrote only into a fixture folder.

## Decisions

### 1. The item's marker is its commit and its receipt

- **When**: revision 1.
- **The decision**: An item's marker is one string: the head commit of its
  pull request and the number of its newest dispatch receipt. A tick that
  changes either one is progress; a tick that changes neither is an idle
  tick. Three idle ticks park the item as `stall`.
- **The gap**: The brief says "no new commit or receipt". It does not say
  where the receipt comes from.
- **The reach**: The receipt is the queue's own record
  (`queue/dispatch-receipts.json`), the same file the rest of the shift
  reads, so the shift keeps no list of its own and counts no attempt of
  its own. The commit is the head of the pull request the board already
  shows. The first tick of an item counts as idle: there is nothing yet to
  compare it with, and counting it parks an item one tick earlier than a
  strict reading would. The attempts are compared as numbers, so `a10` is
  newer than `a9`.
- **The review**: The reviewer showed that the cached board snapshot made a
  stale head count as an idle tick. A tick that could park an item now
  reads the board again first, and the fresh head decides.

### 2. An item is measured when it has a commit or a receipt

- **When**: revision 1.
- **The decision**: The shift measures an item that has a commit or a
  receipt. An item with neither is not measured: it is an item the shift
  has not started yet, and the shift still starts it.
- **The gap**: The brief's rule reads literally: any item with no new
  commit or receipt for three ticks is parked. Taken literally, a ticket
  the ticket CLI refused to start would be parked as a stall after three
  ticks and never started again, and the shift would silently give up on
  it.
- **The reach**: A ticket that the shift started has a receipt, so it is
  measured and it is parked if the builder never delivers. A pull request
  has a commit, so it is measured and it is parked if nothing moves on it.
  A draft pull request is not work the shift does, so it is not measured.
  A ticket that was never started keeps being started (the queue's own
  thirty-minute refusal cache still applies). The literal reading would
  have changed the `start-routing` eval: its fixture shows five ticks with
  no recorded progress, so the literal rule parks the ticket the eval
  asserts is started. Keeping the existing check intact was worth the
  narrower reading.

### 3. The stall state lives in the shift's folder, not in the lane ledger

- **When**: revision 1.
- **The decision**: The state is `run/stall-state.json`, in the shift's own
  folder, next to the policy snapshot and the shift log. The lane ledger
  keeps no stall key.
- **The gap**: The first version kept the state in the lane ledger, next
  to the board snapshot and the pass counter.
- **The reach**: The lane ledger has an eval that asserts a pass that took
  no action leaves it empty (`exact(ledger, {})` in `start-routing`). A
  state key in the ledger broke that check. The shift's own folder is the
  better home anyway: the state is the shift's record of its work, and the
  shift writes it through `write_record`, so it is redacted like every
  other record. The ledger stays the lane's record.

### 4. A stall is not the end of the shift

- **When**: revision 1.
- **The decision**: A stalled board is swept again in the same tick, the
  shift log says `stall`, the alert goes to the coordinator's board, and
  the shift keeps running until every item is done or parked. The morning
  report's end reason now needs the shift to state that it ended with a
  stall; a stall line alone ends nothing.
- **The gap**: The shift log parser treated any line with the word `stall`
  as the end of the shift, so the report would have said "How it ended:
  stall" for a shift that was still running.
- **The reach**: The report's four end reasons stay the four the spec
  allows. `ended: stall` in the shift log still ends the shift with a
  stall, and a stall event on its own does not. The report's other rules
  are untouched. This is the one place where the part reaches into the
  report (spec part T11), and only because the report would otherwise
  claim something false.

### 5. The alert is one item on the coordinator's board

- **When**: revision 1.
- **The decision**: The alert is an item with the id
  `factory-overnight-stall` on the coordinator's board file
  (`coordinator/decisions.json`), the same board the merge alert
  (`factory-zero-merge`) and the watchdog (`factory-watchdog`) use. The
  item is replaced, so a stalled board shows one alert and not one per
  tick.
- **The gap**: The brief says "alert Shyam" and does not name the channel.
- **The reach**: No new channel and no new rights. The alert is a local
  file write, like the two alerts that are already there. The shift's
  folder keeps the detail (the shift log lines and the receipt of the
  parked item), so nothing is lost when the board item is replaced. The
  board file is written the way the merge alert and the watchdog write it,
  so it is not redacted: it holds the coordinator's own items, not the
  shift's records. The shift log says that Shyam was alerted only after
  the alert was written.

### 6. One existing eval changed, and only to keep it hermetic

- **When**: revision 1.
- **The decision**: The `start-routing` eval now patches
  `lane.stall_receipts` to return no receipts. No assertion changed.
- **The gap**: The pass reads the queue's dispatch receipts to measure the
  items. Without the patch the eval's result would depend on the live
  receipts file, and a live receipt for the fixture's ticket would park it.
- **The reach**: The eval reads no live file and asserts exactly what it
  asserted before. The other twelve evals are untouched.

### 7. New work arriving on the board is progress

- **When**: revision 1.
- **The decision**: The board moved when an item's marker changed or when
  a new item appeared on it. The board's first tick is its baseline, the
  way the first tick of an item is.
- **The gap**: The brief says "if the whole board shows no progress for 3
  ticks" and does not say what progress on the board is.
- **The reach**: A board where each tick brings a new item with a new
  commit is a board that is working, and the shift does not alert Shyam
  about it. The baseline keeps the fixture honest: its three ticks are
  three idle ticks, so the third one stalls the board.

## What is not proven here

- The shift was not run against the live board and no live service was
  read or written. The proof is the real command over the real rule on a
  fixture, and the fixture evals.
- The install was not performed: the installer preview shows that the new
  module is installed with the rest. The coordinator owns installation.
- The parked item's receipt carries no check and no gate verdict, because
  a stalled item never reached one. The receipt says `State: parked` and
  names the stall, and the morning report counts it as parked.
