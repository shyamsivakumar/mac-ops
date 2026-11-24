# MO-922 runs

## Ticket proof command (see issue #922)

Red on origin/main 820e81b8 (module absent):

    ModuleNotFoundError: No module named 'inbox_outbox'

Green on the branch: exit 0.

## inbox eval of coordinator/overnight/selftest.py

The eval now calls outbox_cases(). Without coordinator/bin/inbox_outbox.py (origin/main state):

    ModuleNotFoundError: No module named 'inbox_outbox'

On the branch: `inbox ok`. Cases: shadow is on unless COORD_INBOX_SHADOW is exactly 0; unknown kind and none without a reason raise; shadow drain calls no sender and changes nothing; a sent row is not sent again; a late finish after reap never marks sent (hc_send stays unknown, sender called once; coordq_send is claimed again with a new attempt and the stale finish is refused); coordq_send is requeued twice then failed on the third try.
