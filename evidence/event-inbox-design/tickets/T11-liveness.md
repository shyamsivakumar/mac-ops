# Event inbox T11: worker heartbeat, pass alarm and watchdog check

Part of the coordinator event inbox (design: `docs/coordinator-event-inbox-design.md`, PR #897). Shadow mode only: this ticket changes no behavior of the tick, the guard, t56 or any launchd job.

## Goal and why

Make worker liveness judged one way at a time. While the worker lock is held, the watchdog looks at heartbeat age only (alarm above 4 minutes), because a pass may legally run 10 minutes. While the lock is free it looks at pass age only (alarm above 5 minutes), and only when `COORD_INBOX_EXPECT_PASSES` is on (default off in shadow, where passes are run by hand). A free lock with no heartbeat file means the worker never ran and raises nothing. The worker touches the heartbeat every 30 seconds and bounds a pass with a 20-minute `SIGALRM`.

## Context

- Design: section 3.4 invariant 12. `lane_driver.py` already raises `factory-watchdog` and its job runs every 180 seconds (`coordinator/launchd/dev.coordinator.lanes.plist`, `StartInterval` 180), so worst case detection is about 7 minutes.
- A model run is killed at 600 seconds (`coord-tick` line 46), so a healthy pass ends within about 11 minutes.
- With no worker files present the check is a no-op, so installing it changes nothing until the worker runs.

## Scope and non-goals

In:

- `coordinator/bin/inbox_worker.py`: `heartbeat(*, now)` (writes `inbox.worker.heartbeat` in `COORD_INBOX_DIR`), a 30-second timer thread for the pass, a 20-minute `SIGALRM`, and the pure function `liveness(*, now, lock_held, heartbeat, last_pass_end, expect_passes) -> str | None`.
- `coordinator/overnight/lane_driver.py`: call `liveness` in the existing watchdog pass and raise the existing `factory-watchdog` alarm once per episode.
- Setting `COORD_INBOX_EXPECT_PASSES`, default `0`.
- `coordinator/overnight/selftest.py`: extend the `inbox` eval with a temp state dir holding a stale heartbeat and a held lock (one alarm), a fresh heartbeat (none), and a pass that sleeps past the alarm (killed, lock released).
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: The hourly selftest as the alarm path, any plist, `coord-tick`, `coordinator.ts`, any change to the other lane-driver checks. Also out: any plist or job load, any model call, any send, `coordinator/pi/bin/coord-tick`, `coordinator/pi/extensions/coordinator.ts`, the live session t56, the live queue, the real journal and `~/.coordinator`.

## Design fit

Requires: T9.
Provides: A worker that cannot hide a wedge.

## Blocked by

T9 (replace with the issue number once filed).

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main (with the blockers merged) and green on the head, and the `inbox` eval of `coordinator/overnight/selftest.py` named as the case that fails on origin/main and passes on the branch.
3. The proof:

```text
Proof command:
HOME=/nonexistent python3 -c "import sys;sys.path.insert(0,'coordinator/bin');import inbox_worker as w;L=lambda **k:w.liveness(**{**dict(now=1000.0,lock_held=True,heartbeat=900.0,last_pass_end=0.0,expect_passes=False),**k});assert L(heartbeat=800.0) is None,'held: pass age ignored';assert L(heartbeat=700.0),'stale heartbeat';assert L(lock_held=False,last_pass_end=600.0) is None,'shadow';assert L(lock_held=False,last_pass_end=600.0,expect_passes=True),'pass age';assert L(lock_held=False,heartbeat=None,last_pass_end=None,expect_passes=True) is None,'never ran'"
Expected red signature: AttributeError: module 'inbox_worker' has no attribute 'liveness'
Expected on main: AttributeError
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- An alarm during a legal 10-minute run.
- An alarm when no worker has ever run.
- A repeat alarm for the same episode.
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
