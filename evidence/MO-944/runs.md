# MO-944 runs

Proof command is the one in the ticket, run from the repo root with a temporary HOME.

## Ticket proof on origin/main (red)
```
AttributeError: module 'cq' has no attribute 'scope_refusal'
exit 1
```

## close-evidence eval with the new cases on origin/main code (red)
```
AttributeError: module 'fixture_coordq' has no attribute 'scope_refusal'
exit 1
```

## Ticket proof on the branch (green)
```
exit 0
```

## close-evidence eval on the branch, flat copy of coordinator/bin and coordinator/overnight (green)
```
close-evidence OK
exit 0 (prints close-evidence OK)
```

## After review fixes (merged origin/main bdf5cf93)

Ticket proof on the branch:
```
exit 0
```

close-evidence eval in place (coordinator/overnight) and from a flat copy: both print OK (in place OK, close-evidence OK).

Read-only run_check on real PRs (no queue, no card):
```
PR 941 issue 939 merge 98ce6cfb
   scope pass  - every changed file is inside the ticket's stated scope
   proof file pass  - evidence/MO-939/check-proof.md is present
  scope_refusal items: []
PR 921 issue 917 merge d5efd3f8
   scope fail  - outside the ticket's stated scope: coordinator/overnight/selftest.py
   proof file pass  - evidence/MO-917/check-proof.md is present
  scope_refusal items: ['scope']
```

## After second review (merged origin/main, drop_scope_card holds the head on a failed removal)

Ticket proof: exit 0. close-evidence eval in place: "in place OK"; flat copy: "close-evidence OK". New eval cases: failed removal gives False twice then True; dry run with a failed issue read leaves the queue unchanged; ApiBudgetExhausted passes through.
