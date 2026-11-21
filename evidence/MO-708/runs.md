# MO-1133 runs

Replay rows: ten stage:started tickets (649, 633, 614, 611, 610, 607, 605, 591, 543, 530) and #673 to #681 in stage:todo, no live mac-ops thread.
Open PRs: the set open at 2026-11-19T22:50Z from the repository history (535, 545, 566, 579, 582, 595, 598, 665, 670; refs 533, 514, 548, 576, 504, 505, 596, 662, 663, 671). PR 632 (refs 530) merged at 22:57Z and PR 682 (refs 675) opened at 22:53Z, so the two PRs that would make the repo busy are excluded.

## Before: coordq at 687eac75^ (before #712), lane_candidates on the replay rows
```
selected: []
```

## After: refill-busy case on this branch (board_candidates, real coordq)
```
refill-busy PASS: replay selects [673]; log names the ten stale tickets; live thread selects []; open PR refing #675 selects []
```
