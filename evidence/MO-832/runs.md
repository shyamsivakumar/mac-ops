# MO-832 proof runs

## Ticket proof command, origin/main (red)
```
/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.eREGOsKwIW/Library/Logs/coordinator
```

## Ticket proof command, head (green)
```
/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.SVFp1msahk/.local/state/coordinator/journal
```

## Temp-HOME migration run
```
run 1:
/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.zvUXsv6mKD/.local/state/coordinator/journal ['events-2026-11.jsonl', 'events-backfill.jsonl']
run 2 (new file has an appended row; must stay):
/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.zvUXsv6mKD/.local/state/coordinator/journal ['events-2026-11.jsonl', 'events-backfill.jsonl']
{"a":1}
{"c":3}
old folder after:
events-2026-11.jsonl
events-backfill.jsonl
tick.log
run 3 after removing events-backfill from new (new still has events: copies nothing):
/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.zvUXsv6mKD/.local/state/coordinator/journal ['events-2026-11.jsonl']
```

## Pre-existing destination is left untouched (per-file guard, os.link)
```
events-2026-11.jsonl old
events-backfill.jsonl KEEP
```

## Second-writer race: destination month file already exists with a new row (selftest `journal-migration`)
Old folder has events-2026-11 (a, b) and events-backfill (z); new folder already has events-2026-11 (b, c) from a writer that got there first. Migration runs twice.
```
origin PR head 807b8fe9 journal.py:
AssertionError: expected ['{"a":1}', '{"b":2}', '{"c":3}'], got ['{"b":2}', '{"c":3}']

fix (flock on .migrate.lock, merge without duplicates, .migrated written last):
journal-migration PASS
```
