# MO-848 runs

## Ticket proof command

Before (origin/main scorecard):

    KeyError: 'ticket_costs'

(origin/main scorecard run with the same command, path swapped to a copy of origin/main:coordinator/bin/scorecard)

After (branch):

    True

## Scorecard on 2026-11-21 (real journal, receipts and T3 database, read-only)

  human_touches: 70
  ticket_dollars: {"total":null,"median":null,"p90":null,"tickets":0,"unpriced_threads":152}

All 63 accepted tickets' builder and gate threads that day ran on pi aliases that report cost 0 or on drivers with no pi file, so none is priced. The metric prints null with the unpriced thread count, never 0.

## ticket_costs on real priced tickets (tickets with a strategy-replay-workbench builder receipt, journal rows empty)

    259 {'total': 33.52, 'median': 0.24, 'p90': 1.47, 'tickets': 59, 'unpriced_threads': 328}

Fields: accepted tickets passed in, then total dollars, median, p90, tickets priced, threads left unpriced.
