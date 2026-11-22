# MO-1206 runs

## Before (origin/main, no test module)
```text
ModuleNotFoundError: No module named 'tests.test_ladder_score'

Ran 1 test in 0.000s

FAILED (errors=1)
```

## After (head)
```text
test_arm_cmd_matches_first_option (tests.test_ladder_score.LadderScoreTests) ... ok
test_cli_lock_and_locked_detect_drift (tests.test_ladder_score.LadderScoreTests) ... ok
test_final_log_blocks_within_seven_days (tests.test_ladder_score.LadderScoreTests) ... ok
test_locked_score_recorded_arm_and_random_determinism (tests.test_ladder_score.LadderScoreTests) ... ok
test_pick_is_deterministic_and_varies_across_repeats (tests.test_ladder_score.LadderScoreTests) ... ok
test_read_cases_uses_split_and_counts_unscored (tests.test_ladder_score.LadderScoreTests) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.249s

OK
```

## Deliberate break

Throwaway detached worktree copy of score.py: first-option returns shuffled[-1] and the 7-day window is 0 days. The real file is untouched.
```text
FAIL: test_arm_cmd_matches_first_option (tests.test_ladder_score.LadderScoreTests)
FAIL: test_final_log_blocks_within_seven_days (tests.test_ladder_score.LadderScoreTests)
Ran 6 tests in 0.221s
FAILED (failures=2)
```
