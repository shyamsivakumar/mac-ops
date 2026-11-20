# MO-505 gate fixes

Doc: `docs/loop-change-trials.md` (from #595, branch t3/loop-change-evaluation-design).

| Finding | Fix (line in the doc) |
| --- | --- |
| Borderline re-ran stage 2 after a failed 40-task result | Two Stages section: "Stage 2 is terminal" paragraph. Claim A condition 1: "A fail at stage 2 is final." Flowchart: stage 2 goes to its own accept check J, which ends at merge or revert, with no edge back to F. |
| Claim B and the sign-test p-value contradicted (p=0.75 led to both decisions) | Borderline paragraph: "The p-value rule belongs to claim A only", and the p = 0.75 example is decided by claim B conditions alone. Claim B: "decided at stage 1 and has no stage 2", so no stage 2 bar applies to it. Stage 2 text no longer mentions claim B. |
| Stage 2 count wrong (60 vs 120 per arm) | "Runs per arm" bullet: 60 at stage 1, 120 at stage 2. Outcome counts line gives both. Claim B condition 1 now uses 3 of 60 only. |
| Other: claim B allowed an optional 40-task confirm that conflicted with the terminal rule | Removed; claim B is stage 1 only. |

## Arithmetic

- Stage 1 per arm: 20 x 3 = 60. Stage 2 per arm: 40 x 3 = 120.
- Both arms: stage 1 = 120, stage 2 = 240. A/A over 20 tasks = 60; extension over 20 new tasks = 60.
- Stage 2 confirmation adds 240 + 60 = 300 runs x 8 min = 2400 min = 40 h (unchanged).
- Stage 1 with fresh A/A: 120 + 60 = 180 runs x 8 min = 24 h (unchanged).
- Claim B allowance: 5% x 60 = 3 runs.
- p = 0.75 for 1 up / 1 down: P(X>=1 of 2) = 3/4. Table values re-derived by exact binomial and match.
