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

## Existing cases that reach the settle

The first fast check on the M1 failed `gate-pipeline`, `gate-round-cap`, `watchdog`
and `closed-ticket-merge`: their fakes refused a `t3_thread_organize` call, and
`EXPECTED` in `hourly_selftest.py` lacked `gate-settle`. The fakes now answer
`t3_thread_organize` and `EXPECTED` lists the new case. Those cases and
`merge-pass`, `held-merge` and `gate-settle` pass with subprocess calls forbidden.

The second M1 check failed the unittest suite: `tests.test_lane_duplicate_suppression`
(6 cases) fakes T3 and refused `t3_thread_organize`. That fake now answers it; the 8 cases
pass, and so do `tests.test_install_coordinator` and `tests.test_lane_decisions_board`.
