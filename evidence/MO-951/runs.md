# MO-951 runs

## Proof command

Red on origin/main (cf5b343b), exit 1:

    ModuleNotFoundError: No module named 'inbox_worker'

Green on the head, in place: exit 0. Green from a flat copy of coordinator/bin/*.py plus coordinator/overnight/*.py in one temp dir: exit 0.

## inbox eval of coordinator/overnight/selftest.py

The branch's selftest on origin/main: exit 1, `ModuleNotFoundError: No module named 'inbox_worker'` raised from worker_cases.
On the branch, in place: exit 0 ("inbox eval OK"). From the flat copy with HOME=/nonexistent: exit 0.

worker_cases covers: the proof flow (7 lines, one `none/shadow` outbox row, would-wake journal line, gap); garbage reply (rows pending, attempt counted); ModelUnavailable (attempt not counted); runner exception (attempt counted); late finish from a reaped claim (no outbox row); a held worker lock (returns at once); a row for another session (not claimed); no poll when COORD_INBOX_REPOS is unset; lone surrogate, 2 MB, list and string payloads, a corrupt payload column, and a SEND target and text stored as data; unparsable COORD_INBOX_DEBOUNCE and COORD_INBOX_MIN_GAP reported on stderr.

## Review round 1 (after merging origin/main a6eecb81)

- inbox.txn is as on main. `inbox._ack(conn, rows, now)` and `inbox_outbox._insert(conn, ...)` take one explicit connection; `ack` and `add` wrap them. `finish` uses one `txn()` for the ack and every outbox insert.
- New worker_cases: an error on the second outbox insert leaves the rows claimed and no outbox row; a second thread asking for `txn` with a short deadline while another holds it fails instead of joining; `SEND t56 text` or `NOTHING:` lines that do not parse make the whole reply garbage (rows pending, attempt counted, no outbox row); a runner returning None, bytes or a dict is a failed run like garbage.
- Proof command exit 0 in place and flat; inbox eval exit 0 in place and flat (HOME=/nonexistent).
