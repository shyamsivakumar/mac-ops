Historical stop receipt, superseded by the coordinator continuation and delivery.md.

# MO-1006 bounded scope stop

Refs #345. Run: ticket:shyamsivakumar/mac-ops#345:a1.

Prerequisite verified after `git fetch origin main`: origin/main is
8d6c70df (abbreviated; reproduce full identity with `git rev-parse origin/main`).
Commit subject: MO-1005: Detect stopped builders and idle coordinator lanes (#351).
The native blocked-by endpoint for #345 includes closed issue #344.
The clean builder branch was fast-forwarded to this prerequisite.

Source inspection: coordinator/bin/coord-watch main performs one cycle and
releases its state lock before printing. Its persisted state contains github,
items, events and idle. It does not retain runtime start identities or log
inode/offset information. install_coordinator.py already lists coord-watch in
BIN_FILES. Existing mapping therefore needs verification rather than a duplicate.

Stop: the requested persistent loop, runtime timestamp contract, incremental
log reader with rotation and partial-line handling, shutdown/backoff handling,
fake-clock command proofs, temporary-HOME installation proof, full checks and
one independent reviewer round cannot be completed responsibly inside this
five-minute builder slice. No runtime implementation was started. No live
installation, background process, package execution, issue mutation or PR was
performed. Checks were not run; no Builder check PASS is claimed.

Smallest re-cut: first establish runtime alarm detection and persisted event
identities in the existing --once command with fake clock and rotated-log
receipts; follow with the persistent loop and installer proof. Preserve #344
as prerequisite. No new unit tests or weakened checks are needed.

Reproduce read-only prerequisite checks:

    git fetch origin main
    git log -1 --format='%H %s' origin/main
    gh issue view 344 --json state,title
    gh api repos/shyamsivakumar/mac-ops/issues/345/dependencies/blocked_by --jq '.[].number'
    git show origin/main:coordinator/bin/coord-watch
    rg -n 'coord-watch|BIN_FILES' install_coordinator.py
