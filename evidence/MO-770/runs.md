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

After: head 1 (green) gated with the record, head 2 (red) no gate and one card, run 2 makes no new proof run, flag-off repo (#3) queued unchanged:
```
queued gate:o/on#1:8bcf0a962163660e8a2d6efd598159e0b3c179d4 reviewer i m
queued gate:o/off#3:cccccccccccccccccccccccccccccccccccccccc reviewer i m
--- run 1: proof runs so far 2
--- run 2: proof runs so far 2
queued t1 | proof in brief: True
queued t3 | proof in brief: False
card: ['proof-MO-2']
replay: ['head.txt', 'proof.txt', 'ticket.md']
proof_run rows: ['"kind":"gate","model":null,"arm":null,"data":{"state":"green","sha":null,"manifest":null}}', '":"gate","model":null,"arm":null,"data":{"state":"unresolved","sha":null,"manifest":null}}']
proofHeads: {'o/on#1': 'green', 'o/on#2': 'unresolved'}
```

Note: the ticket proof command is the expected shape; it ran as written.
