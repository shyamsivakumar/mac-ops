# MO-926 runs

## Ticket proof command

Command: `python3 -c "<proof>"` (the ticket text, quotes swapped)

### On origin/main d5efd3f8
```
AssertionError: selftest needs a repository script
exit 1
```
### On the head
```
exit 0
```

## Flat run of the installed selftest

Method: `install_coordinator.plan(checkout, tmp_home)` lists the installer's targets. Every file bound for `~/.local/bin` is copied into one directory (`<tmp>/home/.local/bin`), the config and herdr files into the same temp HOME (the installer was not run). Then `python3 selftest.py` runs there with temp HOME, COORDQ_DIR, COORD_JOURNAL_DIR and COORD_INBOX_DIR. EXPECTED holds 34 names; the script is /private/tmp/claude-501/-Users-shyamsivakumar-Code/c283b00e-e8c8-422f-9aa1-eb7c969bb5ce/scratchpad/flat926.sh.

| Checkout | Result |
| --- | --- |
| 820e81b8 (before the metrics case) | exit 0, 34 PASS |
| origin/main d5efd3f8 | exit 1, 33 PASS, `FAIL inbox: [Errno 2] No such file or directory: '.../scripts/coord_wake_metrics.py'` (red) |
| this head (code commit 9df998be) | exit 0, 34 PASS (green) |
| PR #924 head 16f2de65 (adds outbox_cases) | exit 0, 34 PASS |

No other eval fails flat. A first run with the files in a bare directory failed worktree-base-ref and consolidation-guard (they look for ../bin/coordq) and alarm-mute (panel files); those were set-up faults of the temp layout, absent once the layout matched the installed one, and 820e81b8 passes the same way.

The moved case runs as `python3 -m unittest tests.test_coordq_message_dedupe.WakeMetricsTests` (1 test, OK) and is not in the installed selftest. It lives in test_coordq_message_dedupe.py, the existing module that already tests the coordinator queue's dedupe keys; no module covers inbox.py.
