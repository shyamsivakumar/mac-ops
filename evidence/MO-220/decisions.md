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
      request: the module reads the thread and writes the record.
    - An open decision in the coordinator's own decisions log is parked
      with the open line quoted.
    - The file is written whole, so a decision that is no longer waiting
      leaves it and the morning report never names a decision that is
      gone.
  - **The snag log** holds the problems the shift found and what it did
    about them: a failing check on a pull request, a pending request
    whose text could not be read, and an item the budget stopped. A
    problem the shift finds twice is written once, so the log holds the
    problems and not the cycles.
  - The shift cycle (`overnight shift`) runs the parking step after the
    lane pass, so a cycle parks what it cannot decide and logs what it
    found. A cycle that cannot read the board says so and goes on: a
    record that is missing never ends the shift.
- `coordinator/overnight/README.md`: the contract names the `park`
  command, the two inbox files, what is parked, what is logged, and the
  rule that a pending request is parked with its exact text and never
  answered.
- `evidence/MO-220/prove-park.py`: the proof. It runs the real
  `overnight park` command against a temp records folder and a stub
  `t3mcp` that serves one thread waiting on a person and refuses every
  call but a read.
- `evidence/MO-220/fixture-pending-approval.json`: the fixture thread
  that waits on a person.
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
- Thread: mcp:launch:fixture-mo-220
- Parked at: 2026-11-16 05:32 AM PT
- Default: the request stays unanswered and the item stays parked
- Recommend: answer the request in the morning; the shift never answers one
- Next: Shyam answers the request, and the shift works the item again

The request, quoted exactly as the tool showed it:

```text
Approve running `python3 scripts/mac_ops_fast_check.py` on mac-ops#188 and pushing the result to t3/overnight-decision-parking? [y/N]
```
```

The stub was called for `t3_thread_read` and for nothing else, so the
shift read the request and never answered it. The morning report then
names the decision for Shyam with its recommendation and its default:

```
## Decisions for you (one at a time, each with my recommendation)

1. MO-220 (#188) · Overnight T10: Parking lot and snag log — Recommend: answer the request in the morning; the shift never answers one. Default if you say nothing: the request stays unanswered and the item stays parked
```

The live dry run (`park-live-dry-run.log`) shows the same command on the
real board: nothing is parked today, and one problem is logged
(SRW-1169's builder is over its hard budget).

## Checks

- `python3 scripts/mac_ops_fast_check.py`: passed.
- `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` (the full
  local check): passed.
- `python3 coordinator/overnight/overnight selftest`: all 12 fixture
  evals pass.
- `python3 -m pytest tests/ -q`: 286 pass, 2 fail. Both failures are
  pre-existing on this branch's base and are unrelated to this part:
  `tests/test_gatekeep_retry_limit.py::NonAstraGateTest::test_a_dead_opus_gate_is_not_requeued`
  and `tests/test_install_coordinator.py::TestTickLauncher::test_coord_pi_exports_coord_wake_zero`.
  They fail the same way with this change stashed. No existing test or
  check was weakened.

## Not touched

The merge, push and slot-cap rules, the Ascend rules, the coordq queue,
the launchd jobs, the tick, the merge and close commands, the report
command, and every existing test or check. No secret is written: both
files go through the shift's own redaction before they are written.
