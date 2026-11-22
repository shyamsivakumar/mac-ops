# MO-849 runs

## Ticket proof command

Command: `python3 -c "import sys; sys.path.insert(0,'coordinator/bin'); import prompt_paths as p; print(p.prompt_scan(['coordinator/bin/coordq']) == p.LOOP_HOLD)"`

origin/main (673950b8):
```
AttributeError: module 'prompt_paths' has no attribute 'LOOP_HOLD'
```

branch:
```
True
```

## Lane stub run

Run from the worktree root: `python3 evidence/MO-849/lane_stub_proof.py`. `gh` and the merge call are stubbed, the decisions board, COORDQ_DIR, COORD_JOURNAL_DIR and HOME are temp. Case 1 is one head passed twice, then labelled.
```
   journal: merge_held loop code hold
#1 ['coordinator/bin/coordq'] labels=[]
   -> skip #1: gate PASS, loop code change, Shyam merges
   merge calls=0 cards=['prompt-merge-MO-1']
#1 ['coordinator/bin/coordq'] labels=[]
   -> skip #1: gate PASS, loop code change, Shyam merges
   merge calls=0 cards=['prompt-merge-MO-1', 'prompt-merge-MO-1']
#1 ['coordinator/bin/coordq'] labels=['merge:human-ok']
   -> merge call reached
   merge calls=1 cards=['prompt-merge-MO-1', 'prompt-merge-MO-1']
#2 ['README.md'] labels=[]
   -> merge call reached
   merge calls=1 cards=['prompt-merge-MO-1', 'prompt-merge-MO-1']
   journal: merge_held prompt hold
#3 ['skills/x/SKILL.md', 'coordinator/bin/coordq'] labels=['merge:human-ok']
   -> skip #3: gate PASS, prompt change, Shyam merges
   merge calls=0 cards=['prompt-merge-MO-1', 'prompt-merge-MO-1', 'prompt-merge-MO-3']
board mac-ops-owner.json ['prompt-merge-MO-1', 'prompt-merge-MO-3']
```

## Existing module

`python3 -m unittest tests.test_prompt_paths` (temp COORDQ_DIR and COORD_JOURNAL_DIR): 77 tests OK on the branch. The sample path `coordinator/bin/ticket` in that module became `tools/ticket` (and `bin/ticket` in the tree-diff case), because it now correctly reads as loop code; no assertion was loosened.
