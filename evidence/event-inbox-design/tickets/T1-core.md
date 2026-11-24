# Event inbox T1: inbox.db tables, enqueue with dedupe, claim, ack, reap

Part of the coordinator event inbox (design: `docs/coordinator-event-inbox-design.md`, PR #897). Shadow mode only: this ticket changes no behavior of the tick, the guard, t56 or any launchd job.

## Goal and why

Add the durable inbox store the design calls for, with no producer and no consumer yet. One SQLite file holds every table the later tickets need (`inbox`, `seen`, `meta`, `timers`, `outbox`), so no later ticket adds DDL. `enqueue` dedupes on a unique key, `claim` hands out pending rows under a lease, `reap` returns expired claims to pending (to `failed` after 3 claims), and `ack` and `release` end a claim. Nothing calls it yet, so no live behavior changes.

## Context

- Design: `docs/coordinator-event-inbox-design.md` sections 3.2 (row schema), 3.4 (lifecycle and invariants 1 to 5, 8, 11).
- `coordinator/bin/journal.py` is the pattern for the state directory and its override: `COORD_JOURNAL_DIR` there, `COORD_INBOX_DIR` here, default `~/.local/state/coordinator`.
- `coordinator/bin/hourly_selftest.py` `EXPECTED` lists every eval name in `coordinator/overnight/selftest.py` `EVALS`; a new eval must be added to both.

## Scope and non-goals

In:

- `coordinator/bin/inbox.py` (new): `connect()`, `enqueue(kind, key, *, source, ts, session="coordinator", repo=None, pr=None, head=None, payload=None, tier=None) -> bool`, `claim(session, *, worker, now, lease=900, limit=50, pid=None) -> list[dict]` (payload decoded to a dict), `ack(rows, *, now) -> int`, `release(rows, *, count_attempt) -> int`, `reap(*, now) -> int`, `counts() -> dict`.
- Claim token: each `claim` call stores a fresh `uuid4().hex` in `run_id` and returns it on every row. `ack` and `release` take the claimed rows and update only `id=? AND run_id=? AND status='claimed'`, returning how many rows changed, so a late call from a reaped claim changes nothing. `attempts` cannot be the token, because `release(count_attempt=False)` lowers it. `reap` and `release` clear `run_id`.
- Closed set `KINDS`: `pr_opened`, `pr_new_head`, `pr_merged`, `pr_review`, `gate_verdict`, `gate_queued`, `ci_main`, `human_signal`, `timer_due`, `alarm`, `round_cap`, `merge_held`, `close_failed`, `launch_failed`, `recut`. `enqueue` raises `ValueError` for any other kind.
- Setting `COORD_INBOX_WAKE_KINDS`, default `alarm,round_cap,merge_held,close_failed,launch_failed,recut,human_signal,timer_due` (the design's variant B, Shyam's open question 2). `enqueue` sets the `tier` column to `wake` for a kind in the setting and `batch` otherwise, unless `tier` is passed.
- Schema `PRAGMA user_version = 1`, WAL mode. `inbox` has the design's columns plus `tier` and `claimed_pid`; `seen(key, ts)` with no expiry; `meta(k, v)`; `timers(id, due_ts, period, payload)`; `outbox` with the design's columns. `enqueue` also writes the key to `seen`, and a key already in `seen` is ignored.
- `reap` returns a claimed row to `pending` when its lease is past due and its `claimed_pid` is gone (`os.kill(pid, 0)`) or the lease is more than 3600 s past due; a row with 3 attempts goes to `failed` instead. A row whose lease is past due but whose pid is alive and within the hour is left alone.
- `coordinator/overnight/selftest.py`: add one eval `inbox` to `EVALS`; `coordinator/bin/hourly_selftest.py`: add `inbox` to `EXPECTED`. The eval covers the proof below plus `release(count_attempt=False)` and the closed kind set.
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: A producer, a worker, an outbox dispatcher, any plist, the journal hook, `coord-tick`, `coordinator.ts`, `inbox.db` at the real HOME (the proof and the eval use a temp `COORD_INBOX_DIR`). Also out: any plist or job load, any model call, any send, `coordinator/pi/bin/coord-tick`, `coordinator/pi/extensions/coordinator.ts`, the live session t56, the live queue, the real journal and `~/.coordinator`.

## Design fit

Requires: Nothing new.
Provides: The store every later ticket reads and writes.

## Blocked by

None.

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main (with the blockers merged) and green on the head, and the `inbox` eval of `coordinator/overnight/selftest.py` named as the case that fails on origin/main and passes on the branch.
3. The proof:

```text
Proof command:
HOME=/nonexistent python3 -c "import os,sys,tempfile;os.environ['COORD_INBOX_DIR']=tempfile.mkdtemp();sys.path.insert(0,'coordinator/bin');import inbox;k=dict(source='journal',ts=1.0);assert inbox.enqueue('pr_merged','pr_merged:a#1:',**k) and not inbox.enqueue('pr_merged','pr_merged:a#1:',**k),'dedupe';r=inbox.claim('coordinator',worker='w1',now=100.0,lease=10,pid=4194303);assert len(r)==1 and r[0]['attempts']==1,'claim';assert inbox.reap(now=105.0)==0,'early';assert inbox.reap(now=111.0)==1,'reap';[(inbox.claim('coordinator',worker='w',now=t,lease=10,pid=4194303),inbox.reap(now=t+20)) for t in (200.0,300.0)];assert inbox.counts()['failed']==1,'attempts'"
Expected red signature: ModuleNotFoundError: No module named 'inbox'
Expected on main: ModuleNotFoundError
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- A write outside `COORD_INBOX_DIR`, or any read of `~/.local/state/coordinator` when the variable is set.
- A kind outside the closed set stored in any table.
- A model call, a send, a job load, or a change to the tick, the guard or t56.
- No new plist under `coordinator/launchd` (the installer loads every plist there), no weakening of an existing test and no new test file.

## CI

No workflows and no GitHub Actions, ever. The local check is `scripts/mac_ops_fast_check.py`.

## Data/secrets and stop conditions

Never read or print `models.json` or any API key. Never run `coordq dispatch`, refill, `ticket start/close` or the lane. Use a temp `COORD_INBOX_DIR` and `COORD_JOURNAL_DIR` for every run. Stop and report if over 3 code files or about 150 code lines.

## Rollback

Revert the merge commit. The file is not imported by anything, so nothing else changes.

## Gate

Astra gate on the PR head. Loop-code hold applies; Shyam merges after PASS.

## Finish

Report the PR, the head and the check line.
