# MO-970 runs

## Ticket proof command

Run from a copy of origin/main (a15ec9cd) with only burst.py and build_labels.py:

    HOME=/nonexistent python3 -c "...burst.py...; f=s['disagreements']; ..."
    KeyError: 'disagreements'
    exit 1

Run from this branch: exit 0.

## Selftest case

`selftest.disagreement_cases()` on origin/main code:
`AttributeError: module 'burst_disagreements' has no attribute 'disagreements'`
(exit 1). On this branch: passes (also part of the full selftest, run by the fast check).
The existing `tests.test_hillclimb_scripts` module passes (it now points the log and
journal at a temp dir).

## Live journal, read only

The live journal (`~/.local/state/coordinator/journal`, 3 month/backfill files, 647
`gate_verdict` rows: 389 PASS, 258 FAIL, no SPLIT) was read read-only. The script ran
from a temp copy of the hillclimb directory (copies of labels.jsonl, split.json,
score.lock, burst_queue.jsonl); the real directory under ~/Code/coordinator was not
written (sha1 of every file unchanged, no gate_disagreements.jsonl there).

    --log-disagreements, run 1:  gate_disagreements.jsonl: 25 new
    --log-disagreements, run 2:  gate_disagreements.jsonl: 0 new
    normal run:                  gate_disagreements.jsonl: 0 new, then the usual queue rebuild
    shasum -c on labels.jsonl, split.json, score.lock, burst_queue.jsonl after
    --log-disagreements (x2): all OK
    labels.jsonl, split.json, score.lock after the normal run: unchanged

Records by round-1 verdict, round-3 verdict and round-1 class:

    FAIL -> PASS, logic: 25
    every other pair: 0

All 25 are FAIL then PASS, so they are most likely code fixes, not gate errors.

## Cases covered by selftest

SPLIT or other verdicts skipped (a head with a later PASS after SPLIT counts as PASS),
last verdict on a head wins, a head reviewed again later is not a new round, a fourth
head is ignored, rows out of order sorted by ts, rows with missing or bad ts, pr, head,
verdict or data skipped, two PRs kept apart, all month files plus backfill read, an
unparsable journal line skipped, a missing journal directory gives no rows, a second
run appends nothing, a bad line and a torn last line in the log are skipped and the
next append starts on a new line, and labels.jsonl, split.json, score.lock and
burst_queue.jsonl are byte-identical after `--log-disagreements` run twice.
