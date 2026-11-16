# MO-218 decisions

Run id: `ticket:shyamsivakumar/mac-ops#186:a3`. Refs #186.

Spec: the overnight runner spec, revision 2, section 10 (budgets and the
stall cap) and the ticket's own brief for part T8b.

## The gate round

The Opus gate reviewed the first head (`e0cddb0`) and returned FAIL with
four findings. All four are fixed here.

| Finding | The fix |
| --- | --- |
| The lane skipped stalled pull requests and blocked ticket starts, which violates the ticket's newer instruction to report stalls without parking builders. | Both exclusions are gone, and so is the recovery exclusion. A stalled item is reported and the shift keeps working it. |
| Progress was measured from a snapshot cached for five passes while the stall was declared after three, so a new commit could go unseen. | A tick that could report a stall or stall the board reads the board again first. The fresh head decides. |
| Dispatch receipt attempts were compared as strings, so `10` sorted below `9`. | The attempts are compared as numbers. |
| The decisions file recorded only the selected fast check. | The full local check is recorded below, with the two failures that also fail on `origin/main`. |

The ticket's newer instruction is the one that changed the design, and it
is recorded in the ticket itself (Shyam, 2026-11-16 12:42 PT):

> Preserve the newer no-parking policy from Refs #376: report stalled work
> without parking builders.

So the shift reports a stall and keeps working the item. It does not skip
the item, does not block its start, does not recover it, does not label it
and does not re-cut it. The receipt says `State: stuck`, not `parked`.

## The sixth gate round

The gate ran against `10b50bc` and returned one minor finding: the stall
view printed `parked` for an item the lane keeps working, so it reported
an operational state the shift does not have. The label is `stalled` now:

```
$ python3 coordinator/overnight/overnight stall --root /tmp/mo218j
Overnight stall state
shyamsivakumar/mac-ops#218: idle 3 tick(s) stalled
Board idle: 3 tick(s)
```

The receipt of a reported item says `State: stuck`, the shift log says the
item was reported and the shift keeps working it, and no record in the
stall path says `parked`.

## The fifth gate round

The gate ran against `a860533` and returned one major finding and one
minor.

| Finding | Where it is fixed now |
| --- | --- |
| The board was marked as alerted before the alert was delivered, and the state was persisted before the alert was written, so a failed write suppressed the retries for good. | Fixed in `687dced`: `stall.board` does not set the flag, `stall_records` sets it with `stall.delivered` only after the alert was written, and the shift writes the records before it saves the state. The `stall` eval covers it: the board asks again while the alert was not delivered and stops asking once it was. |
| The stall view displayed stalled items as "parked", against the amended policy. | `coordinator/overnight/overnight`: `overnight stall` now says "reported", and the receipt of a reported item says `State: stuck`. Nothing in the stall path parks a builder. |

The gate noted that the full suite still shows two failures. Both are
pre-existing on `origin/main` and both come from other parts' changes,
not from this one:

