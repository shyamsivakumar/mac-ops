# MO-185 verification — 2026-11-12

Scope: move Cockpit's existing transport to T3, retain columns, disable board
merging and drop cleanup. No dependencies or automated CI workflows added.

- `python3 scripts/mac_ops_fast_check.py`: passed (selected checks, not full suite).
- Node syntax checks for hub.js, main.js and ui.js: passed.
- `git diff --check`: passed.
- Required retired-call grep: no matches.
- Existing cockpit-specific tests: none found; existing tests unchanged.
- Read-only loader probe: exact running ID equality before/after the load,
  six threads; twelve Needs groups; Hub reachable; Queue matched the same
  `empq status` sample at cap 6, live 6, queued 6. The probe allowlisted only
  thread/project/pending reads and `empq status`.
- Probe and full private receipt: `/tmp/mo185-probe.mjs` and
  `/tmp/mo185-read-proof.json`. No tokens or .env read or printed.
- Herdr mod check passed; installed directory backed up before copying;
  native hot reload observed; app status reported no errors.
- One Luna Max in-session read-only reviewer round found the legacy automatic
  preflight incorrectly stored the relay notice as a refusal. Fixed by disabling
  automatic preflight and ignoring obsolete refusal records. No second round.
- Diff comment review and bounded deslop pass: no added comments, dependencies,
  compatibility transport or unrelated cleanup. Removed retired terminal and
  shell probes as part of eliminating Empryo support.

Reply, Settle and pending responses were not executed. No emp, send, settle or
interrupt call was made during acceptance. Exact-head Claude Opus gate is
pending and was deliberately not launched. No merge authorized here.

Final native frame: `/tmp/mo185-final-board.png`; matching live listing:
`/tmp/mo185-final-running.json`; queue sample:
`/tmp/mo185-final-queue.json` (cap 6, live 6, queued 7); app status:
`/tmp/mo185-final-app-status.json` (errors empty). Frame shows Running 6/6,
Needs you 12, Hub T3 reachable and Queue 6/6 with 7 queued. Running cards
retain the existing task grouping (SRW-1036 includes its separate review).
