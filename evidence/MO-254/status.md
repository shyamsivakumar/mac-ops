# MO-254 / #277 delivery

Fresh base: origin/main 580535a0b096161fe54e0f60b718b98ed79aad7a.
The older partial patch is preserved in the local stash. Main replaced its
proposed dispatcher with lane_driver, so this delivery extends that active path.

Implemented shared PR classification, draft/conflict/link/check/fix actions,
missing-builder reasons, receipt/title builder lookup, completion reminder then
fresh gate recovery, queue-locked action dedupe, and board state summaries.
Removed direct merge/close from the PR handler. Gate completion keeps the standing
Astra-first reviewer rules. No live sends or runtime installation were performed.

Decision: regate and regate-fresh are separate phase keys. Otherwise once-per-head
dedupe would prevent the explicitly requested second-stage recovery. Removed the
old additional continue message for an already-sent fix: once per head wins.

In-session review: inspected the active handler, shared classifier, queue-lock
boundary, dry-run branches and board projection. Corrected failed-check priority,
exact-head matching, duplicate continuation sends and dry-run needs-you writes.
No new code comments were added; no-comments diff pass has no deletions. Deslop
pass removed duplicate actionKey assignment; no dependencies or unrelated cleanup.

Verification: Python compilation and git diff --check pass. Required
python3 scripts/mac_ops_fast_check.py returns FAIL. Unmodified send-integrity
expects the old coordq command shape; gate-pipeline expects lane merges and
immediate fresh-gate recovery; no-parking expects an extra same-head continuation.
These failures are caused by intentional changed contracts, not claimed unrelated.
Correction: the branch had deleted gate-brief assertions from consolidation-guard. The finish pass restored those assertions from origin/main. Final PR check line records FAIL.

Left for later: reconcile existing proof expectations with the new contract;
stubbed repeated-cycle/new-head coverage and live board counts are not collected.
Device/live/owner testing is waived by the coordinator. No canonical wiki update:
the current instruction forbids editing another repository; usage is documented
in coordinator/overnight/README.md here.
