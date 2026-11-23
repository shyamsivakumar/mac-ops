# Event inbox T9: shadow worker pass (batch, coalesce, parse, would-wake line)

Part of the coordinator event inbox (design: `docs/coordinator-event-inbox-design.md`, PR #897). Shadow mode only: this ticket changes no behavior of the tick, the guard, t56 or any launchd job.

## Goal and why

Add the worker pass in shadow mode. One pass takes the worker lock, reaps, enqueues due timers, replays the journal, polls (only for configured repos), then claims a batch for the `coordinator` session when a wake-tier row is at least 60 seconds old and the last run ended at least 30 minutes ago. It coalesces rows by repo, PR and kind, runs the batch through the shadow runner (which returns `NOTHING: shadow`), parses the reply into outbox rows, marks the rows done in one transaction with those outbox rows, and writes one `inbox_would_wake` journal line. No model is called and nothing is sent; the real runner replaces the shadow runner only at cutover.

## Context

- Design: section 3.5 (claim, batch and run), 3.4 invariants 4, 6, 10, section 6 step 3.
- The reply format `SEND <target>: <text>` or `NOTHING: <reason>` follows `coord-tick`'s `ALERT:` and `NOOP` convention (`alert_lines`, lines 176 to 186); a reply with neither is a failed run whose rows go back to pending with the attempt counted. A runner that raises `ModelUnavailable` puts rows back without counting an attempt.
- Do not import or edit `coordinator/pi/bin/coord-tick`.

## Scope and non-goals

In:

- `coordinator/bin/inbox_worker.py` (new): `shadow_pass(*, now) -> dict` (`batches`, `lines`), `coalesce(rows)`, `parse_reply(text) -> list`, `finish(ids, reply, *, run_id, now)`, and `ModelUnavailable`. The lock is `inbox.worker.lock` in `COORD_INBOX_DIR`.
- Settings: `COORD_INBOX_DEBOUNCE`, default `60`; `COORD_INBOX_MIN_GAP`, default `1800` (the design's 30-minute gap, Shyam's open question 3); `COORD_INBOX_SHADOW`, default `1`.
- `coordinator/overnight/selftest.py`: extend the `inbox` eval with the proof plus a garbage reply (rows pending, attempt counted) and a `ModelUnavailable` runner (rows pending, attempt not counted).
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: A real model runner, `coord-tick`, a launchd plist (the installer loads every plist in `coordinator/launchd`), the in-session timer, any send. Also out: any plist or job load, any model call, any send, `coordinator/pi/bin/coord-tick`, `coordinator/pi/extensions/coordinator.ts`, the live session t56, the live queue, the real journal and `~/.coordinator`.

## Design fit

Requires: T1, T3, T4, T6, T7, T8.
Provides: The shadow week's `inbox_would_wake` lines and the pipeline the cutover plugs a real runner into.

## Blocked by

T3, T4, T6, T7, T8 (replace with the issue numbers once filed).

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main (with the blockers merged) and green on the head, and the `inbox` eval of `coordinator/overnight/selftest.py` named as the case that fails on origin/main and passes on the branch.
3. The proof:

```text
Proof command:
HOME=/nonexistent python3 -c "import os,sys,glob,tempfile,subprocess;subprocess.run=subprocess.Popen=None;j=tempfile.mkdtemp();os.environ.update(COORD_JOURNAL_DIR=j,COORD_INBOX_DIR=tempfile.mkdtemp());sys.path.insert(0,'coordinator/bin');import inbox_worker as w,inbox;e=lambda k,key,p:inbox.enqueue(k,key,source='journal',ts=0.0,repo='o/r',pr=p);[e('pr_new_head',f'pr_new_head:o/r#{p}:{h}',p) for p in range(1,6) for h in 'ab'];e('round_cap','round_cap:o/r#1:x',1);e('round_cap','round_cap:o/r#2:x',2);a=w.shadow_pass(now=100.0);assert a['batches']==1 and a['lines']==7,a;assert [tuple(r) for r in inbox.connect().execute('select kind,reason from outbox')]==[('none','shadow')],'outbox';assert 'inbox_would_wake' in ''.join(open(f).read() for f in glob.glob(j+'/events-*.jsonl')),'journal';assert w.shadow_pass(now=101.0)['batches']==0,'gap'"
Expected red signature: ModuleNotFoundError: No module named 'inbox_worker'
Expected on main: ModuleNotFoundError
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- A subprocess, a model call or a send (the proof replaces `subprocess.run` and `Popen` with `None`).
- A done row without its outbox row in the same transaction.
- Rows lost when the runner fails.
- A model call, a send, a job load, or a change to the tick, the guard or t56.
- No new plist under `coordinator/launchd` (the installer loads every plist there), no weakening of an existing test and no new test file.

## CI

No workflows and no GitHub Actions, ever. The local check is `scripts/mac_ops_fast_check.py`.

## Data/secrets and stop conditions

Never read or print `models.json` or any API key. Never run `coordq dispatch`, refill, `ticket start/close` or the lane. Use a temp `COORD_INBOX_DIR` and `COORD_JOURNAL_DIR` for every run. Stop and report if over 3 code files or about 150 code lines.

## Rollback

Revert the merge commit. No job calls the module until cutover.

## Gate

Astra gate on the PR head. Loop-code hold applies; Shyam merges after PASS.

## Finish

Report the PR, the head and the check line.
