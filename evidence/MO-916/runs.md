# MO-916 runs

Proof command (ticket item 3), from the repo root, temp COORD_JOURNAL_DIR and COORD_INBOX_DIR:

```
HOME=/nonexistent python3 -c "import os,sys,tempfile;os.environ.update(COORD_JOURNAL_DIR=tempfile.mkdtemp(),COORD_INBOX_DIR=tempfile.mkdtemp(),COORD_INBOX_HOOK='on');sys.path.insert(0,'coordinator/bin');import journal,inbox;[journal.emit('gate_verdict','lane',repo='o/r',pr=7,head='a'*40,verdict='PASS') for _ in (0,0)];journal.emit('alarm_raised','alarms',alarm='x-1');journal.emit('alarm_withdrawn','alarms',alarm='x-1');journal.emit('alarm_raised','alarms',alarm='x-1');c=inbox.counts();assert c['pending']==3,('hook',c)"
```

## Red on origin/main 2ea72fba

```
AssertionError: ('hook', {'pending': 0, 'claimed': 0, 'done': 0, 'failed': 0})
```

## Green on the head

```
exit 0
```

## inbox eval of coordinator/overnight/selftest.py

On origin/main code with the new selftest: fails (`AttributeError: module 'journal' has no attribute 'INBOX_WAIT'`, the first hook case).
On this branch: `selftest.inbox()` passes. Cases: hook unset imports no inbox module and opens no inbox file; hook on writes 3 rows for gate_verdict x2, alarm raise, withdraw, raise x2, and an unmapped event (alarm:x-1:0, alarm:x-1:1, one gate_verdict); an unwritable COORD_INBOX_DIR keeps the journal line and prints one stderr line; a database held under BEGIN IMMEDIATE returns in under 2 s with the journal line kept and one stderr line.

## Bounds

- Database wait: journal passes one monotonic deadline (2 s) to `inbox.txn(deadline)`. It sets the sqlite connect timeout to the time left, polls the `.init` flock with LOCK_NB until the deadline, and sets `busy_timeout` to the time left before each BEGIN IMMEDIATE. Callers passing no deadline keep the 30 s timeout and the blocking flock.
- Alarm generation: read in `from_journal` and bumped on `alarm_withdrawn` inside the same BEGIN IMMEDIATE transaction as the insert, so concurrent processes serialize on the database write lock.
