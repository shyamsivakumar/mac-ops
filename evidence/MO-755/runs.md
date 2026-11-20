Adapted: PYTHONPATH=coordinator/overnight added (runpy does not put the script dir on sys.path, so `import alarms` fails otherwise); origin/main copy run from a sibling file.

## Before (origin/main)
  File "<string>", line 5, in <module>
KeyError: 'journal_merged'
ugrep: warning: /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.29DPuqQalp/events-*.jsonl: No such file or directory

## After (branch)
1

## Duplicate merged rows for real PRs (read only, ~/Library/Logs/coordinator/events-2026-11.jsonl)

38 `merged` or `merged_outside_lane` rows for 38 distinct PRs, 0 duplicates (36 merged, 2 merged_outside_lane, all 2026-11-20). The burst is not present for real PRs after #740.

## Cause

Both call sites keyed the ledger by `journal-outside:{repo}#{number}:{head}`, so a PR whose head differed (fake heads) or a ledger that lost a write emitted again. `journal_merged` keys by PR only and also checks the current month journal.

## Garbage lines in the journal

Journal with a partial line, a `merged_outside_lane` row for r/x#5, then another partial line. `journal_has_merged('r/x',5), journal_has_merged('r/x',6)` prints (no exception):

    True False
