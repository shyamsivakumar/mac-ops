# MO-904 runs

Temp COORD_INBOX_DIR and COORD_JOURNAL_DIR in every run. Python 3.9.6, SQLite 3.54.0. `claim` uses no RETURNING.

## Ticket proof command

On origin/main (no `inbox` module):

    ModuleNotFoundError: No module named 'inbox'

On the head: exit 0.

## `inbox` eval (coordinator/overnight/selftest.py)

On origin/main (eval run against a checkout without `inbox.py`): `ModuleNotFoundError: No module named 'inbox'`.

On the branch: `PASS inbox`.

Mutation check: with the `run_id` filter removed from `ack` and `release`, the eval fails with `expected (0, 0), got (1, 0)` at the late-ack step.

Covered: dedupe and the `seen` write in one transaction; tier from `COORD_INBOX_WAKE_KINDS`; closed kind set (`ValueError`, nothing stored in `seen`); two spawned processes claiming 10 rows with no row handed to both; early reap, reap, failure after 3 claims; A claims, is reaped, B claims, A's late `ack` and `release` return 0 and B stays claimed; the same after `release(count_attempt=False)` by A then B's claim; `os.kill` raising `PermissionError` counts as alive; a lease over an hour past due is reaped.
