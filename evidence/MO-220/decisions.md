# MO-220 decisions

Overnight runner spec part T10: the parking lot and the snag log. The
shift parks the decisions it cannot make, each with a default and a
recommendation, logs the problems it found, and never answers a pending
approval request.

Run id: `ticket:shyamsivakumar/mac-ops#188:a1`. Refs #188.

## What landed

- `coordinator/overnight/overnight`: one new part in the same module as
  every other part of the shift (T10).
  - A new `park` subcommand: `overnight park`.
    - It reads the board (GitHub), the queue's own records (coordq) and
      the threads that hold the work (T3), so it keeps no second queue of
      its own.
    - It writes `inbox/parking-lot.md` and `inbox/snag-log.md` under the
      shift's records folder, and it writes a `park` line to the shift
      log.
    - `--dry-run` prints both files and writes none. `--fixture` parks the
      pending request of one fixture thread, which is how the rule is
      proved without a live approval dialog.
  - **The parking lot** holds the decisions the shift could not make, one
    section per item, each with a `Default:` line (what happens when
    Shyam says nothing) and a `Recommend:` line.
    - A pending approval request on a thread that holds the work is
      parked with its exact text, quoted as the tool showed it, and the
      request is never answered. The shift has no call that answers a
      request: the module reads the thread and writes the record. The
      request that is parked is the last one the thread holds that is
      still open, so a question that was already answered is never parked
      as if it waited for an answer.
    - An open decision in the coordinator's own decisions log is parked
      with the open line quoted, and so is a ticket the filter drops for
      a decision (marked needs Shyam, marked design needed, an open item
      or a hold in the decisions log). A ticket dropped as Ascend work, or
      as being off the allow list, is not a decision and is never parked.
    - The file is written whole, so a decision that is no longer waiting
      leaves it and the morning report never names a decision that is
      gone. A decision that is still waiting keeps the time it was first
      parked.
  - **The snag log** holds the problems the shift found and what it did
    about them: a failing check on a pull request, a pending request
    whose text could not be read, an item the budget stopped, and a thread
    that could not be read. A problem the shift finds twice is written
    once, so the log holds the problems and not the cycles.
  - The shift cycle (`overnight shift`) runs the parking step after the
    lane pass, so a cycle parks what it cannot decide and logs what it
    found. Nothing in that step raises out of the cycle: a parking
    problem never takes the morning report with it.
  - `parse_parking_lot` reads the fences now, so a quoted request that
    holds a heading or a `Default:` line cannot change the decision it is
    quoted in.
- `coordinator/overnight/README.md`: the contract names the `park`
  command, the two inbox files, what is parked, what is logged, and the
  rules that keep the records honest.
- `evidence/MO-220/prove-park.py`: the proof. It runs the real
  `overnight park` command against temp records folders, a stub `t3mcp`
  that serves the threads it is given and refuses every call but a read,
  and the live board (read only).
- `evidence/MO-220/fixtures/`: the fixture threads and the fixture
  requests.
- `evidence/MO-220/park-fixture.log`: the proof's output.
- `evidence/MO-220/park-live-dry-run.log`: the same command on the live
  board, read only.
- `evidence/MO-220/decisions.md`: this file.

## The proof

The acceptance is a fixture pending request parked, not answered. The
entry the proof writes, from `evidence/MO-220/park-fixture.log`:

```
## MO-220 (#188) · Overnight T10: Parking lot and snag log

- Repo: shyamsivakumar/mac-ops
- Ticket: MO-220
- Kind: pending approval request
- Thread: mcp:launch:t10-answered
- Parked at: 2026-11-16 05:42 AM PT
- Default: the request stays unanswered and the item stays parked
- Recommend: answer the request in the morning; the shift never answers one
- Next: Shyam answers the request, and the shift works the item again

The request, quoted exactly as the tool showed it:

```text
Approve running `python3 scripts/mac_ops_fast_check.py`?
```
```

The stub was called for `t3_thread_read` and for nothing else, so the
shift read the request and never answered it. The proof also shows:

1. and 2. the answered question that sits before the pending approval
   is not parked, and the pending approval is;
