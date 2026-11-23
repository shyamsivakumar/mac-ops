# Event inbox T8: poll pass for CI on main from Mac-published statuses

Part of the coordinator event inbox (design: `docs/coordinator-event-inbox-design.md`, PR #897). Shadow mode only: this ticket changes no behavior of the tick, the guard, t56 or any launchd job.

## Goal and why

Add `ci_main` rows from the commit status of each configured repo's default branch head, keeping only the contexts the Mac publishes and only terminal states. There is no GitHub Actions and there never will be, so check-runs from workflows are never read. A failure is a wake row; a success is batch-only.

## Context

- Design: section 3.3 (CI on main), 3.2 (the key ends in the terminal state, so a pending status cannot hide the later result).
- `srw/agent-check` is the Mac-published context on SRW PR heads. Whether `main` carries one per repo is unconfirmed; a repo with no Mac context is skipped and logged.

## Scope and non-goals

In:

- `coordinator/bin/inbox_poll.py`: `poll_ci(repos, fetch_status, *, now) -> int` and a default `fetch_status(repo)` through `gh_gateway` returning `{"sha", "statuses": [{"context", "state"}]}`. Key `ci_main:<repo>:<sha>:<context>:<state>`; `tier` is `wake` for `failure` and `error`, `batch` for `success`; `pending` is never enqueued.
- Setting `COORD_INBOX_CI_CONTEXTS`, default `srw/agent-check` (a comma list of Mac-published contexts).
- `coordinator/overnight/selftest.py`: extend the `inbox` eval with the proof.
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: Reading workflow runs or check-runs, any GitHub write, a change to `gh_gateway.py`. Also out: any plist or job load, any model call, any send, `coordinator/pi/bin/coord-tick`, `coordinator/pi/extensions/coordinator.ts`, the live session t56, the live queue, the real journal and `~/.coordinator`.

## Design fit

Requires: T7's `inbox_poll.py`.
Provides: `ci_main` rows.

## Blocked by

T7 (replace with the issue number once filed).

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main (with the blockers merged) and green on the head, and the `inbox` eval of `coordinator/overnight/selftest.py` named as the case that fails on origin/main and passes on the branch.
3. The proof:

```text
Proof command:
HOME=/nonexistent python3 -c "import os,sys,tempfile;os.environ['COORD_INBOX_DIR']=tempfile.mkdtemp();sys.path.insert(0,'coordinator/bin');import inbox,inbox_poll as p;st={'sha':'c'*40,'statuses':[{'context':'srw/agent-check','state':'pending'},{'context':'ci/other','state':'failure'}]};f=lambda repo:st;assert p.poll_ci(['o/r'],f,now=1.0)==0,'pending and non-Mac';st['statuses'][0]['state']='success';assert p.poll_ci(['o/r'],f,now=2.0)==1,'success';st['statuses'][0]['state']='failure';assert p.poll_ci(['o/r'],f,now=3.0)==1,'state is in the key';tiers=[r['tier'] for r in inbox.claim('coordinator',worker='w',now=4.0,lease=9,pid=4194303)];assert sorted(tiers)==['batch','wake'],tiers"
Expected red signature: AttributeError: module 'inbox_poll' has no attribute 'poll_ci'
Expected on main: AttributeError
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- A row for a non-Mac context or a `pending` state.
- A read of Actions or workflow check-runs.
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