- `tests/test_install_coordinator.py::test_coord_pi_exports_coord_wake_zero`
  expects `export COORD_WAKE=0` in `coordinator/pi/bin/coord-pi`. The
  launcher now defaults wake on (`export COORD_WAKE="${COORD_WAKE:-1}"`),
  which came with `7d33f57` ("Enable coordinator backlog auto-wake",
  Refs #346). Making the test pass again would undo another ticket's
  decision.
- `tests/test_gatekeep_retry_limit.py::test_a_dead_opus_gate_is_not_requeued`
  uses the stale gate-model fixture that `docs/coord-watch.md` already
  records as failing on `origin/main`.

Both fail the same way in a clean worktree of `origin/main`
(`580535a0b096161fe54e0f60b718b98ed79aad7a`), with no errors. No test was
changed and no assertion was removed to hide them: they belong to other
parts, and this part does not touch the launcher, the gatekeep retry
policy or the queue. The full-suite receipt is in "The repository
checks" below.

## A self-review round

A self-review over the same diff, with the gate's bar in mind, found and
fixed three more things:

- `stall.appeared` and `stall.stalled` were not used by the shift any
  more: `appeared` was replaced by `arrived` (new work on the board) and
  `stalled` had no caller outside the eval. Both are gone, so the module
  has no unused surface.
- The module docstring still said the state lived in the lane ledger. It
  lives in `run/stall-state.json`, in the shift's own folder, and the
  docstring says so now.

## The fourth gate round

The gate ran against `1c8fd42` and returned one major finding: the board
was marked as alerted before the alert was delivered, so a decisions file
that was temporarily unreadable or unwritable left the board quiet for
good. It is fixed:

- The rule (`stall.board`) no longer sets the flag. It asks while the
  board is idle and the alert was not delivered.
- The writer (`stall_records`) sets the flag with `stall.delivered` only
  after the alert was written, and says so in the shift log.
- The shift writes the records before it saves the state, so the persisted
  flag says "delivered" only when the alert was delivered. A tick whose
  alert could not be written leaves the flag unset, and the next idle
  tick asks again.

The `stall` eval covers it: the board asks again while the alert was not
delivered, and stops asking once it was.

The gate's note that "drafts are excluded from item measurement, but still
counted toward board stalls" is fixed too: a draft is not on the board
for the shift, so it is not measured and it is not counted.

## The third gate round

The gate ran against `ab4bb8b` and returned the same two major findings.
Both were already fixed in `d7bdbc5`, which is two commits earlier than
the head the gate read:

| Finding | Where it is fixed now |
| --- | --- |
| The lane skipped stalled pull requests and blocked ticket starts and the recovery path. | `coordinator/overnight/lane_driver.py`: the pull request loop calls `act_on_pr` for every pull request (line 724), `start_next` filters the ready tickets by stage, problems and group only (line 506), and `unstick` lists its orphans without a stall condition (line 537). The driver reads the stall state only to measure and report it; nothing in it suppresses work, and the driver's `park()` is never called by the stall path. |
| The decisions file recorded only the selected fast check. | `evidence/MO-218/decisions.md`, "The repository checks": the fast check and the full local suite, with the head they ran on. |

The gate's reconciliation note said that "new tickets without receipts
remain excluded from progress detection". That is fixed now: the board
tracks the keys it holds, so a new ticket on the board is progress whether
or not the shift has measured it, and the tracking stays bounded by the
board. The `stall` eval covers it (a board that receives a new ticket every
tick does not stall).

## The second gate round

The gate ran again and returned the same report, against the same first
head (`e0cddb0`): it says "Reconfirmed the exact head and PR-body line:
`Builder check: PASS e0cddb00e55cdf36664e731034efe90b0475a9d9`". The four
findings are the four above, and all four are already fixed in this
revision. Where each one is fixed, at this head:

| Finding | Where it is fixed now |
| --- | --- |
| The lane skipped stalled pull requests and blocked ticket starts. | `coordinator/overnight/lane_driver.py`: the pull request loop calls `act_on_pr` for every pull request (line 724), `start_next` filters the ready tickets by stage, problems and group only (line 506), and `unstick` lists its orphans without a stall condition (line 537). No stall state is read anywhere in the driver except to measure and report it. The receipt of a stalled item says `State: stuck`, and the shift log says the item was reported and the shift keeps working it. |
| Progress was measured from a snapshot cached for five passes. | `coordinator/overnight/lane_driver.py` lines 678-689: a tick that could report a stall or stall the board reads the board again first (`stall.board_pending`, `stall.pending`, `board_snapshot(ledger, force=True)`), and the markers are taken from that fresh board. |
| Receipt attempts were compared as strings. | `coordinator/overnight/lane_driver.py` line 170: `receipt_attempt` compares the attempts as numbers, so `a10` is newer than `a9`. |
| The decisions file recorded only the selected fast check. | `evidence/MO-218/decisions.md`, "The repository checks": the fast check and the full local suite (`heavy timeout 300 python3 -m unittest discover -s tests -t .`, 288 tests, the two failures that also fail on `origin/main`). |

The gate's own note that "the ticket's earlier detector gap has an
implementation, but its no-parking requirement remains unresolved" is
answered by decision 0: the shift reports a stalled item and keeps
working it, and the lane's `park()` is never called by the stall path (or
by anything else in the driver).

