# MO-229 decisions

Refs #208. Ticket: https://github.com/shyamsivakumar/mac-ops/issues/208
Run id: `ticket:shyamsivakumar/mac-ops#208:a2`

## What landed

`coordinator/bin/coordq` only. The dispatcher (`coordq dispatch`, the job
`dev.coordinator.dispatch` runs every 30 s) now refills the board when the
machine has free slots.

- **The refill sits inside the dispatcher loop.** `cmd_dispatch` drains the
  queue as before and then calls `refill`. The refill runs after the queue
  lock is released, so the ticket CLI it calls can take that lock itself
  without deadlocking against the dispatcher.
- **The refill calls the existing ticket CLI.** It runs `ticket start` on the
  open `stage:todo` issues of the repos in `tickets.json`, oldest first. It
  starts nothing of its own: no relabelling, no closing, no other kind of
  start. The ticket CLI stays the only authority on whether a ticket may
  start.
- **It runs only when the queue is empty and the live count is below the
  cap**, and at most once per five minutes. The window is a stamp in the
  queue folder (`refill.last`), not a timer in memory, so a restart cannot
  turn the five minutes into five seconds.
- **One log line per start**, in the dispatch log the dispatcher already
  writes: `refill started owner/repo#number`. A refused ticket gets its own
  line (`refill refused owner/repo#number: ...`) and the scan moves on to the
  next candidate, because a refusal starts nothing. A failed start (a gh
  failure, a timeout) is a different line, `refill failed`.
- **`coordq dispatch --dry-run` starts nothing.** It leaves the queue alone
  and runs the scan with `ticket start --dry-run`, so the operator can see
  what the dispatcher would start without starting it.

## The cap is never crossed

The queue already refuses to launch above the cap, and the refill keeps the
same count: it reads the live threads the same way the queue does, and it
counts the slots its own starts took, because the live count can lag behind
a launch. The refill stops when the live threads plus the queued items plus
the slots it filled reach the cap. The proof shows the case: four live
threads and a cap of six leave two starts, and the scan stops there.

## The scan carries on where it stopped

The board holds tickets that `ticket start` refuses: a title without the repo
key, a body naming a blocker that is still open, a ticket that is already
running. The ticket CLI refuses them, the dispatcher skips them and moves
on.

A scan that always started at the oldest ticket would never reach the
tickets behind that pile, so the scan keeps a cursor (`refill.cursor` in the
queue folder): it starts at the ticket after the one the last scan stopped
at, and wraps to the oldest ticket when it reaches the end of the board. The
order inside a scan is still oldest first, and the cursor makes sure every
ticket on the board is examined once per pass instead of the same forty
tickets every five minutes.

A ticket the board refused waits for the next pass, which is a few refills
away, unless the thirty minute tick starts it first.

A scan tries at most 40 candidates and stops after two minutes, so one
refill cannot hold the dispatcher for long.

The board's own hygiene is out of scope for this ticket (no relabelling, no
closing), so the dispatcher pays for those refusals on every pass until the
board is cleaned up.

## The proof

`evidence/MO-229/refill-proof.txt` is a hermetic run: a temp `COORDQ_DIR`, a
stub `gh`, a stub `t3mcp` and a stub `ticket`. It shows the empty queue
starting the oldest candidate, a refused candidate being skipped and the
scan continuing, a second run inside the five minutes starting nothing, a
run outside it starting again, a non-empty queue and a full machine starting
nothing, the cap never being crossed, the dry run starting nothing and the
scan continuing after the ticket the last scan stopped at.

`evidence/MO-229/board-dry-run.log` is the same dispatcher against the real
board: the real `tickets.json`, the real `gh`, the real ticket CLI, an empty
queue in a temp folder. It shows the empty queue scanning the real board,
the non-empty queue being skipped and the second run inside the five
minutes being skipped. The thread count is stubbed at 0 in those runs,
because the machine was really at cap 6/6 at that moment; the first run
shows the real count and the real skip.

## Not touched

The queue, the launch path, every other `coordq` subcommand, the ticket CLI,
the launchd jobs and the tick interval. The tick still runs every 30 minutes.
No existing test or check was weakened, and no test file was added.
