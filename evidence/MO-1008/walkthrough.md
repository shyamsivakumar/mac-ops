# MO-1008 source walkthrough

2026-11-16. Coordinator continuation overrides the earlier prerequisite stop.
Fresh `git fetch origin` and `git rebase origin/main` completed successfully.
Wake backlog exists on origin/main in coordinator.ts; native dependency #346
is absent (existing dependencies: #332, #374, #388). This administrative gap
is recorded rather than changing issue relationships in a README ticket.

Read-only review round: checked README commands against installed package
sources under ~/.pi/agent-coordinator/npm/node_modules, without executing them.
- pi-background-monitor docs/reference.md and src/index.ts: start command/id,
  regex ^EVENT, wake, once=false, TTL, inspection cursors, restart and cleanup.
- pi-checklist README.md: meta toggle, flat meta, generated dependency IDs,
  ten-task capacity, frozen done entries and session-only state.
- pi-subagent-manager docs/settings.md and extension limitations: scoped model
  selection, tool filtering and extension/bridge inheritance.
- Repository settings.json, role YAML, coord-pi, coordinator.sb and
  install_coordinator.py: pins, model, launcher sandbox and installed paths.
- Canonical lane.md and notes.md read in ~/Code/coordinator; unchanged.

Review result: source-contract walkthrough PASS. Commands are operator examples,
not live execution receipts. No new unit tests or package execution. Device,
owner and live-service checks waived. Restart recovery requires explicit old
producer closure; no automatic adoption API is claimed. Exact EVENT recovery
is bounded and may return unknown after log loss. Checklist remains a board view.

Reproduce: inspect the named sources and README JSON calls, then run
`timeout 300 python3 scripts/mac_ops_fast_check.py` from repository root.
Provides pi-runbook is a merge-time fact, not yet asserted on origin/main.
Deslop: reviewed the scoped prose and removed duplicate action ownership.
No-comments diff review: documentation only, no source comments changed.
