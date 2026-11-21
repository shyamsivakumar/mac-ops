# MO-830 proof runs

## Ticket proof command, before (origin/main, live receipts)

    /opt/homebrew/bin/python3 -c "import json; r=json.load(open('.../queue/dispatch-receipts.json')); print([k for k in r if k.startswith('ticket:shyamsivakumar/strategy-replay-workbench#1580:')])"
    []

The live file is not edited from this branch (builder rules), so the key appears
there when `coordq fix` or the next `coordq gatekeep` runs from the merged code.

## Selftest case builder-receipt (temp COORDQ_DIR and COORD_JOURNAL_DIR)

Before, on origin/main coordq:

    before: FAIL AttributeError module 'old_coordq' has no attribute 'record_builder'

After, on this branch:

    after: PASS

The case checks that a thread found by title is written once as
`ticket:<repo>#1580:a1`, that a ticket with a receipt (a2) is returned without a
lookup, that a second call does no second lookup, and that an unknown builder
writes nothing.
