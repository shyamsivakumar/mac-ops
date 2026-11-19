# MO-232 · ticket start refuses an issue that already has an open or merged PR

## Goal and why
Shyam, 2026-11-13 13:25 PT: "why are there so many bugs in your board sweeps?". The coordinator's ad-hoc sweep relaunched finished tickets (MO-230, MO-231, MO-208, LMW-58, LMW-65) because agent PRs say `Refs #n`, so a merged PR leaves its issue open, and `ticket start` does not check whether the issue already has a PR. The guard belongs in `ticket start`, so every caller (the sweep, the planned dispatcher refill, manual starts) gets it.

## Context
Owner: `ticket` CLI in mac-ops (installed at `~/.local/bin/ticket`); it already reads PR state for blockers (around the `closed, merged or open for a referenced issue or pull request` helper). A dispatcher board refill now in review calls the same start path.

## Scope and non-goals
In: `ticket start <repo>#<n>` refuses, with a one-line reason naming the PR, when a PR in the same repo whose body says `Refs #<n>` (or Fixes/Closes) is open, or merged after the issue's newest `Coordinator` restart comment. If merged, print `already merged via #<pr>; close the issue` and exit non-zero. No override flag.
Out: closing issues automatically, the dispatcher, coordq.

## Design fit
Inside the existing start checks next to the blocker check.

## Stated behavior change
`ticket start` refuses issues with an open or merged referencing PR. Update existing tests that encode the old behaviour only as far as needed and list every changed line.

## Acceptance and proof
`ticket start shyamsivakumar/sams-llm-wiki#160 --dry-run` refuses naming open PR #195; `ticket start shyamsivakumar/mac-ops#219 --dry-run` refuses naming PR #220 (while open); a todo issue with no PR still passes `--dry-run`.

## Must not cause
No change to labels, blockers or vendor checks. No writes in dry-run.

## Interface

The tests use these names and signatures, which the change must provide (names only, no behaviour implied):

- `coordinator/bin/ticket`: `def references_issue(body, number, repo=None)`
- `coordinator/bin/ticket`: `def referencing_pulls(repo, number)`
- `coordinator/bin/ticket`: `def is_restart_comment(body)`
- `coordinator/bin/ticket`: `def pull_guard_reasons(repo, issue)`

The repository is at `/app`. Make the change there. Do not edit test files.
