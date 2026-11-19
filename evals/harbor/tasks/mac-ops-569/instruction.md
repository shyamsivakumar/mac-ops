# MO-1091 · Gate convergence rule in the lane driver's gate bar; stop after 3 failed reviews

## Goal and why
Shyam adopted Fable's convergence rule on 2026-11-18 at 09:55 PT ("go do it"): seven PRs went 5 to 6 review rounds, each round raising a new edge-case major. The coordinator's pump already reads the rule from ~/Code/coordinator/loop/gate-bar.md; the lane driver's and ticket's gate briefs come from coordinator/bin/gate_bar.py in mac-ops and do not have it.

## Stated behavior change
Add the rule to the gate bar text in coordinator/bin/gate_bar.py, word for word:
- Round 1 must list every critical and major found, not just the first.
- Round 2 and later: a new major (not raised in an earlier round of this PR) blocks only with a failing case (a concrete input or sequence with the wrong result) or inside lines changed since the last review; otherwise it is a minor under 'Left for later'.
- Earlier findings: confirm each is fixed; an unfixed earlier major still blocks.
- After 3 review rounds without PASS, the PR is re-cut into smaller PRs or brought to Shyam; no 4th review as is.
And make the lane driver stop sending fix rounds after the 3rd failed review of a PR, raising one decisions item instead.

## Context
gate_bar.py, ticket's gate brief, lane_driver.py fix-round sends in mac-ops; the pump's copy in loop/gate-bar.md is the reference text.

## Design fit
One text change in the existing bar plus one counter in the existing fix-round path.

## Scope and non-goals
In: rule text and the round cap. Out: other gate rules.

## Acceptance and proof
`ticket gate --print-brief` on an open PR shows the rule; a replay shows no 4th fix round and one decisions item. Repo check passes; `Builder check: PASS <full head sha>`.

## Must not cause
Blocking first-round majors; merging prompt text without Shyam (this PR touches gate_bar.py, so its gate stops at the verdict and Shyam merges).

## Data/secrets and stop conditions
No secrets. 15 minutes.

## Addition (2026-11-18 12:55 PT, from the Herdr session after Shyam said yes to herdr/needs-shyam)
Also add one line to the builder, reviewer and gate prompt rules (AGENT-RULES and the gate bar): "When a question is for Shyam, start it with 'Shyam,' so the board routes it to Needs you; otherwise the question goes to the coordinator."

The repository is at `/app`. Make the change there. Do not edit test files.
