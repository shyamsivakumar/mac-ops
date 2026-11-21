## Ticket proof command, before (origin/main)
```
KeyError: 'gate_allowed'
```
## After (branch)
```
False True True
```

## Gatekeep run (evidence/MO-771/gatekeep_proof.py)
```
no proof record for o/on#2
--- proof_required=True run 1: proof runs 2, queued ['t1', 't3', 't4']
no proof record for o/on#2
--- proof_required=True run 2: proof runs 2, queued ['t1', 't3', 't4']
--- proof_required=False run 1: proof runs 2, queued ['t1', 't3', 't4', 't2']
--- proof_required=False run 2: proof runs 2, queued ['t1', 't3', 't4', 't2']
card: ['proof-MO-2']
gate_skipped rows: 1
proofHeads: {'o/on#1': 'green', 'o/on#2': 'unresolved', 'o/on#4': 'legacy'}
```
