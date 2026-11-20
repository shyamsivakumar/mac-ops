# MO-752 runs

## Ticket proof command (printed value: rows returned by load_journal)

- origin/main `coordinator/bin/scorecard`: `3`
- branch `coordinator/bin/scorecard`: `1`

## 2026-11-20 merge count on a copy of events-2026-11.jsonl.bak-20261120T133425

Copy of the pre-quarantine backup (3195 rows), counted with `load_journal`, event `merged`, local and UTC date 2026-11-20:

- origin/main: 56 merged rows (3195 rows loaded)
- branch: 35 merged rows (2817 rows loaded), 35 distinct (repo, pr) pairs

The ticket expected "28, not 47". The backup was taken later in the day, so more real merges are in it. After the change every merged row is a distinct real PR.
