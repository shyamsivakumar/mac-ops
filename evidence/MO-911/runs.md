# MO-911 runs

## Proof on origin/main (hourly_selftest.py from origin/main)
```
AssertionError: ['old', 'overnight-selftest']
```

## Proof on the head
```
exit 0
```

## Fixture hourly_selftest_fixture on the head
Covers a failing suite adding exactly its own card beside a card raised during the run, an unparseable board left byte-identical with state recording board=failed, and a missing board created with only the card.
```
decisions board not updated: failed
fixture ok
```

Temp dirs and a temp COORD_JOURNAL_DIR only. If the board write fails, the state file records last_run, passed and board ("failed"); stderr names it. ALARM does not match OWNER_IDS, so the card stays on the decisions path. A pass with no card on the board writes nothing (a missing board is no longer created empty).
