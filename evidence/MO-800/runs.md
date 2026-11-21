# MO-800 runs

Proof script adapted from the ticket shape: settle_merged_prs called twice with three fake merged PRs (Refs to snapshot ticket, no Refs, Refs to unknown ticket), temp COORDQ_DIR and COORD_JOURNAL_DIR, gh stubbed.

Before (origin/main c497f8fd):
```
first call rows: 1 ticket: [None]
second call new rows: 0
```

After (branch head):
```
first call rows: 3 ticket: ['5', None, None]
second call new rows: 0
```
