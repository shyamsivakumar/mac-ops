# MO-964 runs

Proof command (issue #964), run in a clean checkout of origin/main and on the branch head:

```
HOME=/nonexistent python3 -c "import os,sys,tempfile,subprocess;subprocess.run=subprocess.Popen=None;d=tempfile.mkdtemp();os.environ.update(COORD_JOURNAL_DIR=tempfile.mkdtemp(),COORD_INBOX_DIR=d,COORD_INBOX_SHADOW=\"1\");sys.path.insert(0,\"coordinator/bin\");import inbox_worker as w;assert w.main([])==0;e=os.path.join(tempfile.mkdtemp(),\"x\");os.environ.update(COORD_INBOX_DIR=e,COORD_INBOX_SHADOW=\"0\");assert w.main([])==2 and not os.path.exists(e)"
```

## Red on origin/main (fc27b9ad)

```
AttributeError: module 'inbox_worker' has no attribute 'main'
exit 1
```

## Green on the branch

```
inbox shadow pass skipped: shadow mode off
exit 0
```

(The stderr line is the refusal path of the second assert: shadow off, exit 2, no inbox dir created.)

## Eval

`inbox` eval in coordinator/overnight/selftest.py, new `main_cases`, run alone with subprocess forbidden:
origin/main: `AttributeError: module 'inbox_worker' has no attribute 'main'`; branch: passes.

## Interpreter

`/usr/bin/python3` is 3.9.6. The job's python (same as the turncap plist) runs the worker, every inbox*.py and journal.py import and run on it:
the proof above, the sizing below and the error run below were all run with `/usr/bin/python3`.

## First-pass cost on a copy of the live journal (temp COORD_INBOX_DIR and COORD_JOURNAL_DIR)

Copy of ~/.local/state/coordinator/journal: 9.0 MB, 21460 lines.

| run | seconds | db bytes |
|---|---|---|
| pass 1 (activates, replays everything) | 0.50 | 3932160 |
| pass 2 (reads no new bytes) | 0.04 | 3932160 |

After both: inbox rows 0, outbox rows 0, seen rows 21284. Nothing from before activation was enqueued.

## Synthetic round_cap, injected clock (temp dirs only)

Appended one round_cap row at t0, then shadow_pass(now=...):

```
t+0    {'batches': 0, 'lines': 0}
t+30   {'batches': 0, 'lines': 0}
t+62   {'batches': 1, 'lines': 1}
t+63   {'batches': 0, 'lines': 0}
```

One `inbox_would_wake` row (rows=1, lines=1, delay=62.0) landed in the temp journal after the 60 s debounce.

## A pass that errors

COORD_INBOX_DIR pointing at a file: `rc=1`, stderr `inbox shadow pass failed: FileExistsError` (42 bytes). One line per minute is 60 KB a day. No payload, no journal row.
