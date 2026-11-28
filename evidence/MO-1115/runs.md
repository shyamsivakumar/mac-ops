# MO-1115 runs

Proof command (ticket body): fakes for `run`, `fast_forward_main`, the receipts and `t3` call
`lane_driver.close_after_merge('o/r', 5, ...)` for ticket 7 and assert the settled threads are
the ticket's builder, the PR's fix thread and the PR's gate thread, and no other thread.

## origin/main (red)

```text
  File "<string>", line 1, in <module>
AssertionError: []
```

## Branch (green)

Exit code 0.

## `gate-settle` selftest case (extended)

The case now also covers the close: a dry run settles nothing; the close settles the
ticket's builder (`ticket:o/r#7:a1`) and the PR's fix and gate threads, and leaves a
running vote thread, another ticket (`#70`) and another PR (`#50`) alone; a later pass settles
the vote thread once it is no longer running, and settles nothing twice.

Receipts name the threads (`ticket:<repo>#<issue>[:aN]` and
`fix|check|continue|gate|vote|regate:<repo>#<pr>:...`), so no title is parsed. The retry
runs from `settle_merged_prs` for a PR whose ledger says `closed`.

All `EVALS` cases and `tests.test_lane_duplicate_suppression` pass with subprocess calls forbidden.
