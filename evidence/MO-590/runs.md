# MO-590 runs

- `heavy python3 coordinator/overnight/selftest.py` with the change: all 27 evals PASS, including the extended `root-workspace` eval.
- Same selftest with `lane_driver.py` from origin/main (plus an empty `PASS_WORKTREES` so the eval imports): `FAIL root-workspace: expected [{'type': 'worktree', ...}], got [{'type': 'existing_worktree', ...}]`. The herdr-branch worktree was reused on main.
- `heavy python3 scripts/mac_ops_fast_check.py --proof evidence/MO-590/check-proof.md`: passed.
