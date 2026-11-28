# MO-1133 proof runs

Proof command: the heredoc in the ticket body, run from the repo root (fake gh, 1 s per PR-list read, 12 repos, temp HOME, COORDQ_DIR and COORD_JOURNAL_DIR).

## origin/main (b2610e2b)
```
FAIL elapsed=17.6s rc=0 timing=None
```

## head
```
PASS elapsed=3.2s rc=0 timing=gatekeep timing: total=2.1s pr_list=2.1s
```

The timing line of the head run:
```
2026-11-27 20:47:33 gatekeep timing: total=2.1s pr_list=2.1s pr_reads=0.0s scope=0.0s proof=0.0s queue=0.0s other=0.0s
```
