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
  next candidate, because a refusal starts nothing.
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

## The scan is bounded

The board holds tickets that `ticket start` refuses (a title without the repo
key, a body naming a blocker that is still open, a ticket that is already
running). The ticket CLI refuses them, the dispatcher skips them and moves
on. A scan tries at most 40 candidates and stops after two minutes, so one
refill cannot hold the dispatcher for long. The rest of the board waits for
the next refill, which is at most five minutes away.

The board's own hygiene is out of scope for this ticket (no relabelling, no
closing), so the dispatcher pays for those refusals on every scan until the
board is cleaned up.

## The proof

`evidence/MO-229/refill-proof.txt` is a hermetic run: a temp `COORDQ_DIR`, a
stub `gh`, a stub `t3mcp` and a stub `ticket`. It shows the empty queue
starting the oldest candidate, a refused candidate being skipped and the
scan continuing, a second run inside the five minutes starting nothing, a
run outside it starting again, a non-empty queue and a full machine starting
nothing, the cap never being crossed and the dry run starting nothing.

`evidence/MO-229/board-dry-run.log` is the same dispatcher against the real
board: the real `tickets.json`, the real `gh`, the real ticket CLI, an empty
queue in a temp folder. The thread count is stubbed at 0 in the second run,
because the machine was really at cap 6/6 at that moment; the first run shows
the real count and the real skip.

## Not touched

The queue, the launch path, every other `coordq` subcommand, the ticket CLI,
the launchd jobs and the tick interval. The tick still runs every 30 minutes.
No existing test or check was weakened, and no test file was added.

## The follow-ups of the reviewer round

PR #221 landed this refill. The reviewer round that read its diff found one
major and eight minor findings. The major one (the scan always started at
the oldest ticket, so the tickets behind the ones the board keeps refusing
never got examined) and the refusal/failure finding were fixed by the
follow-up pulls #247 and #276. The rest are fixed here:

- **A log entry stays one line.** The ticket CLI answers with more than one
  line now and then, and the answer was written into the dispatch log as it
  came, so one refusal could break the log into several lines. The answer is
  put on one line before it is logged or recorded.
- **A timed out start takes its child with it.** The ticket CLI starts the
  queue entry itself, so killing the ticket CLI on a timeout left that
  child running: the ticket could be queued while the dispatcher had given
  up on it. The whole process group is killed now.
- **The dry run path logs a failure instead of raising.** The dry run called
  the refill outside the guard the real path has, so a GitHub timeout ended
  in a traceback instead of a log line.
- **The board search reads every ticket of an owner.** The search took the
  first 200 open stage:todo tickets of an owner and the tickets of the
  configured repos were picked out of that, so a repo could lose its
  tickets when its owner had more than 200 of them. The limit is now the
  1000 the search allows.
- **The stage label is read from the board.** The search index can lag, so a
  ticket that was moved out of `stage:todo` a moment ago could still be
  started. The scan now only takes a ticket whose stage label is the one
  `stage:todo` label, the same one the ticket CLI insists on.

The proof of these is `evidence/MO-229/refill-followup-proof.txt`.
