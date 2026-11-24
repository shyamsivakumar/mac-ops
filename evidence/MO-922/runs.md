# MO-922 runs

## Ticket proof command (see issue #922)

Red on origin/main 820e81b8 (module absent):

    ModuleNotFoundError: No module named 'inbox_outbox'

Green on the branch: exit 0.

## inbox eval of coordinator/overnight/selftest.py

The eval now calls outbox_cases(). Without coordinator/bin/inbox_outbox.py (origin/main state):

    ModuleNotFoundError: No module named 'inbox_outbox'

On the branch: `inbox ok`. Cases: shadow is on unless COORD_INBOX_SHADOW is exactly 0; unknown kind and none without a reason raise; shadow drain calls no sender and changes nothing; a sent row is not sent again; a late finish after reap never marks sent (hc_send stays unknown, sender called once; coordq_send is claimed again with a new attempt and the stale finish is refused); coordq_send is requeued twice then failed on the third try.

## Review fixes on top of ba8a82be

drain now claims, sends and finishes one row at a time in id order up to `limit`, with a fresh lease per row from `clock` (default: constant `now`), and a failed row is skipped for the rest of the pass. `none` with a blank reason raises. New eval cases: a BaseException from the sender on the first of three hc_send rows leaves the other two pending and the next pass sends each once; `none` with "  " raises.

Red with ba8a82be's inbox_outbox.py: `AssertionError: none` (blank reason accepted). Green on the branch: `inbox ok`; the ticket proof command exits 0.
