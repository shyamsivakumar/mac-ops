# MO-951 runs

## Proof command

Red on origin/main (cf5b343b), exit 1:

    ModuleNotFoundError: No module named 'inbox_worker'

Green on the head, in place: exit 0. Green from a flat copy of coordinator/bin/*.py plus coordinator/overnight/*.py in one temp dir: exit 0.

## inbox eval of coordinator/overnight/selftest.py

The branch's selftest on origin/main: exit 1, `ModuleNotFoundError: No module named 'inbox_worker'` raised from worker_cases.
On the branch, in place: exit 0 ("inbox eval OK"). From the flat copy with HOME=/nonexistent: exit 0.

worker_cases covers: the proof flow (7 lines, one `none/shadow` outbox row, would-wake journal line, gap); garbage reply (rows pending, attempt counted); ModelUnavailable (attempt not counted); runner exception (attempt counted); late finish from a reaped claim (no outbox row); a held worker lock (returns at once); a row for another session (not claimed); no poll when COORD_INBOX_REPOS is unset; lone surrogate, 2 MB, list and string payloads, a corrupt payload column, and a SEND target and text stored as data; unparsable COORD_INBOX_DEBOUNCE and COORD_INBOX_MIN_GAP reported on stderr.
