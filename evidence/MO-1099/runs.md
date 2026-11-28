# MO-1099 runs

Proof command (ticket body): a fake t3 and a temp journal dir call
`lane_driver.journal_verdict` with a PASS and assert one
`t3_thread_organize` settle call.

## origin/main (red)

```text
  File "<string>", line 1, in <module>
AssertionError: []
```

## Branch (green)

```text
exit=0
```

## New selftest case `gate-settle` (branch)

Covers: a PASS settles once and a second call does nothing; a failed settle
leaves no ledger key, logs, and the next FAIL call settles; SPLIT settles
nothing; a dry run settles nothing.

```text
DEAD T: settle failed: down; left for the next pass
gate_settle PASS
```

On origin/main the case does not exist (no `settle_read_gate`, no settle call), so the
proof command above is its red run.
