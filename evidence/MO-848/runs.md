# MO-848 runs

## Ticket proof command

Before (copy of origin/main scorecard, same command): `KeyError: 'ticket_costs'`

After (branch): `True`

## Scorecard on 2026-11-21 (real journal, receipts, T3 database and pi rates, all read-only)

```
  accepted_tickets: 49
  human_touches: 70
  ticket_dollars: {"dollars":{"total":null,"median":null,"p90":null,"tickets":0},"list_dollars":{"total":null,"median":null,"p90":null,"tickets":0},"tokens":{"total":1041390986,"median":11532119,"p90":44944772,"tickets":47},"unpriced_threads":152}
```

The scorecard counts 49 accepted tickets for 2026-11-21. Tokens are present for 47 of them (about 1.04 billion tokens, cache reads dominate). Billed dollars and list dollars are both null: the builder threads ran on morph-dsv41flash (and morph-dsv41flash-1017 in 5 cases), which report cost 0 and have no cost block in ~/.pi/agent/models.json or models-store.json, so list pricing has no rates to use. 152 threads are unpriced (no usage or no model rates). My earlier count of 63 came from my own query that counted closes on both 2026-11-21 and 2026-11-22 (49 + 14); the scorecard counts one day.

That billed-dollars line was the gate finding on this head: a ticket with an
observed zero charge was dropped from the distribution. After the fix the same
run reports `"dollars":{"total":0.0,"median":0.0,"p90":0.0,"tickets":47}`.
See `check-proof.md` for the before and after lines.

## ticket_costs on real priced tickets (strategy-replay-workbench builder receipts, journal rows empty; scorecard at `60564179`, before this fix)

```
259 {"dollars": {"total": 33.52, "median": 0.24, "p90": 1.47, "tickets": 59}, "list_dollars": {"total": 25.97, "median": 0.24, "p90": 1.17, "tickets": 58}, "tokens": {"total": 7964366186, "median": 23328780, "p90": 75434687, "tickets": 203}, "unpriced_threads": 330}
```