## The review round

One reviewer round ran in-session (Codex, `gpt-6.1-sol`, high effort) over
`git diff origin/main...HEAD`. It returned FAIL with five major findings
and one minor. All six are fixed in this revision, and the fixes are
covered by the `stall` eval.

| Finding | The fix |
| --- | --- |
| The cached board snapshot was counted as an idle observation, so an item could be reported as stalled on a stale head. | A tick that could report a stall or stall the board reads the board again first (`stall.pending`, `stall.board_pending`, `board_snapshot(force=True)`). The fresh head decides. |
| A draft pull request was measured, so the shift could report work it never does. | Drafts are not measured. |
| `unstick` ignored the stall state, so a reported issue could be kept out of the recovery path. | The exclusion is gone: a reported item is recovered like any other. |
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
  works against the state the shift kept, prints the stall events, reads
  the board again before it decides, and sweeps the board again when the
  whole board stopped moving. It never skips a stalled item and never
  blocks one.
- `coordinator/overnight/overnight`: the shift loads and saves the stall
  state around the pass, writes the records of the stall events (the
  receipt of a stalled item, the lines in the shift log, the alert), and
  gains the command `overnight stall` that runs the rule over a fixture or
  shows the shift's own state.
- `coordinator/overnight/selftest.py`: the `stall` eval, with its negative
  control. It covers the idle count, the progress that resets it, the
  board's baseline, the fresh read before a decision, the draft that is
  not measured, the stalled item the lane keeps working, and the bounded
  tracking.
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
STALL shyamsivakumar/mac-ops#218: no new commit or receipt for 3 ticks; reported, the shift keeps working it
STALL board: no board progress for 3 ticks; the board is swept again
wrote /tmp/mo218proof/receipts/MO-218.md (wrote)
wrote /tmp/mo218proof/decisions.json
```

The records the run wrote:

```
$ cat /tmp/mo218proof/run/shift-log.md
2026-11-16 05:55 AM PT | stall: shyamsivakumar/mac-ops#218 reported, no new commit or receipt for 3 ticks; the shift keeps working it
2026-11-16 05:55 AM PT | stall: no board progress for 3 ticks; the board was swept again and Shyam was alerted

$ cat /tmp/mo218proof/receipts/MO-218.md
# MO-218

- Item: Overnight T8b: Stall detection
- Repo: shyamsivakumar/mac-ops
- Ticket: MO-218 (#218)
- State: stuck
- Time used: 0 min
- Observed: 0 s
- Stopped because: stall: no new commit or receipt for 3 ticks
- Next: the shift keeps working the item; Shyam sees it in the morning report

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

The repository checks, run at head `b274f78702196f3d216354e9751f4e34884a543a`
(the commit after it adds only this receipt):

```
$ ~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py
...
fast-check: passed; selected checks are not the full suite

$ ~/.local/bin/heavy timeout 300 python3 -m unittest discover -s tests -t .
Ran 288 tests in 7.889s
FAILED (failures=2)
```

The two failures are `tests/test_gatekeep_retry_limit.py`
(`test_a_dead_opus_gate_is_not_requeued`) and
`tests/test_install_coordinator.py`
(`test_coord_pi_exports_coord_wake_zero`). Both fail the same way on
`origin/main`: they were run in a clean worktree of `origin/main`
(`580535a0b096161fe54e0f60b718b98ed79aad7a`) and produced the same two
failures and no errors. The first is the stale gate-model fixture that
`docs/coord-watch.md` already records as failing on `origin/main`; the
second reads a launcher on this Mac that the test does not expect. Neither
touches this part, and no test was changed to make the suite pass.

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

### 0. A stalled item is reported, not parked

- **When**: revision 2.
- **The decision**: The shift measures the idle cycles, and after three
  unchanged observations it reports the stall: a receipt for the item
  (`State: stuck`), a line in the shift log and, for the board, one alert.
  The shift keeps working the item. Nothing is skipped, nothing is
  blocked, nothing is labelled and nothing is re-cut.
- **The gap**: The ticket's brief says "parked as 'stall' and the shift
  moves on". The ticket's newer instruction (Shyam, 2026-11-16, quoted
  above) says to preserve the no-parking policy from Refs #376 and to
  report stalled work without parking builders.
