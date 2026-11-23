# Event inbox T7: poll pass for PR opened, new head, review and unverified human signals

Part of the coordinator event inbox (design: `docs/coordinator-event-inbox-design.md`, PR #897). Shadow mode only: this ticket changes no behavior of the tick, the guard, t56 or any launchd job.

## Goal and why

Add the real source of `pr_opened` and `pr_new_head`. `gate_queued` misses held, draft and ungated PRs (mac-ops #868 and #882 were queued 27 hours after they opened), so a poll over the open PR list produces the rows. A review, a comment or the `merge:human-ok` label is recorded as `human_signal` with `verified=false`, because agents act under Shyam's GitHub login and the login proves no person.

## Context

- Design: section 3.3 (PR opened, new head, review, label and comment events; human signals are hints), section 3.6.
- `coordinator/bin/gh_gateway.py` is the existing cached GitHub caller (ETag, list TTL); use it, do not add a second caller.
- Detection lag is up to 2 minutes; `pr_opened` is a batch kind, so it adds no wake.

## Scope and non-goals

In:

- `coordinator/bin/inbox_poll.py` (new): `poll_prs(repos, fetch, *, now) -> int` and a default `fetch(repo)` that lists open PRs through `gh_gateway` (`number`, `headRefOid`, `isDraft`, `createdAt`, `labels`, `reviews`). Keys `pr_opened:<repo>#<n>:`, `pr_new_head:<repo>#<n>:<head>`, `pr_review:<repo>#<n>:<review id>`, `human_signal:<repo>#<n>:<label or review id>`. `ts` is the PR's `createdAt` or the review time, not `now`. A `human_signal` payload is `{"verified": false, ...}`.
- Setting `COORD_INBOX_REPOS`, default empty (a comma list). With no repos the pass makes no GitHub call.
- `coordinator/overnight/selftest.py`: extend the `inbox` eval with the proof; the eval patches the fetch, so it makes no network call.
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: Parsing comment or review text (payloads carry ids and labels only), `ci_main` (T8), any write to GitHub, the guard. Also out: any plist or job load, any model call, any send, `coordinator/pi/bin/coord-tick`, `coordinator/pi/extensions/coordinator.ts`, the live session t56, the live queue, the real journal and `~/.coordinator`.

## Design fit

Requires: T1.
Provides: `pr_opened`, `pr_new_head`, `pr_review`, `human_signal` rows.

## Blocked by

T1 (replace with the issue number once filed).

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main (with the blockers merged) and green on the head, and the `inbox` eval of `coordinator/overnight/selftest.py` named as the case that fails on origin/main and passes on the branch.
3. The proof:

```text
Proof command:
HOME=/nonexistent python3 -c "import os,sys,tempfile;os.environ['COORD_INBOX_DIR']=tempfile.mkdtemp();sys.path.insert(0,'coordinator/bin');import inbox_poll as p,inbox;pr=lambda n,**k:dict(number=n,headRefOid='a'*40,isDraft=True,createdAt='2026-11-22T17:18:16Z',labels=[],reviews=[],**k);prs=[pr(868),pr(5)];f=lambda repo:prs;assert p.poll_prs(['o/r'],f,now=10.0)==2,'opened';assert p.poll_prs(['o/r'],f,now=11.0)==0,'again';prs[1]['headRefOid']='b'*40;prs[0]['labels']=[{'name':'merge:human-ok'}];assert p.poll_prs(['o/r'],f,now=12.0)==2,'head+signal';row=[r for r in inbox.claim('coordinator',worker='w',now=13.0,lease=9,pid=4194303) if r['kind']=='human_signal'][0];assert row['payload']['verified'] is False,row"
Expected red signature: ModuleNotFoundError: No module named 'inbox_poll'
Expected on main: ModuleNotFoundError
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- A GitHub write of any kind.
- A `human_signal` treated as proof of a person (the payload says `verified: false`).
- A second GitHub caller beside `gh_gateway`.
- A model call, a send, a job load, or a change to the tick, the guard or t56.
- No new plist under `coordinator/launchd` (the installer loads every plist there), no weakening of an existing test and no new test file.

## CI

No workflows and no GitHub Actions, ever. The local check is `scripts/mac_ops_fast_check.py`.

## Data/secrets and stop conditions

Never read or print `models.json` or any API key. Never run `coordq dispatch`, refill, `ticket start/close` or the lane. Use a temp `COORD_INBOX_DIR` and `COORD_JOURNAL_DIR` for every run. Stop and report if over 3 code files or about 150 code lines.

## Rollback

Revert the merge commit. The setting `COORD_INBOX_REPOS` is empty by default, so nothing polls.

## Gate

Astra gate on the PR head. Loop-code hold applies; Shyam merges after PASS.

## Finish

Report the PR, the head and the check line.
