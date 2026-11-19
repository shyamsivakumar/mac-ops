# Route mac-ops tooling alarms to the owner board, not Shyam's

The lane driver and the stall rule write mac-ops tooling items to Shyam's board (~/Code/coordinator/decisions.json): factory-zero-merge, factory-overnight-stall, and prompt-merge-MO-<n> / lane-gate-rounds-shyamsivakumar-mac-ops-<n>. mac-ops tooling is owned by the mac-ops owner session since 2026-11-18, and the Coordinator removes these items by hand every tick (last at 01:14 PT on 2026-11-19); they come back on the next tick.

Acceptance: those items are written to a mac-ops owner board file instead of decisions.json, any copy already on decisions.json is removed, and every other item still goes to decisions.json unchanged.

The repository is at `/app`. Make the change there. Do not edit test files.
