# Event inbox T6: timers table and the 2-hour fallback timer

Part of the coordinator event inbox (design: `docs/coordinator-event-inbox-design.md`, PR #897). Shadow mode only: this ticket changes no behavior of the tick, the guard, t56 or any launchd job.

## Goal and why

Add timers that only enqueue. `enqueue_due_timers` turns due timers into `timer_due` rows (missed periods collapse into one row after a sleep). The `fallback` timer fires only when no run happened for 7,200 seconds, so it never adds a run on a busy day. Nothing starts a run from here.

## Context

- Design: section 3.3 (timers), 3.4 invariant 9, section 4 (fallback).
- The `timers` and `meta` tables come from T1; `last_run` lives in `meta`.

## Scope and non-goals

In:

- `coordinator/bin/inbox.py`: `add_timer(id, *, due_ts, period=None, payload=None)`, `cancel_timer(id)`, `enqueue_due_timers(*, now) -> int`, `set_last_run(*, now)`, `ensure_fallback(*, now)`. Key `timer_due:<id>:<due_ts>`. After firing, a periodic timer's next due is the first multiple of its period after `now`. The `fallback` timer, when due, is pushed to `last_run + 7200` instead of firing if a run happened less than 7,200 s ago.
- Setting `COORD_INBOX_FALLBACK_SECONDS`, default `7200`.
- `coordinator/overnight/selftest.py`: extend the `inbox` eval with the proof.
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: Starting a run, a launchd job, the in-session idle timer, `coord-tick`. Also out: any plist or job load, any model call, any send, `coordinator/pi/bin/coord-tick`, `coordinator/pi/extensions/coordinator.ts`, the live session t56, the live queue, the real journal and `~/.coordinator`.

## Design fit

Requires: T1's `enqueue`, `meta` and `timers` table. This ticket never claims, so it does not use `claim`, `ack(rows, *, now)` or `release(rows, *, count_attempt)` or the claim token; `enqueue_due_timers` only calls `enqueue`.
Provides: The fallback row T9's pass reads.

## Blocked by

T1 (replace with the issue number once filed).

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main (with the blockers merged) and green on the head, and the `inbox` eval of `coordinator/overnight/selftest.py` named as the case that fails on origin/main and passes on the branch.
3. The proof:

```text
Proof command:
HOME=/nonexistent python3 -c "import os,sys,tempfile;os.environ['COORD_INBOX_DIR']=tempfile.mkdtemp();sys.path.insert(0,'coordinator/bin');import inbox;inbox.add_timer('t1',due_ts=100.0,period=50.0);assert inbox.enqueue_due_timers(now=120.0)==1,'due';assert inbox.enqueue_due_timers(now=121.0)==0,'again';assert inbox.enqueue_due_timers(now=1000.0)==1,'collapse';inbox.cancel_timer('t1');inbox.set_last_run(now=1000.0);inbox.ensure_fallback(now=1000.0);assert inbox.enqueue_due_timers(now=4600.0)==0;inbox.set_last_run(now=8000.0);assert inbox.enqueue_due_timers(now=8300.0)==0,'busy';assert inbox.enqueue_due_timers(now=15300.0)==1,'fallback'"
Expected red signature: AttributeError: module 'inbox' has no attribute 'add_timer'
Expected on main: AttributeError
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- A timer that starts anything.
- A fallback row while a run happened in the last 7,200 seconds.
- A model call, a send, a job load, or a change to the tick, the guard or t56.
- No new plist under `coordinator/launchd` (the installer loads every plist there), no weakening of an existing test and no new test file.

## CI

No workflows and no GitHub Actions, ever. The local check is `scripts/mac_ops_fast_check.py`.

## Data/secrets and stop conditions

Never read or print `models.json` or any API key. Never run `coordq dispatch`, refill, `ticket start/close` or the lane. Use a temp `COORD_INBOX_DIR` and `COORD_JOURNAL_DIR` for every run. Stop and report if over 3 code files or about 150 code lines.

## Rollback

Revert the merge commit.

## Gate

Astra gate on the PR head. Loop-code hold applies; Shyam merges after PASS.

## Finish

Report the PR, the head and the check line.
