# Event inbox T3: outbox table writer and shadow-safe dispatcher

Part of the coordinator event inbox (design: `docs/coordinator-event-inbox-design.md`, PR #897). Shadow mode only: this ticket changes no behavior of the tick, the guard, t56 or any launchd job.

## Goal and why

Add the outbox: every decision of a run becomes a row (`hc_send`, `coordq_send`, `request_notice`, or an explicit `none` with a reason), and a dispatcher drains them. The dispatcher never calls a sender while `COORD_INBOX_SHADOW` is on (the default), so nothing is sent. `hc_send` is at-most-once (a row left in `sending` after a crash becomes `unknown`); `coordq_send` is at-least-once.

## Context

- Design: section 3.7 (outbox columns, the kind-dependent delivery rule, `no_decision`).
- The outbox table is created by T1; this ticket writes and drains it.
- The sender is injected (`sender(row)`), so no test or proof needs `hc` or `coordq`.

## Scope and non-goals

In:

- `coordinator/bin/inbox_outbox.py` (new): `add(run_id, index, kind, target, body, *, reason=None, now) -> bool` with dedupe key `<run_id>:<index>`; `ValueError` for an unknown kind and for `none` without a reason. `drain(sender, *, now, shadow=None) -> dict` (`shadow` defaults to the setting). In shadow it returns `{"would_send": n}` and changes nothing. Otherwise it marks a row `sending`, calls `sender(row)`, marks it `sent`, and counts a sender exception as `errors` while leaving the row `sending`; `none` rows are marked `sent` with no call. `reap(*, now) -> dict` turns `hc_send` rows in `sending` for more than 600 s into `unknown` and returns `{"unknown": n}`; a `coordq_send` row in `sending` returns to `pending` up to 3 tries, then `failed`.
- Setting `COORD_INBOX_SHADOW`, default `1`.
- `coordinator/overnight/selftest.py`: extend the `inbox` eval with the proof's cases plus the 3-try rule for `coordq_send`.
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: Any real sender, `hc`, `coordq`, the card path, a loaded job, `coord-tick`. Also out: any plist or job load, any model call, any send, `coordinator/pi/bin/coord-tick`, `coordinator/pi/extensions/coordinator.ts`, the live session t56, the live queue, the real journal and `~/.coordinator`.

## Design fit

Requires: T1.
Provides: The outbox every run's decisions pass through.

## Blocked by

T1 (replace with the issue number once filed).

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main (with the blockers merged) and green on the head, and the `inbox` eval of `coordinator/overnight/selftest.py` named as the case that fails on origin/main and passes on the branch.
3. The proof:

```text
Proof command:
HOME=/nonexistent python3 -c "import os,sys,tempfile;os.environ['COORD_INBOX_DIR']=tempfile.mkdtemp();sys.path.insert(0,'coordinator/bin');import inbox_outbox as o;sent=[];assert o.add('r',0,'hc_send','t56','hi',now=1.0) and not o.add('r',0,'hc_send','t56','hi',now=1.0),'dup';o.add('r',1,'none',None,'',reason='quiet',now=1.0);assert o.drain(sent.append,now=2.0,shadow=True)=={'would_send':1} and not sent,'shadow';assert o.drain(sent.append,now=3.0,shadow=False)['sent']==2 and len(sent)==1,'send';o.add('r',2,'hc_send','t56','again',now=4.0);assert o.drain(lambda r:1/0,now=5.0,shadow=False)['errors']==1;assert o.reap(now=900.0)=={'unknown':1},'crash'"
Expected red signature: ModuleNotFoundError: No module named 'inbox_outbox'
Expected on main: ModuleNotFoundError
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- A call to a sender while `COORD_INBOX_SHADOW` is on.
- A `none` row without a reason.
- A second resend of an `hc_send` row.
- A model call, a send, a job load, or a change to the tick, the guard or t56.
- No new plist under `coordinator/launchd` (the installer loads every plist there), no weakening of an existing test and no new test file.

## CI

No workflows and no GitHub Actions, ever. The local check is `scripts/mac_ops_fast_check.py`.

## Data/secrets and stop conditions

Never read or print `models.json` or any API key. Never run `coordq dispatch`, refill, `ticket start/close` or the lane. Use a temp `COORD_INBOX_DIR` and `COORD_JOURNAL_DIR` for every run. Stop and report if over 3 code files or about 150 code lines.

## Rollback

Revert the merge commit. Nothing imports the module.

## Gate

Astra gate on the PR head. Loop-code hold applies; Shyam merges after PASS.

## Finish

Report the PR, the head and the check line.
