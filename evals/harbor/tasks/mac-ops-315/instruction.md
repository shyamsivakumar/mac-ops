# MO-269 · A docs-only merged PR does not count as delivering its ticket

## Goal and why
`ticket start` refuses a ticket as "already merged via #N" whenever any merged PR says `Refs #<ticket>`. SRW #472 was refused forever because docs-only PR #1038 (`evidence/SRW-761/plan.md`) referenced it while the implementation stayed on an unmerged branch.

## Context
`coordinator/bin/ticket`, the already-merged refusal (search for `already merged via`). The refill and the board both rely on it.

## Scope and non-goals
In: count a merged PR as delivering the ticket only when it changed at least one file outside `evidence/`, `docs/` and `*.md`, or when the ticket carries a gate `VERDICT: PASS. Merged via #N` close comment. Otherwise report `merged PR #N changed only docs; not treated as delivery` and let the start proceed. Out: no change to other refusals.

## Design fit
The ticket CLI owns start refusals; this narrows one rule in place.

## Acceptance and proof
A ticket whose merged PR changed code is still refused.

## Must not cause
A second start of a ticket that really merged.

## Interface

The tests use these names and signatures, which the change must provide (names only, no behaviour implied):

- `coordinator/bin/ticket`: `def pull_files(repo, number, changed_files=None)`
- `coordinator/bin/ticket`: `def pull_guard_reasons(repo, issue, notices=None)`

The repository is at `/app`. Make the change there. Do not edit test files.
