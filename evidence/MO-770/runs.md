# MO-770 runs

## Ticket proof command

Before (coordq of the base, #769 head):
```
KeyError: 'write_replay'
```

After (this branch):
```
['head.txt', 'proof.txt', 'ticket.md']
```

## Gatekeep run (evidence/MO-770/gatekeep_proof.py, temp COORDQ_DIR, COORD_JOURNAL_DIR, HOME, fake PR data)

Before (base coordq): both heads queued with no proof, no card:
```
queued gate:o/on#1:49361f2b1d0684dd4695afe141949902d26276fb reviewer i m
queued gate:o/on#2:333aff1b6d73be4e6fded1fea7c05dd8000476de reviewer i m
queued gate:o/off#3:cccccccccccccccccccccccccccccccccccccccc reviewer i m
    print("card:", [i["id"] for i in json.load(open(root + "/mac-ops-owner.json"))["items"]])
FileNotFoundError: [Errno 2] No such file or directory: '/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/gk770-9netx_xx/mac-ops-owner.json'
```

After: head 1 (ticket opened with proof red, green) gated with the record, head 2 (red) no gate and one card, run 2 makes no new proof run, flag-off repo (#3) queued unchanged. Head 4 is a flag-on repo whose ticket has no `proof: red` ticket_opened row: gated, state legacy, no proof run (runs stay at 2), no card:
```
queued gate:o/on#1:40682d5e1bf67969b85937e375dda749de4467c9 reviewer i m
queued gate:o/off#3:cccccccccccccccccccccccccccccccccccccccc reviewer i m
queued gate:o/on#4:cccccccccccccccccccccccccccccccccccccccc reviewer i m
--- run 1: proof runs so far 2
--- run 2: proof runs so far 2
queued t1 | proof in brief: True
queued t3 | proof in brief: False
queued t4 | proof in brief: False
card: ['proof-MO-2']
replay: ['head.txt', 'proof.txt', 'ticket.md']
proof_run rows: ['"kind":"gate","model":null,"arm":null,"data":{"state":"green","sha":null,"manifest":null}}', '":"gate","model":null,"arm":null,"data":{"state":"unresolved","sha":null,"manifest":null}}', 'kind":"gate","model":null,"arm":null,"data":{"state":"legacy","sha":null,"manifest":null}}']
legacy head 4 (no red opened row): legacy | proof runs 2
proofHeads: {'o/on#1': 'green', 'o/on#2': 'unresolved', 'o/on#4': 'legacy'}
```

Note: the ticket proof command is the expected shape; it ran as written.

## Fetch retry (evidence/MO-770/fetch_retry_proof.py, temp COORDQ_DIR, COORD_JOURNAL_DIR, HOME, fake PR data)

PR 1 fetch fails once then works; PR 2 fetch always fails. Before this fix a failed fetch cached `unresolved` on tick 1 and the head was never retried. After: PR 1 is gated green on tick 2; PR 2 is retried on ticks 1 to 3 (3 fetch attempts), cached unresolved with one card `proof-MO-2` on tick 3, and ticks 4 and 5 make no more attempts.
```
tick 1: fetch attempts {1: 1, 2: 1} | queued [] | proofHeads {} | cards []
queued gate:o/on#1:91d8bfe64d2e9b2024f3e6c4fc0d7040d400456f reviewer i m
tick 2: fetch attempts {1: 2, 2: 2} | queued ['t1'] | proofHeads {'o/on#1': 'green'} | cards []
tick 3: fetch attempts {1: 2, 2: 3} | queued ['t1'] | proofHeads {'o/on#1': 'green', 'o/on#2': 'unresolved'} | cards ['proof-MO-2']
tick 4: fetch attempts {1: 2, 2: 3} | queued ['t1'] | proofHeads {'o/on#1': 'green', 'o/on#2': 'unresolved'} | cards ['proof-MO-2']
tick 5: fetch attempts {1: 2, 2: 3} | queued ['t1'] | proofHeads {'o/on#1': 'green', 'o/on#2': 'unresolved'} | cards ['proof-MO-2']
proofFetch: {'o/on#1': (1, 'cannot fetch the head: fatal: unable to '), 'o/on#2': (3, 'cannot fetch the head: fatal: unable to ')}
```
