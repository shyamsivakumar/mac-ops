# MO-834 runs

## Proof command on origin/main (before)
```
AttributeError: module 'lane_driver' has no attribute 'cap_waived'
```

## Proof command on the branch (after)
```
True
```

## gate-round-cap eval (extended: labelled PR gets a fix round, no card, card withdrawn, gate_cap_waived journaled once; unlabelled PR unchanged; card has 3 options)
Run in a temp COORDQ_DIR, COORD_JOURNAL_DIR and HOME, with the extended selftest.

On origin/main code:
```
    raise AssertionError(f"expected {expected!r}, got {actual!r}")
AssertionError: expected 3, got 2
```
On the branch:
```
gate_round_cap OK
```
