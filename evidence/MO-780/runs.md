# MO-780 runs

Run with PYTHONPATH=coordinator/overnight (the module imports sibling modules); the ticket command as written fails on that import before reaching the function.

## Before (origin/main)
```
  File "<string>", line 1, in <module>
KeyError: 'classify_failure'
```

## After (branch)
```
minor_only moved_bar logic size
```

## Real FAIL gate threads (read-only, 2026-11-20), classify_failure(thread text, "ok", {})

Gate replies carry no `[severity] path:line` lines yet, so every one falls back to logic. Classes are meaningful once the reviewer follows the new format.

| PR head | class | reason |
|---|---|---|
| 802 c519c62b | logic | FAIL, no parsed findings |
| 428de9ca | logic | incorrect historical replay blocks on correctness |
| 9dc05f79 | logic | admission defect blocks the PR |
| 3ec6fbf6 | logic | first-dispatch behavior blocks |
| 801 49065313, 793 4c54c807, 792 7e55c708, 792 5ac28fec | logic | FAIL with no parsed findings |