3. a pending request whose text cannot be read is still parked, and the
   problem is logged;
4. a quoted request that holds markdown does not break the morning
   report: the report names one decision with its own default and its own
   recommendation;
5. a thread that cannot be read leaves the parking lot as it was, exits
   non-zero, and logs the failure;
6. a problem that is still there is written once, not once a cycle;
7. a ticket the filter drops for an open question in the coordinator's
   decisions log is parked with its default and its recommendation.

The morning report then names the decision for Shyam:

```
## Decisions for you (one at a time, each with my recommendation)

1. MO-222 (#190) · Overnight T10: a request that holds markdown — Recommend: answer the request in the morning; the shift never answers one. Default if you say nothing: the request stays unanswered and the item stays parked
```

The live dry run (`park-live-dry-run.log`) shows the same command on the
real board: nothing is parked today, and the problems the shift found
(items whose builder is over its hard budget) are logged.

## The gate round (PR #435, VERDICT: FAIL at 3055473)

The gate on the first head of this PR found two major defects and marked
the earlier answer-payload finding as partly unresolved. All three are
fixed here.

1. **Major, the duplicate `park_cycle`.** The module held two
   `park_cycle` definitions. The second one overrode the corrected one
   and rethrew `SystemExit`, so a parking step that raised `SystemExit`
   ended the shift cycle before its morning report. The duplicate is
   removed and the module now holds exactly one. The proof counts the
   definitions in the module's own source and drives the one definition
   with a `cmd_park` that raises `SystemExit`: the cycle ends without
   the exception.
2. **Major, the fence of a quoted request.** The parser toggled on every
   triple-backtick line, so a request that carries a fence of its own
   let the lines after it out of the fence: a quoted `Default:`,
   `Recommend:` or heading became a field of the decision and the
   morning report was corrupted. The fence that quotes a request is now
   longer than any fence inside it (`code_fence`), and the parser closes
   a fence only on the exact delimiter that opened it (`parse_parking_lot`).
   The proof parks a request that carries its own fence and shows that
   the report still names one decision with its own default and its own
   recommendation.
3. **Answered requests (the earlier finding, partly resolved).** An
   item that carries the answer itself, with no flag and no status that
   says so, was parked as if it waited for an answer. `carries_answer`
   now reads the answer payload (`answer`, `answerText`, `answerPayload`,
   `answeredText`, `response`, `reply`, `resolution`), and a thread that
   holds nothing but answered requests waits for nobody, so nothing is
   parked. The proof parks a request that carries its answer and shows
   that the shift parks nothing and says why.

Device, handset and live-service testing is waived (Shyam, 2026-11-14).
No device or live case was run, so none failed.

## The second gate round (PR #435, VERDICT: FAIL at d54695d)

The gate on the second head found two major defects. Both are fixed here.

1. **The latest request could be the wrong one.** When the last open
   request of a thread had no readable text, the search fell back to an
   older open request, so the parking lot presented a request nobody
   waits for and the unreadable request was never logged. The latest open
   request is now selected first and its own text is what is parked: when
   that text cannot be read, the entry says so and the snag log holds the
   problem. The proof parks a thread whose latest request has no text and
   shows that the older request is not parked in its place.
2. **Two tickets with the same title collided in the snag log.** The
   identity of a problem was the title's suffix and the problem, so two
   tickets with the same title and the same failing check were one
   problem and one of them was silently dropped. The identity now holds
   the repository, the ticket, the item's number and the problem, in both
   the generation and the parsing. The proof parks two tickets that share
   a title and shows that the log keeps both.
3. **The stopping wording (the earlier partly-resolved finding).** The
   budget snag still copied the rule's wording, which said the item "was
   stopped and parked". The problem line now holds what was observed (the
   builder's own time and the queue's own count of fix tries) and the
   entry quotes the shift's own receipt when there is one, so the record
   says what was recorded instead of what it assumes.

Device, handset and live-service testing is waived (Shyam, 2026-11-14).
No device or live case was run, so none failed.

