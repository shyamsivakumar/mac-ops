# MO-988 runs

## Ticket proof (HOME=/nonexistent, run from the checkout)

On origin/main code: exit 1

```text
p.Refuse: --alongside needs a Scope In that names a readable file
```

On the branch: exit 0

## Eval cases (refill_busy in coordinator/overnight/selftest.py, temp COORDQ_DIR and COORD_JOURNAL_DIR)

With origin/main coordinator/bin/ticket: exit 1

```text
fixture_ticket.Refuse: --alongside needs a Scope In that names a readable file
```

With the branch ticket: exit 0 (refill_busy PASS)

## Live open issues, read only (gh issue list, old and new code loaded side by side)

```text
strategy-replay-workbench open 60 scope_files identical 60 of 60 | stage:todo 43 started 2 | todo with names old/wide 28 36 | exact-name shared pairs old/wide 92 96
  gained pairs [(1930, 2529, 'scripts/srw1461_exit_drill_proof.cjs'), (2529, 1930, 'scripts/srw1461_exit_drill_proof.cjs'), (2545, 2546, 'scripts/srw1445_kill_entries_recovery_proof.cjs'), (2546, 2545, 'scripts/srw1445_kill_entries_recovery_proof.cjs')]
mac-ops open 16 scope_files identical 16 of 16 | stage:todo 0 started 0 | todo with names old/wide 0 0 | exact-name shared pairs old/wide 0 0
  gained pairs []
```

scope_files without wide is byte-identical on every open issue body, so check_body, the file cap and every scope_overlap call without --alongside (which uses plain name equality) give the same results. The gained pairs are the tickets that now overlap with --alongside: two SRW pairs that share a proof script.
