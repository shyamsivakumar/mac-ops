# MO-860 runs

## Proof command

```
python3 -c "import runpy; s=runpy.run_path('coordinator/bin/coordq', run_name='proof'); print(s['stamped']('skip x'))"
```

Before (origin/main 68e2e951): `KeyError: 'stamped'`

After: `2026-11-22 12:13:57 skip x`

## gatekeep --dry-run on temp COORDQ_DIR, COORD_JOURNAL_DIR, decisions and gh cache (read-only gh reads)

Before:
```
skip shyamsivakumar/strategy-replay-workbench#1867: at the gate round cap, no gate queued
would queue gate:shyamsivakumar/mac-ops#856:41890f0e453bed2bf4cb72f7db8fe1a25a393be0 reviewer openai-api openai/gpt-6.2-astra
would queue gate:shyamsivakumar/sams-llm-wiki#244:bc583010c0c0e8798d2f7ea3c9c8c864c054a558 reviewer openai-api openai/gpt-6.2-astra
```

After:
```
2026-11-22 12:13:28 skip shyamsivakumar/strategy-replay-workbench#1867: at the gate round cap, no gate queued
2026-11-22 12:13:33 would queue gate:shyamsivakumar/mac-ops#856:41890f0e453bed2bf4cb72f7db8fe1a25a393be0 reviewer openai-api openai/gpt-6.2-astra
2026-11-22 12:13:39 would queue gate:shyamsivakumar/sams-llm-wiki#244:bc583010c0c0e8798d2f7ea3c9c8c864c054a558 reviewer openai-api openai/gpt-6.2-astra
```

Both runs exit 0. No repeated backstop or stuck lines appeared in this run, so no counts to note.

## Existing tests

tests.test_gatekeep_retry_limit: the old `startswith("gave up ")` assertions fail 3 cases on the new output (timestamp prefix); with `"gave up " in line` and the same change in tests.test_gatekeep_backstop_reviewer, 36 tests pass.