## The third gate round (PR #435, VERDICT: FAIL at 3a251b1)

The gate found one major defect: `park --dry-run` returned success before
the incomplete-read check, so a failed thread read made the preview hide
a pending decision and call itself complete.

The incomplete read is handled before the dry-run return now. Both modes
say the same thing: the preview prints an `INCOMPLETE` line on stderr
before the parking lot, the snag log holds the failed read, and the
command exits non-zero without writing a file. A preview that hides a
decision and calls itself complete is the same failure as a write that
erases one, so it is refused the same way. The fixture path refuses a
dry run the same way and writes nothing. The proof's case 15 runs the
board path with a T3 stub that fails every thread read and shows the
`INCOMPLETE` line, the snag entry, the refusal and exit 1, with no file
written.

Device, handset and live-service testing is waived (Shyam, 2026-11-14).
No device or live case was run, so none failed.

## The fourth gate round (PR #435, VERDICT: FAIL at 4418dd2)

The gate found one major defect and one stale document line.

1. **The receipt lookup used the pull request's number before the linked
   issue's.** A pull request has two numbers, and its own number is not
   its ticket's: pull request #435 belongs to issue #188, so a receipt
   filed under #435 belongs to some other ticket. The snag entry looked
   up both numbers and took whichever it found first, so it could quote
   an unrelated ticket's state and stopping reason.
   `receipt_number` now returns the ticket's number and nothing else: the
   linked issue for a pull request, the item's own number for a ticket,
   and no number at all for a pull request with no linked ticket. The
   proof's case 16 files receipts under both numbers and shows that the
   entry quotes the linked ticket's receipt, never the other one, and
   that a pull request with no linked ticket quotes nothing and says the
   action was not verified.
2. **The README still claimed the log holds a stop.** The log line said
   the shift "stopped the item and spent no further fix try on it". It
   now says the shift's budget rule held the item back, records the
   observation, and never states that the item was stopped. The README
   also names the receipt rule now: an entry that names an action quotes
   the shift's own receipt, looked up by the ticket's number.

Device, handset and live-service testing is waived (Shyam, 2026-11-14).
No device or live case was run, so none failed.

## The fifth gate round (PR #435, VERDICT: FAIL at f80e0be)

The gate found one major defect: the thread lookup still read the
receipts under both the linked issue's number and the pull request's own
number. Pull request #435 linked to issue #188 could therefore pick up
the threads of an unrelated ticket #435, and park that ticket's pending
approval under #188.

`item_threads` reads two sources and only two now: the threads the board
attaches to the item, taken as they are, and the queue's dispatch
receipts looked up by the **ticket's** number alone (`receipt_number`).
A pull request with no linked ticket contributes no receipt thread at
all. The proof's case 17 files a builder receipt under an unrelated
ticket #435 and shows that the pull request linked to #188 borrows
nothing, parks no decision, keeps the board's own attached thread, and
still finds its linked ticket's builder when that receipt exists.

Device, handset and live-service testing is waived (Shyam, 2026-11-14).
No device or live case was run, so none failed.

## The merge with main (PR #435 conflicted at 0b7d428)

While this part was open, main took the cycle health check (T14,
`dev.coordinator.tick` retirement work) and stall detection (T8b). The
merge conflict was one hunk in `coordinator/overnight/overnight`, where
both sides inserted their own section at the same place.

The resolution keeps both parts whole and puts them in the order the
cycle runs them:

- main's cycle health check (`health_deadline`, `cycle_health`) runs at
  the start of the cycle, as main wrote it;
- the lane pass keeps main's stall records (`STALL_STATE`,
  `stall_records`, `save_stall_state`) and the `STALL_EVENTS` loop;
- the T10 parking step runs after the lane pass, inside the same lock,
  and takes its deadline from the cycle's remaining time (`left`), so it
  cannot outlive the cycle.

`README.md` merged without a conflict and holds both sections. The
selftest now runs fourteen fixture evals: main's twelve plus
`cycle-health` and `stall`, and all fourteen pass. Nothing in this
resolution changes the T10 behaviour: the live dry run and the proof are
re-captured on the merged tree.

