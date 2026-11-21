## Goal and why

The cumulative sell reservation owner for SRW #1458 starts with its pure helpers: identity keys and the position shape. Nothing calls them yet.

This is ticket 1 of 8 cutting SRW #1579, which counts 798 code lines in 4 code files, over the cap of 150 lines and 3 files.

## Context

- Original pull request shyamsivakumar/strategy-replay-workbench#1579, head `cd544b89687a064a422a0502791d94d6dd0d7f06`. Read it with `gh pr diff 1579 -R shyamsivakumar/strategy-replay-workbench`.
- Parent ticket SRW #1577 and #1458. The branch is `t3/cumulative-sell-reservations`.

## Scope and non-goals

In:
- `thala_executor/order_identity.cjs`: the RESERVATION_* constants, `TERMINAL_ORDER_STATUSES`, `canonicalIdentity`, `reservationKey`, `sellReservationIdentity`, `executionDedupKey`, `emptyPosition`, `clonePosition`, `outstandingOf`, `soldOf`, `reservedOf`, `rowSoldOf`, `rowReservedOf` (no export yet)

Size: about 101 code lines, 1 code file.

Out: every other file of #1579. Activation of the reservation book (P54, #1464).

## Design fit

Requires: `origin/main` at `02d5a019` or later.
Provides: the pieces named above, taken from #1579 head `cd544b89` without change.

## Blocked by

Nothing.

## Acceptance and proof

1. `heavy scripts/check.sh` passes on the final head.
2. Proof command: node -e "const m=require('./thala_executor/order_identity.cjs');console.log(['canonicalIdentity','reservationKey','sellReservationIdentity','executionDedupKey'].map(k=>typeof m[k]).join())"
Expected red signature: undefined
Green on the PR head: function,function,function,function
3. `Builder check: PASS <full sha>` on its own line in the PR body.

## CI

No workflows and no GitHub Actions, ever. The local check is `scripts/check.sh`, run through `heavy`.

## Must not cause

- A change outside Scope In.
- A new default-path behavior: no production code builds a `sellReservation`.
- No weakening of an existing check.

## Data/secrets and stop conditions

No secrets and no network. Stop and report if the ticket needs more than 3 code files or about 150 code lines.

## Rollback

Revert the merge commit.

## Gate

Astra gate on the PR head, read-only, ending with the verdict line.

## Finish

Report the PR, the merged head and the check line. Close this ticket when the PR merges.
