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

### The follow-up fixes (after the reviewer and the gate)

- **A refusal is told from a failed check by its output, not by the exit
  code.** The ticket CLI exits 2 for a refusal and for a usage error, and
  exits 1 for a missing or unknown issue, so the exit code alone cannot say
  which one happened. The fix is on the `coordq` side, because the ticket
  CLI is out of scope for this ticket: `is_refusal()` treats exit 2 as a
  refusal only when a line of the output starts with `refused:`, which is
  the ticket CLI's own refusal message. Anything else is a failed check:
  it is logged as `refill could not check` and is not recorded, so the next
  pass tries the ticket again instead of hiding it for the retry age.
- **A dry run writes nothing.** `refill --dry-run` no longer adds a pass to
  the count and no longer writes the state file, so a diagnostic cannot hide
  a ticket from the next real pass.
- **The examined count is the real one.** The pass line reports the number
  of candidates the pass actually looked at, not the size of the board.
- **The `ticket_start` docstring matches the code**, and says why the exit
  code cannot be read on its own.

## The board, read live

`gh search issues` over the repos in `~/.coordinator/tickets.json` returned
92 open `stage:todo` candidates when the proof run read it at
2026-11-13 17:37:17 PST. The old window was the first 40 of them.

## Proof

### The live board: the refill started a ticket from past the old window

The real refill ran against the live board and the live coordinator queue
directory (`~/Code/coordinator/queue`), from the branch copy of
`coordinator/bin/coordq` at commit `821d75b` (the head that carries the
refusal-contract fix, and the code that produced the quoted lines), and the
log lines are in `~/Code/coordinator/queue/dispatch.log`:

```
2026-11-13 17:37:36 refill started shyamsivakumar/strategy-replay-workbench#899
2026-11-13 17:38:02 refill started shyamsivakumar/strategy-replay-workbench#924
2026-11-13 17:38:24 refill stopped: the slots are full (6/6)
2026-11-13 17:38:24 refill pass 5: examined 60 candidate(s) of 92, skipped 43 unchanged refusal(s), attempted 17, started 3
```

**`shyamsivakumar/strategy-replay-workbench#899` was at position 44 of the 92
candidates**, in the board order read at 17:37:17, one minute before the
refill started it. It is outside the old first-40 window, so the old code
could never have reached it.

The pass skipped 43 candidates whose refusal was still on file and whose
board state had not changed, and it examined 60 of the 92 candidates, so it
walked past the whole front of the board and into the part the old window
cut off. The ticket CLI accepted #899 (the ticket CLI decides every start,
and it accepted this one).

Live pass count: **5**. Live skipped-refusal count in the last pass: **43**.
The live state file (`~/Code/coordinator/queue/refill-state.json`) holds the
same numbers and 57 refusal records:

```json
{"passes": 5, "last_pass": {"pass": 5, "examined": 60, "skipped": 43, "attempted": 17, "started": 3}}
```

### The scan reaches past the window, without the live board

The real `refill()` was also driven against a 60 candidate board (candidates
1 to 40 refused by the ticket CLI with exit 2, 41 and up accepted) with the
real code, the real lock, the real state file and the real log. The harness
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

Pass 2 skipped the 40 candidates refused in pass 1 and started candidate 41,
which the old `candidates[:REFILL_MAX]` window could never reach. Pass 4
shows that a candidate whose board state changed is attempted again even
though its last refusal is still on file.

## Checks

- `python3 scripts/mac_ops_fast_check.py` passed.
- `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` passed.
- The head sha and the check result are in the pull request body.

## The installed coordinator

The installed `~/.local/bin/coordq` on this Mac carries pull request #251
head `6343bdef`, which has the gate backstop and the gate subcommand. This
branch changes the same file, so after both pull requests merge the
installer must run once from `main` so the installed file matches the merged
code. The installer was not run for this ticket.

The live proof above did not depend on the installed file: it ran the branch
copy of `coordinator/bin/coordq` directly against the live queue directory,
so the quoted `refill pass 5` line comes from this branch's head
(`821d75b`), not from the installed binary and not from the old code (the
old code writes `refill scanned N candidate(s)`, a line that is not in that
log segment).

## The reviewer round and the gate

The in-session Opus 5.5 round read `git diff origin/main...HEAD` and
returned `VERDICT: FAIL`. Its findings and the fixes:

1. **The live proof was missing and the evidence was out of date.** The
   evidence now carries the live pass count and the skipped count that
   `refill-state.json` holds, the live board reading with its timestamp, and
   the live pass line from `dispatch.log`.
2. **A builder loop was left running.** The loop
   (`$TMPDIR/mo238/loop.sh`) that drove the refill every two seconds with
   the throttle off was stopped. The proof run above is a bounded script
   that stops when the proof lands.
3. **A failed check was stored as a refusal.** Fixed on the `coordq` side,
   with the rule written down under "The follow-up fixes" above.
4. **A dry run wrote the live state file.** Fixed: a dry run writes no
   state and counts no pass.
5. **The examined count was the size of the board, not the number of
   candidates the pass looked at.** Fixed.
6. **The harness was not named.** The proof section names the path and the
   command.

The coordinator's gate then read the branch at `94bef35` and returned
`VERDICT: FAIL` with two majors and two minors:

1. **The live proof was still missing.** Fixed: the live pass above started
   `strategy-replay-workbench#899` from position 44, outside the old
   window.
2. **The quoted live pass line came from the code before the fixes.** Fixed:
   the quoted line is `refill pass 5`, which only the head code writes, and
   it is the pass that started #899.
3. **The exit code cannot tell a refusal from a failed check.** Fixed on the
   `coordq` side: `is_refusal()` reads `refused:` out of the output. The
   ticket CLI was not touched, because it is out of scope for this ticket.
4. **The `ticket_start` docstring did not match the code.** Fixed, and the
   comment on `REFUSE_CODE` now states the real contract: a refusal and a
   usage error both exit 2, a missing or unknown issue exits 1.
5. **The Builder check line named an older head.** The pull request body
   names the head the check ran on, and this file records the same head.

## Known limits

- The board moves while a proof runs: it had 120 candidates at 16:45, 112
  at 16:58 and 92 at 17:37, because finished work leaves the board. A
  position is therefore a reading of a moment, and the proof records the
  time of that reading.
- The board state used for the skip is what the board search shows
  (`updatedAt`, title, labels). A ticket whose only change is in a blocker
  it depends on keeps its own `updatedAt`, so it is retried when the refusal
  grows older than `COORDQ_REFILL_RETRY_AGE`, not before.
- The scan order is still oldest first. The night-shift runner
  (`coordinator/overnight/overnight`) owns the ordering (ticket MO-210); the
  refill keeps its own order and only covers more of the board.
- `~/.local/bin/coordq` is the branch head, not a merged commit, and
  another in-flight worktree installs into the same path, so the installed
  binary can be either until this merges. The proof run above used the
  branch copy directly, so the line it wrote comes from this head.
- The proof reads the board with the same `gh search` call the refill uses,
  and one of those reads hit the GitHub search rate limit once
  (`HTTP 403 ... rate limit exceeded`) while the proof ran. The refill
  itself makes one search per owner per pass, the same as before this
  change, so the change adds no API rate of its own.

## Rollback

Revert the commit and reinstall the coordinator.
