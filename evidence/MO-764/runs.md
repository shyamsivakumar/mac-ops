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

## gatekeep with fake PR data (temp COORDQ_DIR and COORD_JOURNAL_DIR)

PR 1 has 100 code lines, PR 2 has 200, PR 3 has 800. Each also has a 5000-line evidence markdown file that does not count.
`gate_candidates` is replaced by a fake that yields events carrying `size`; `cmd_gatekeep` itself is real.

```
queued gate:o/r#1:aaaa... reviewer i m
queued gate:o/r#2:aaaa... reviewer i m
recut #3
journal: gate_queued ok 1 | gate_queued over_cap 2 | recut 3
```

Two gates are queued (over_cap is only tagged), PR 3 queues no gate and journals `recut`.
