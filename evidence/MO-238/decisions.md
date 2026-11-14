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

### The follow-up fixes (after the reviewer round)

- **Only a real refusal is recorded.** The ticket CLI exits 2 for a refusal
  and 1 for a failed check (`gh` error, timeout). Only exit 2 is written to
  the ledger now. A failed check is logged as `refill could not check` and
  is retried by the next pass, instead of hiding the ticket for the retry
  age.
- **A dry run writes nothing.** `refill --dry-run` no longer adds a pass to
  the count and no longer writes the state file, so a diagnostic cannot hide
  a ticket from the next real pass.
- **The examined count is the real one.** The pass line reports the number
  of candidates the pass actually looked at, not the size of the board.

## The board, read live

`gh search issues` over the repos in `~/.coordinator/tickets.json`, read at
2026-11-13 16:58 PST, returned **112** open `stage:todo` candidates. The
old window was the first 40 of them. The candidates outside that window
that the ticket CLI accepts today (each checked with a real
`ticket start <repo>#<n> --dry-run`, exit 0):

| position | ticket | ticket CLI |
| --- | --- | --- |
| 44 | `shyamsivakumar/strategy-replay-workbench#716` | accepted |
| 45 | `shyamsivakumar/strategy-replay-workbench#720` | accepted |
| 48 | `shyamsivakumar/strategy-replay-workbench#723` | accepted |

The board moves as tickets change stage, so the positions are a reading of
that moment, not a fixed list.

## Proof

### The scan reaches past the window

The real `refill()` was driven against a 60 candidate board (candidates 1 to
40 refused by the ticket CLI with exit 2, 41 and up accepted) with the real
code, the real lock, the real state file and the real log. The harness
lives outside the repository, because the ticket bans new test files; it is
at `$TMPDIR/mo238/harness.py` and is run with:

```sh
python3 "$TMPDIR/mo238/harness.py"
```

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

The same two numbers come out of the state file, which keeps the pass count
and the skipped count of the last pass.

### The live board

The refill was run against the live board and the live coordinator queue
directory (`~/Code/coordinator/queue`). The new `coordq` is installed in
`~/.local/bin/coordq`, so the live dispatcher runs it on its own cadence
(`coordq dispatch` every 30 seconds, a refill at most every 300 seconds).

One pass of the new code ran against the live board, at 16:53:21:

```
refill refused shyamsivakumar/fantasy-football-toolkit#185: refused: text blockers: ...#184 is still open
refill pass 1: examined 117 candidate(s), skipped 0 unchanged refusal(s), attempted 1, started 0
```

Live pass count: 1. Live skipped-refusal count: 0. The state file holds one
refusal record, for `fantasy-football-toolkit#185`, with its reason.

**The live start of a ticket from past the old window is still open.** The
machine was over its cap for the whole run: 7 live threads against a cap of
6, and a queue that held 16 items from the overnight runner and the gate
job. The refill answers that correctly and starts nothing (`refill skipped:
at cap 6/6`, `refill skipped: the queue holds 16 item(s)`). The old code
would have answered the same way: the slot cap and the queue check come
before the scan, and they are not what this ticket changes.

What is proven on the live board today is that the eligible tickets outside
the old window exist (the table above) and that the pass reaches them once
the machine has a free slot and the queue is empty. The next live pass that
finds one starts a ticket that the old window never reached, and its number
and position land in `dispatch.log` and in `refill-state.json`.

## Checks

- `python3 scripts/mac_ops_fast_check.py` passed.
- `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` passed.
- The head sha and the check result are in the pull request body.

## The reviewer round

One in-session Opus 5.5 round read `git diff origin/main...HEAD` and
returned `VERDICT: FAIL`. What it found and what was done:

1. **The live proof was missing and the evidence was out of date.** The
   evidence now carries the live pass count and the skipped count that
   `refill-state.json` holds, the live board reading with its timestamp, and
   an explicit statement that the live start of a past-window ticket is
   still open and why.
2. **A builder loop was left running.** The loop
   (`$TMPDIR/mo238/loop.sh`) that drove the refill every two seconds with
   the throttle off was stopped. The live dispatcher now runs the new
   `coordq` on its own cadence, so nothing runs unattended with the
   throttle off.
3. **A failed check was stored as a refusal.** Fixed: only exit code 2 is
   recorded; a failed check is logged and retried.
4. **A dry run wrote the live state file.** Fixed: a dry run writes no
   state and counts no pass.
5. **The examined count was the size of the board, not the number of
   candidates the pass looked at.** Fixed.
6. **The harness was not named.** The proof section names the path and the
   command.

The round also confirmed the parts that were kept: the slot cap, the skip
rule, the pass limits, the ticket CLI's own refusals, the scope (no test or
check changed, no new test file), and that the stubbed proof reproduces the
table above.

## Known limits

- The live start of a past-window ticket is not recorded yet (see above).
- The board state used for the skip is what the board search shows
  (`updatedAt`, title, labels). A ticket whose only change is in a blocker
  it depends on keeps its own `updatedAt`, so it is retried when the refusal
  grows older than `COORDQ_REFILL_RETRY_AGE`, not before.
- The scan order is still oldest first. The night-shift runner
  (`coordinator/overnight/overnight`) owns the ordering (ticket MO-210); the
  refill keeps its own order and only covers more of the board.
- The installed `~/.local/bin/coordq` is the branch head, not a merged
  commit. It is `origin/main` plus the change in this branch.

## Rollback

Revert the commit and reinstall the coordinator.
