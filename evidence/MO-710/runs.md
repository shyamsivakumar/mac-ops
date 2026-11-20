# MO-710 runs

## Before: models.py from da70cd7d (before #709), new case run
```
FAIL provider-until: expected False, got True
```

## After: current models.py (origin/main with #709)
```
29
PASS provider-until
not-due
```

Replays in provider-until: past until not blocked; future until blocked; manual block stays; unknown-model entry pruned. Each asserted with exact().
