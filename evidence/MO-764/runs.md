# MO-764 runs

Proof command (ticket), run in the worktree.

## Before (origin/main coordq)

```
KeyError: 'size_class'
```

## After (branch)

```
ok over_cap recut
```

## gatekeep with fake PR data (temp COORDQ_DIR, COORD_JOURNAL_DIR, HOME and decisions board)

PR 1 has 100 code lines, PR 2 has 200, PR 3 has 800. Each also has a 5000-line evidence markdown file that does not count.
The real `cmd_gatekeep` and `gate_candidates` run; only the GitHub reads, `gate_request` and the login are faked.
PR 3 gets a new head before run 3.

```
run 1: files calls=3 journal rows=[('gate_queued', 'ok', None, None), ('gate_queued', 'over_cap', None, None), ('recut', None, 800, 1)] cards=['recut-MO-3'] alarm rows=1
run 2 same heads: files calls=0 journal rows=[('gate_queued', 'ok', None, None), ('gate_queued', 'over_cap', None, None), ('recut', None, 800, 1)] cards=['recut-MO-3'] alarm rows=1
run 3 new head on PR 3: files calls=1 journal rows=[('gate_queued', 'ok', None, None), ('gate_queued', 'over_cap', None, None), ('recut', None, 800, 1), ('recut', None, 800, 1)] cards=['recut-MO-3'] alarm rows=2
```

Run 1 queues PR 1 (ok) and PR 2 (over_cap), journals `recut` once for PR 3 with its counted lines and files, and raises one card `recut-MO-3` (id matches OWNER_IDS, so it lands on the mac-ops owner board). Run 2 on the same heads makes 0 files calls, writes 0 new rows and leaves 1 card. Run 3 judges the new head of PR 3 again (1 files call, one more `recut` row) and the card id stays one.