- **The reach**: The newer instruction wins, and the lane's own no-parking
  policy (Refs #376) agrees: the lane never parks a builder. So the shift
  reports the stall and keeps working the item. The receipt says `State:
  stuck`, because the item is not set aside: the morning report names it
  under "Stuck", and Shyam sees it there. The gate on the first head
  found the opposite of this (the lane skipped stalled items and blocked
  their starts) and failed the pull request for it; both exclusions are
  gone, and so is the third one in the recovery path.

### 1. The item's marker is its commit and its receipt

- **When**: revision 1.
- **The decision**: An item's marker is one string: the head commit of its
  pull request and the number of its newest dispatch receipt. A tick that
  changes either one is progress; a tick that changes neither is an idle
  tick. Three idle ticks report the item as stalled.
- **The gap**: The brief says "no new commit or receipt". It does not say
  where the receipt comes from.
- **The reach**: The receipt is the queue's own record
  (`queue/dispatch-receipts.json`), the same file the rest of the shift
  reads, so the shift keeps no list of its own and counts no attempt of
  its own. The commit is the head of the pull request the board already
  shows. The first tick of an item counts as idle: there is nothing yet to
  compare it with, and counting it reports an item one tick earlier
  than a strict reading would. The attempts are compared as numbers, so `a10` is
  newer than `a9`.
- **The review**: The reviewer showed that the cached board snapshot made a
  stale head count as an idle tick. A tick that could report a stall now
  reads the board again first, and the fresh head decides.

### 2. An item is measured when it has a commit or a receipt

- **When**: revision 1.
- **The decision**: The shift measures an item that has a commit or a
  receipt. An item with neither is not measured: it is an item the shift
  has not started yet, and the shift still starts it.
- **The gap**: The brief's rule reads literally: any item with no new
  commit or receipt for three ticks is reported. Taken literally, a ticket
  the ticket CLI refused to start would be reported as stalled after three
  ticks, and the shift would keep reporting it instead of trying it again.
- **The reach**: A ticket that the shift started has a receipt, so it is
  measured and it is reported if the builder never delivers. A pull request
  has a commit, so it is measured and it is reported if nothing moves on it.
  A draft pull request is not work the shift does, so it is not measured.
  A ticket that was never started keeps being started (the queue's own
  thirty-minute refusal cache still applies). The literal reading would
  have changed the `start-routing` eval: its fixture shows five ticks with
  no recorded progress, so the literal rule reports the ticket the eval
  asserts is started as stalled. Keeping the existing check intact was worth the
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
  stalled item), so nothing is lost when the board item is replaced. The
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
  receipts file, and a live receipt for the fixture's ticket would report it
  as stalled.
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
  three idle ticks, so the third one stalls the board. The tracking is
  bounded: an item's idle count stops at the cap, an item that leaves the
  board is not tracked any more, and the board is alerted once per episode
  (the alert comes again after the board moves and stalls a second time).

## What is not proven here

- The shift was not run against the live board and no live service was
  read or written. The proof is the real command over the real rule on a
  fixture, and the fixture evals.
- The install was not performed: the installer preview shows that the new
  module is installed with the rest. The coordinator owns installation.
- The stalled item's receipt carries no check and no gate verdict, because
  a stalled item never reached one. The receipt says `State: stuck` and
  names the stall, and the morning report counts it as stuck.
