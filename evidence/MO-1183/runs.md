# MO-1183 runs

## Finding
The ticket's cause (codex Astra listed first since #666) is not what fails. `models.json` lists `astra-api` (openai-api) first in the review order. The test fails in suite order because `test_failed_thread_queues_once` records a real block on openai-api in the module's one shared COORDQ_DIR, so `reviewer_model` skips it and returns codex. Run alone, the test passes on main, so the ticket's single-test proof does not fail there. The fix gives each test its own COORDQ_DIR.

## Before (origin/main test file), module pair in suite order
```
AssertionError: {'instanceId': 'codex', 'model': 'gpt-6.2-astra'} != {'instanceId': 'openai-api', 'model': 'openai/gpt-6.2-astra'}
- {'instanceId': 'codex', 'model': 'gpt-6.2-astra'}
?                 - ^ ^

+ {'instanceId': 'openai-api', 'model': 'openai/gpt-6.2-astra'}
?                  ^ ^^^^^^^             +++++++


----------------------------------------------------------------------
Ran 31 tests in 0.192s

FAILED (failures=1)
```

## After (this branch), same command
```
----------------------------------------------------------------------
Ran 31 tests in 0.187s

OK
```

## Ticket proof command after
```
Ran 1 test in 0.003s

OK
```

## Forced failure (temporary local edit adding self.fail to test_quota_markers, reverted), check_isolation called directly
```
Run result: failed: the unittest suite is red (exited 1): FAIL: test_quota_markers (tests.test_gate_reviewer_quota.ReviewerQuotaTests)
```

## Clean run of check_isolation on this branch (before the proof commit)
```
Run result: passed: ... 686 tests ran (unittest exited 0, selftest exited 0)
```
