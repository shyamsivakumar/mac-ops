# MO-1130 · Test modules that load coordq and ticket pass and the fast check runs them

# Fix coordq and ticket test selection

Built in Herdr session t1j, not by the refill (Shyam, 2026-11-19:
"file tickets but do it here. not on the board").
Labelled stage:hold for that reason only.

## Goal and why

The test modules that load `coordq` and `ticket` pass on main, and the
fast check runs them whenever either file changes.

On 2026-11-19, the 12 modules that load them gave 298 tests with 13
failures and 3 errors on `da70cd7d`. The same 16 names failed before
and after the journal change.

modules by changed `.py` file. `coordq` and `ticket` have no `.py`
suffix.

## Context

  `tests/test_*.py` for the changed files.
- The modules: `tests/test_coordq_*.py`, `tests/test_gatekeep_*.py`,
  `tests/test_lane_*.py` and any others that load
  `coordinator/bin/coordq` or `coordinator/bin/ticket` by path
  (`tests.test_gatekeep_backstop_reviewer.load_coordq` is one loader).
- #679 (tests use a fake gh and temp logs) may explain some failures;
  read it and say which overlap.

## Scope and non-goals

In:

  `coordinator/bin/coordq` or `coordinator/bin/ticket` selects every
  test module that loads that file.
- The failing tests or the code they test, case by case: for each of
  the 16, say whether the test is stale (behaviour changed on purpose,
  cite the PR) or the code is wrong, and fix that side.
  Files: `tests/test_gate_reviewer_quota.py`, `tests/test_gatekeep_backstop_reviewer.py`,
  `tests/test_gatekeep_retry_limit.py`, `tests/test_reviewer_vendor_split.py`,
  `tests/test_ticket_text_blockers.py` (all stale or reading live state; no code under `coordinator/` was wrong).
- `coordinator/config/tickets.json`: drop `"merge": "manual"` for digitized/Concerning (Shyam 2026-11-19: merge it too), which `tests/test_install_coordinator.py` flagged.
- `evidence/MO-701/check-proof.md`,
  `evidence/MO-701/README.md` (the 16 names, the verdict and
  fix for each).

Out:

- No deleted or skipped test to make the count pass.

## Design fit

Requires: `origin/main` at `52334e7c` or later.
Provides: the test modules that load `coordq` and `ticket` pass on
main, and the fast check runs them when either file changes.

## Acceptance and proof

1.
   evidence/MO-701/check-proof.md` passes on the final head,
   and its table shows those modules ran.
2. `python3 -m unittest` over the same 12 modules: 0 failures, 0
   errors, with the output in the README.
3. A trial change touching only `coordinator/bin/coordq` makes the
   fast check select those modules (shown by its selection output).
4.

## Must not cause

- A test deleted, skipped or loosened without a cited reason.
- Tests that call the live GitHub account or write real logs.
- A fast check slower than 10 minutes.

The repository is at `/app`. Make the change there. Do not edit test files.
