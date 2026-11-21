# MO-1120 · Gatekeep honours the 3-review cap; the round decision re-checks the board

## Goal and why

Gatekeep ignores the 3-review cap. SRW#1338 has been gated 10 times (ledger `rounds:...#1338` count 10, 10 distinct `queued gate:...#1338:<head>` lines in `gatekeep.log`, #11410 queued for 3b7671c1). The lane answers "no fix round, the decisions item is on the board" for #1333 and #1338, but `decisions.json` and `mac-ops-owner.json` hold no card for either: `gate_round_decision` trusts its own `rounds-decision:` ledger key and never checks the board.

Fix: gatekeep does not queue a gate for a PR at or over the round cap. `gate_round_decision` re-raises the item when the ledger key is set but the card is missing. Replay both.

## Context

- `coordinator/bin/coordq` gate candidates (the generator that ends around line 1720) yields a `candidate` for every non-draft PR whose head has a passing check and no gated record. It never asks how many failed rounds the PR already has, so each new head is queued again.
- `coordinator/overnight/lane_driver.py:49` sets `GATE_ROUND_CAP = 3`. `gate_rounds_used` (around line 760) is the lane's own cap test, and `failed_reviews` (line 675) reads `rounds:<repo>#<n>` from the ledger.
- `gate_round_decision` (line 733) returns "no fix round, the decisions item is on the board" whenever `rounds-decision:<repo>#<n>` is in the ledger, and only calls `alarms.migrate_stale`. It never checks that the card is on the board, so a card that was withdrawn or never written is not re-raised.
- `clear_gate_round_decision` (around line 770) is the matching removal when a PR passes.

## Scope and non-goals

In:
- `coordinator/bin/coordq`: gatekeep skips a PR at or over the round cap and reports the skip, so no gate is queued for it.
- `coordinator/overnight/lane_driver.py`: `gate_round_decision` re-raises the item when the ledger key is set but the card is missing from the board.
- `coordinator/overnight/selftest.py`: a replay of a PR at the cap (no gate queued) and a replay of a ledger key with no card (item re-raised).
- `evidence/MO-676/check-proof.md`: the check proof for the final head.

Out:
- No change to `GATE_ROUND_CAP` or to how a failed review is counted.
- No change to the text of the decisions item.
- No cleanup of old cards (that is #677).

## Design fit

The lane owns the round count and the decisions board; gatekeep must read the same count instead of keeping its own, so it stays one rule. Reading the board before trusting the ledger key keeps `gate_round_decision` correct when the board and the ledger disagree.

Requires: `origin/main` at `6d35521a` or later.
Provides: gatekeep queues no gate for a PR at or over the round cap, and a PR whose decisions card is missing gets it raised again.

## Acceptance and proof

1. `python3 coordinator/overnight/overnight selftest` passes with two new replay cases: a PR with 3 failed rounds yields no gate candidate in gatekeep, and a ledger with `rounds-decision:` set but no card on the board raises the item again.
2. The replay output shows the SRW#1338 shape (count 10) skipped, not queued.
3.

Device, handset and live-service testing is waived (Shyam 2026-11-14: "no testing is needed lets just finish backlog building everything").

## Must not cause

- No gate queued for a PR under the cap that was queued before.
- No second decisions card for a PR whose card is on the board.
- No change to the retry-on-no-verdict path.
- No weakening of an existing test to make the check pass.

## Interface

The tests use these names and signatures, which the change must provide (names only, no behaviour implied):

- `coordinator/bin/coordq`: `def lane_ledger()`

The repository is at `/app`. Make the change there. Do not edit test files.
