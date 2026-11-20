# MO-753 runs

## Before (origin/main)
```
  File "<string>", line 1, in <module>
KeyError: 'coverage_state'
```

## After (branch)
```
partial full none
```

Notes: the red run fails with KeyError (runpy dict lookup), not AttributeError; same meaning, the function does not exist.

## Real run on a copy of the live journal (read-only copy, GitHub read live, 2026-11-20 13:5x PT)
```
2026-11-20  coverage partial  GitHub 90  matched 43  ratio 0.478
  missing by repo: mac-ops 8, strategy-replay-workbench 37, sams-llm-wiki 2
2026-11-19  coverage none     GitHub 121 matched 0   ratio 0.0
2026-11-18  coverage none     GitHub 47  matched 0   ratio 0.0
```
`backfill --merges` on a temp copy wrote 168 merged rows marked source=backfill for 2026-11-19 on, none in the live journal.
