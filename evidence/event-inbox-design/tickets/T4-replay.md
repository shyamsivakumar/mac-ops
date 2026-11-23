# Event inbox T4: activation watermark and journal replay across month files

Part of the coordinator event inbox (design: `docs/coordinator-event-inbox-design.md`, PR #897). Shadow mode only: this ticket changes no behavior of the tick, the guard, t56 or any launchd job.

## Goal and why

Let the inbox be rebuilt from the journal without flooding it. The first activation records `activated_at`; journal lines older than that go straight into `seen` and never become pending rows. A per-file offset cursor reads every `events-YYYY-MM.jsonl`, so a late line appended to an old month is still read after the cursor has moved on. Without the watermark a replay of this month would enqueue 1,461 old facts.

## Context

- Design: section 1 (the three replay rules).
- `journal.py` names files `events-YYYY-MM.jsonl` in `COORD_JOURNAL_DIR`; a line that does not parse must be skipped, not crash the caller.
- `from_journal` is T2's mapping.

## Scope and non-goals

In:

- `coordinator/bin/inbox_replay.py` (new): `activate(*, now)` writes `activated_at` to `meta` once; `replay() -> dict` returns `{"enqueued", "seen_only", "skipped"}`. Per-file byte offsets live in `meta`. A line with `ts` below `activated_at` goes to `seen` only (`seen_only`); a mapped newer line is enqueued; an unmapped or unparsable line counts as `skipped`. A repeated replay is a no-op.
- `coordinator/overnight/selftest.py`: extend the `inbox` eval with the proof plus a truncated last line (no newline yet) that is read on the next call.
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: Running the replay from any job (T9 does), the hook, any change to `journal.py`. Also out: any plist or job load, any model call, any send, `coordinator/pi/bin/coord-tick`, `coordinator/pi/extensions/coordinator.ts`, the live session t56, the live queue, the real journal and `~/.coordinator`.

## Design fit

Requires: T1 and T2.
Provides: A safe rebuild and the hourly repair pass.

## Blocked by

T1, T2 (replace with the issue numbers once filed).

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main (with the blockers merged) and green on the head, and the `inbox` eval of `coordinator/overnight/selftest.py` named as the case that fails on origin/main and passes on the branch.
3. The proof:

```text
Proof command:
HOME=/nonexistent python3 -c "import os,sys,json,tempfile;j=tempfile.mkdtemp();os.environ.update(COORD_JOURNAL_DIR=j,COORD_INBOX_DIR=tempfile.mkdtemp());sys.path.insert(0,'coordinator/bin');import inbox_replay as p,inbox;r=lambda t,e,n,**k:dict(ts=t,event=e,actor='x',repo='o/r',pr=n,head='a'*40,ticket=None,data=k);w=lambda f,*L:open(os.path.join(j,f),'a').writelines(json.dumps(x)+'\\n' for x in L);w('events-2026-10.jsonl',r(100,'gate_verdict',1),r(5000,'gate_verdict',2));w('events-2026-11.jsonl',r(6000,'alarm_raised',0,alarm='a-1'));open(os.path.join(j,'events-2026-11.jsonl'),'a').write('not json\\n');p.activate(now=1000.0);a=p.replay();assert a=={'enqueued':2,'seen_only':1,'skipped':1},a;w('events-2026-10.jsonl',r(7000,'gate_verdict',3));assert p.replay()['enqueued']==1,'late'"
Expected red signature: ModuleNotFoundError: No module named 'inbox_replay'
Expected on main: ModuleNotFoundError
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- A pending row from a line older than `activated_at`.
- A crash on a line that does not parse.
- A read of the whole month file on every call (seek to the saved offset).
- A model call, a send, a job load, or a change to the tick, the guard or t56.
- No new plist under `coordinator/launchd` (the installer loads every plist there), no weakening of an existing test and no new test file.

## CI

No workflows and no GitHub Actions, ever. The local check is `scripts/mac_ops_fast_check.py`.

## Data/secrets and stop conditions

Never read or print `models.json` or any API key. Never run `coordq dispatch`, refill, `ticket start/close` or the lane. Use a temp `COORD_INBOX_DIR` and `COORD_JOURNAL_DIR` for every run. Stop and report if over 3 code files or about 150 code lines.

## Rollback

Revert the merge commit. Nothing calls it until T9.

## Gate

Astra gate on the PR head. Loop-code hold applies; Shyam merges after PASS.

## Finish

Report the PR, the head and the check line.
