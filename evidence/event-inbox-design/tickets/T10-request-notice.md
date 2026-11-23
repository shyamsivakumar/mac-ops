# Event inbox T10: request notice, outcome close, no grant

Part of the coordinator event inbox (design: `docs/coordinator-event-inbox-design.md`, PR #897). Shadow mode only: this ticket changes no behavior of the tick, the guard, t56 or any launchd job.

## Goal and why

Replace approvals with a request notice. When a run ends on a blocked call, it writes a `request_notice` outbox row naming the PR, head and action wanted. The row carries no authority: there is no grant table, no `approve` text parsing, and no inbox kind that the guard could accept. Shyam performs the guarded action, and the inbox sees the result (`pr_merged`) and closes the notice. An unanswered notice is raised again once after 24 hours.

## Context

- Design: section 3.6 (why no grant: any agent can `hc send t56 "approve <id>"`, `decisions.json` has several agent writers, and agent actions on GitHub use Shyam's login), open question 1 (an authenticated channel is a separate decision and is not built here).
- The guard (`coordinator.ts`) stays deny-only and is not touched.

## Scope and non-goals

In:

- `coordinator/bin/inbox_outbox.py`: `request_notice(run_id, index, repo, pr, head, action, *, now)` (outbox kind `request_notice`), `close_requests(*, now) -> int` (closes a notice when a `pr_merged` row for the same repo and PR has `ts` at or after the notice), `reissue_due(*, now) -> int` (a notice open more than 86,400 s that was not raised before gets one more notice).
- `coordinator/overnight/selftest.py`: extend the `inbox` eval with the proof plus a forged `approve <id>` payload that creates no row of any kind.
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: `coordinator.ts`, the guard, parsing text from t56 or the decisions board, an authenticated channel, a real send. Also out: any plist or job load, any model call, any send, `coordinator/pi/bin/coord-tick`, `coordinator/pi/extensions/coordinator.ts`, the live session t56, the live queue, the real journal and `~/.coordinator`.

## Design fit

Requires: T3, T9.
Provides: The only approval-shaped path in the design, and it grants nothing.

## Blocked by

T3, T9 (replace with the issue numbers once filed).

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main (with the blockers merged) and green on the head, and the `inbox` eval of `coordinator/overnight/selftest.py` named as the case that fails on origin/main and passes on the branch.
3. The proof:

```text
Proof command:
HOME=/nonexistent python3 -c "import os,sys,tempfile;os.environ['COORD_INBOX_DIR']=tempfile.mkdtemp();sys.path.insert(0,'coordinator/bin');import inbox,inbox_outbox as o;o.request_notice('run1',0,'o/r',7,'a'*40,'merge PR 7',now=10.0);__import__('unittest').TestCase().assertRaises(ValueError,inbox.enqueue,'approval_answer','k',source='human',ts=1.0);assert not [n for (n,) in inbox.connect().execute('select name from sqlite_master') if 'grant' in n],'no grant table';assert o.close_requests(now=20.0)==0,'open';inbox.enqueue('pr_merged','pr_merged:o/r#7:',source='journal',ts=15.0,repo='o/r',pr=7);assert o.close_requests(now=20.0)==1,'closed';o.request_notice('run1',1,'o/r',8,'b'*40,'merge PR 8',now=30.0);assert o.reissue_due(now=30.0+86401)==1 and o.reissue_due(now=30.0+86402)==0,'reissue once'"
Expected red signature: AttributeError: module 'inbox_outbox' has no attribute 'request_notice'
Expected on main: AttributeError
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- A table, kind, setting or function named for a grant or an approval answer.
- Any change to the guard or to what it allows.
- A send.
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
