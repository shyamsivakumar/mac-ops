# MO-238 decisions

Run id: `ticket:shyamsivakumar/mac-ops#243:a1`. Refs #243.

The refill in `coordinator/bin/coordq` used to look at the oldest
`REFILL_MAX` (40) candidates of the board and stop there. A blocked ticket at
the front of that list was refused again in every pass, so the same tickets
were re-checked forever and the eligible tickets further down the board were
never reached. The change makes the refill cover the whole board over time.

## What changed

One file: `coordinator/bin/coordq`.

1. **A refusal ledger.** Every refused candidate is written to
   `refill-state.json` in the coordinator queue directory, with the reason,
   the pass it was refused in, and the board state it was refused on
   (`updatedAt`, title and label names as the board shows them).
2. **A skip rule.** A candidate whose board state is unchanged since its last
   refusal is skipped, so the pass walks past it instead of paying for the
   ticket CLI again. The skip expires after `COORDQ_REFILL_RETRY_AGE`
   (default 3600 seconds), because a ticket can become startable without the
   ticket itself changing, for example when a blocker closes.
3. **The scan no longer stops at the window.** The refill walks the whole
   candidate list. `REFILL_MAX` is now the number of ticket CLI attempts one
   pass may make, and a skipped refusal does not count against it, so each
   pass reaches further down the board than the one before it.
4. **A per-pass record.** The state file keeps the pass count and the record
   of the last pass (examined, skipped, attempted, started, and the refused
   candidates with their reasons). Every refusal is also logged to
   `dispatch.log` as before.

Nothing else moved. The slot cap (`cap()`, `used_slots()`), the stage
labels, the hold rules, the ticket CLI's own refusals, the merge, push and
Ascend rules are untouched. The refill still asks the ticket CLI for every
start, so a ticket the CLI would refuse today is still refused today. No
new unit test file was added, and no existing test or check was touched.

## The board, read live

`gh search issues` over the repos in `~/.coordinator/tickets.json`, read at
2026-11-13 16:45 PST, returned **120** open `stage:todo` candidates. The old
window was the first 40 of them, ending at
`shyamsivakumar/strategy-replay-workbench#680`. The first candidate outside
that window is `shyamsivakumar/strategy-replay-workbench#692` at position 41.

`ticket start shyamsivakumar/strategy-replay-workbench#692 --dry-run` exits
0, so the ticket CLI accepts it today; it is eligible and it is outside the
old first-40 window.

## Proof

### The scan reaches past the window

The real `refill()` was driven against a 60 candidate board (candidates 1 to
40 refused by the ticket CLI, 41 and up accepted) with the real code, the
real lock, the real state file and the real log:

| pass | attempted | skipped | started |
| --- | --- | --- | --- |
| 1 | 1 to 40 | 0 | 0 |
| 2 | 41 to 46 | 40 | 6 |
| 3 | 41 to 46 | 40 | 6 |
| 4 (candidate 1 changed on the board) | 1, then 41 to 46 | 39 | 6 |

Pass count: 4. Skipped-refusal count in the last pass: 39. Pass 2 skipped
the 40 candidates refused in pass 1 and started candidate 41, which the old
`candidates[:REFILL_MAX]` window could never reach. Pass 4 shows that a
candidate whose board state changed is attempted again even though its last
refusal is still on file.

The same numbers come out of the live state file, which keeps the pass
count and the skipped count of the last pass.

### The live board

The refill was run against the live board and the live coordinator queue
directory (`~/Code/coordinator/queue`) with the repository copy of
`coordinator/bin/coordq`, in a loop, so the pass runs as soon as a slot is
free.

**The live board was at its slot cap for the whole run.** The coordinator
queue holds 6 live threads against a cap of 6, and the log line for every
attempt was `refill skipped: at cap 6/6` (and `the slots are full (7/6)`
when the queue held a waiting item). The refill correctly started nothing,
because nothing could be started. No pass of the new code ran against the
live board during this run, so the live pass count is 0 and the live
skipped-refusal count is 0.

That is the one part of the acceptance that is still open: the live run has
to wait for a free slot on the machine. The mechanism is proven above and
the live board has an eligible ticket outside the old window
(`strategy-replay-workbench#692` at position 41 of 120), so the first pass
that finds a free slot starts a ticket that the old window never reached.

The installed `~/.local/bin/coordq` was written at 16:45 by another
in-flight worktree (`t3-e50d2c39`), so the proof ran the repository copy
directly and did not overwrite it. The install stays with the merged commit.

## Checks

- `python3 scripts/mac_ops_fast_check.py` passed.
- `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` passed.
- The head sha and the check result are in the pull request body.

## Known limits

- The live start of a past-window ticket is not recorded yet (see above).
- The board state used for the skip is what the board search shows
  (`updatedAt`, title, labels). A ticket whose only change is in a blocker
  it depends on keeps its own `updatedAt`, so it is retried when the refusal
  grows older than `COORDQ_REFILL_RETRY_AGE`, not before.
- The scan order is still oldest first. The night-shift runner
  (`coordinator/overnight/overnight`) owns the ordering (ticket MO-210); the
  refill keeps its own order and only covers more of the board.

## Rollback

Revert the commit and reinstall the coordinator.