Device, handset and live-service testing is waived (Shyam, 2026-11-14).
No device or live case was run, so none failed.

## The reviewer round

One in-session reviewer round ran over the diff (`gpt-6.1-sol`, high
effort). It found eight defects, all fixed in this branch:

1. the builder of a pull request was looked up by the pull request's
   number, so a pull request's builder was missed. The board's own
   builder and gate threads are read first, and the receipts are looked
   up by the linked ticket's number.
2. the tickets with an open question in the decisions log are dropped by
   the filter, so the parking lot never held them. The drops come with
   the items now, and the decisions among them are parked.
3. the quoted request could be an old, answered question. The last open
   request is the one that is parked, and a request that carries an
   answer is skipped.
4. a failed read could empty the parking lot. A thread that cannot be
   read leaves the file as it is, exits non-zero and logs the failure.
5. a parking failure could terminate the shift cycle. The parking step
   catches what it raises, so the morning report is still written.
6. a quoted request could corrupt the morning report. The parser reads
   the fences now.
7. a failed write reported success. A failed write is reported, exits
   non-zero and is recorded in the shift log.
8. a problem that was still there was written again every cycle. The
   identity of a problem is the item and the problem, not the time.

## Checks

- `python3 scripts/mac_ops_fast_check.py`: passed on the merged head
  (`evidence/MO-220/fast-check.log`).
- `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` (the full
  local check): passed.
- `python3 coordinator/overnight/overnight selftest`: all 12 fixture
  evals pass.
- `python3 evidence/MO-220/prove-park.py`: passed (seventeen cases,
  including every case the five gate rounds found).
- `python3 -m pytest tests/ -q`: 286 pass, 2 fail. Both failures are
  pre-existing on this branch's base and are unrelated to this part:
  `tests/test_gatekeep_retry_limit.py::NonAstraGateTest::test_a_dead_opus_gate_is_not_requeued`
  and `tests/test_install_coordinator.py::TestTickLauncher::test_coord_pi_exports_coord_wake_zero`.
  They fail the same way with this change stashed. No existing test or
  check was weakened.

## Not touched

The merge, push and slot-cap rules, the Ascend rules, the coordq queue,
the launchd jobs, the tick, the merge and close commands, and every
existing test or check. No secret is written: both files go through the
shift's own redaction before they are written.

## Fix round 2

Reject empty or malformed thread records before parking aggregation. An unreadable
thread marks the read incomplete and preserves the existing parking lot. Snags
report observed check failures and budget thresholds; delivery and stopping are
explicitly unverified. Both corrections agree with #188's reporting scope.

In-session reviewer round: inspected the boundary, preservation path, and changed
report strings. No remaining critical or major finding in this diff. A direct
probe rejected empty objects, empty thread objects, list thread values, and
non-string statuses. No existing tests were changed. Diff comment review: no new
comments. Deslop review: no further cleanup needed. Live actions were not run.

## Fix round 3

Refs #188. Select the latest open request before extracting text, so an
unreadable latest request produces a snag instead of quoting an older one.
Snag parsing and generation share repository, ticket, item number and problem
identity. Budget problems describe observed time and retry counts; receipt
claims are explicitly attributed to the receipt.

The real-command parking proof passed, including unreadable latest requests,
distinct-ticket snag identity and budget reporting. Direct and heavy-wrapped
`python3 scripts/mac_ops_fast_check.py` passed. No operational stop or delivery
was attempted. Existing checks were preserved. The diff cleanup review found
no separate cleanup needed.

## Finish verification, 2026-11-16

The inherited merge completed at 66e7579 while verification was running.
The in-session review found that the merged parking call restarted the remaining
cycle budget after the lane pass. It now uses the original cycle deadline.
No existing tests or checks were changed. Comment review added no comments;
bounded cleanup found no further change needed.

Earlier check receipts refer to earlier revisions and do not prove this head.
Current direct and heavy repository check results are recorded in the PR body.

### Left for later

Authenticated live approval behavior and deployment remain unverified. The
full pytest suite was not rerun; the repository check selects its own checks.
