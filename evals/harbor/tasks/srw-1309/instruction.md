# Expose read-only durable sell recovery evidence (Refs #1220)

Refs #1220. Refs #892. Refs #490.

Expose getSellRecoverySnapshot({tradeId}) beside getCloseEvidence on the THALA broker facade. It returns copied durable records and complete replacement groups with frozen quantity, cumulative fills, send uncertainty and conservative terminal evidence. Unknown identity fails closed.

Fix round 1 on this branch:
- The executor change, the registration change and the canonical replacement change are reverted to origin/main. Sell submission and durable registration behave exactly as on main, and no new rejection condition was added. The ticket (Refs #1220) excludes executor behavior changes and ledger mutation, and it carries no amendment that allows them, so the ticket decides and the earlier continuation-authorization claim is withdrawn.
- Durable trade identity is now resolved read-only from the canonical client order id grammar thala-<tradeId>-exit-<ref>-L<leg>-<phase>, interpreted by the new canonical predicate paper_external_order_ownership.sellIdentity. The ledger is never written and the reader resolves nothing outside the full grammar, so legacy and hashed ids stay unresolved instead of being guessed.
- evidence/SRW-1173/decisions.md was rewritten to match what the branch actually does.

Head: 0012e15c175dafba15d46dd0edac3f8e56f78d46

Builder check: PASS 0012e15c175dafba15d46dd0edac3f8e56f78d46

Exact-head srw/agent-check reports success on 0012e15c175dafba15d46dd0edac3f8e56f78d46. scripts/check.sh was not run, per the repository rules for this repo.

Scoped checks: timeout 300 node --check alpaca_paper_execution.js; timeout 300 node --check paper_external_order_ownership.js; timeout 300 node --check thala_v2_executor.js; timeout 300 node --check evidence/SRW-1173/sell-recovery-snapshot.probe.cjs; timeout 300 git diff --check. All exit 0.

Sanitized facade probe: timeout 300 node evidence/SRW-1173/sell-recovery-snapshot.probe.cjs
Output: PASS restart identity, complete chain, old rejected uncertainty, terminal distinction, mutation isolation, fail-closed identity; POSTs=0 writes=0
It runs the real facade over sanitized durable state and records restart identity, original and replacement uncertainty, old rejected records, mutation isolation, zero POST and zero write evidence, fail-closed identity, and the executor-facing thalaBroker().getSellRecoverySnapshot call. It is a temporary sanitized probe, not the B5 acceptance proof.

## Left for later
B4 consumer integration of this evidence, B5 full acceptance (owned by the B5 ticket), legacy client order ids outside the canonical grammar, and the Coordinator exact-head gate.

The repository is at `/app`. Make the change there. Do not edit test files.
