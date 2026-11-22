# MO-848 runs

## Ticket proof command

Before (copy of origin/main scorecard, same command): `KeyError: 'ticket_costs'`

After (branch): `True`

## Scorecard on 2026-11-21 (real journal, receipts and T3 database, all read-only)

Command: `python3 coordinator/bin/scorecard --date 2026-11-21`

```
  accepted_tickets: 49
  human_touches: 70
  per_ticket: {"tickets":49,"no_usage_tickets":2,"tokens":{"total":1041390986,"median":11532119,"p90":44944772},"dollars":{"total":null,"median":null,"p90":null,"tickets":0},"unpriced_threads":152}
```

All 49 accepted tickets are counted; 2 have no thread with token counts. The
builders run on Morph Ultra (flat price) and record cost 0, so dollars has no
tickets and prints null, not 0. The 152 unpriced threads have zero or absent
recorded cost. The metric was `ticket_dollars` with a `list_dollars` field and a
`tickets` key inside tokens before this round; those are gone.

## Gate findings on head d868a1ab, before and after

Fixtures: temp SQLite, temp pi session files, temp HOME, COORDQ_DIR and
COORD_JOURNAL_DIR (scratch script, not in the repo). Threads: t1 tokens 150 and
cost 0; t2 cost 2.0 and no token counters; t3 tokens 10 and cost 1.0.

| Finding | Before | After |
| --- | --- | --- |
| 1. zero cost with tokens (t1) | `unpriced_threads` decided through list pricing and the `charged` flag; dollars counted a $0 ticket (`dollars.tickets` 1, total 0.0) | `unpriced_threads` 1, `dollars.tickets` 0, tokens total 150 |
| 2. $2 cost, no token counters (t2) | `unpriced_threads` 1, `dollars` total 2.0 only through `billed_known`; thread dropped from `usage` | `dollars` total 2.0, `unpriced_threads` 0, `no_usage_tickets` 1 |
| 3. accepted ticket without receipts (3 and 4 accepted, receipts only for 3) | only tickets with receipts iterated; no `tickets` or `no_usage_tickets` field | `tickets` 2, `no_usage_tickets` 1 |
| 4. receipts file holding `null` | `AttributeError: 'NoneType' object has no attribute 'items'` in ticket_costs | metric is `unknown` (listed under `unknown metrics`, cost.per_ticket) |
