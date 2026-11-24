# MO-910 runs

Proof script (size_class for 16 lines in 7 files, 301 lines in 1 file, 16 lines in 7 files whole, plus 300 lines in 7 files); the ticket one-liner asserts the same triple.

## On origin/main (red)
```
Traceback (most recent call last):
  File "/private/tmp/claude-501/-Users-shyamsivakumar-Code/c283b00e-e8c8-422f-9aa1-eb7c969bb5ce/scratchpad/p910.py", line 8, in <module>
    assert r==("over_cap","recut","over_cap"), r
AssertionError: ('recut', 'recut', 'over_cap')
exit: (see signature above)
```
## On the head (green)
```
16 lines/7 files, 301 lines/1 file, 16 lines/7 files whole: ('over_cap', 'recut', 'over_cap')
300 lines/7 files: over_cap
exit: (see signature above)
```

Existing tests pinning the file trigger: none found (grep of selftest.py, hourly_selftest.py, tests/ for size_class, RECUT_FILES and the card cause). No test changed.
Docs grep (lane_briefs.py, gate_bar.py, coordinator/config/AGENT-RULES.md, overnight/README.md, factory-cut skill): no stated six-file re-cut trigger.
