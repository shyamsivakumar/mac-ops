# MO-1173 proof

## Ticket proof command

`heavy python3 -m pytest -q tests/test_install_deny_rules.py`

### Red: new assertions with production files unchanged from origin/main

```text
FAILED tests/test_install_deny_rules.py::ListTest::test_claude_list_splits_ask_and_deny_and_covers_token_files
AssertionError: 'Read(**/*token*.json)' not found in rules['deny']
1 failed, 30 passed in 12.62s
exit 1
```

The next run also caught the hook's source `FAMILY_MODES` still set to ask:

```text
FAILED tests/test_install_deny_rules.py::ListTest::test_hook_constants_match_the_list
AssertionError: secret_files: expected deny, got ask
1 failed, 30 passed in 12.26s
exit 1
```

### Green: this branch

```text
...............................                                          [100%]
31 passed in 11.82s
exit 0
```
