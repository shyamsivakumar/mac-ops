# MO-765 runs

The ticket text asks for `lane_driver.recut_brief`. The owner's instruction moved the brief to the gatekeep recut branch in coordq, with the text in `coordinator/bin/lane_briefs.py`, so the proof command is adapted to `evidence/MO-765/proof.py`. It uses a temp COORDQ_DIR, COORD_JOURNAL_DIR, HOME, decisions board and rules file, and queue cap 0, so t3 is never called. `gate_candidates` is faked and, like the real one (coordq `recutHeads` check), skips a head already recorded.

## Before (origin/main)

```
recut #9
run 1 briefs queued: 0
run 2 same head briefs queued: 0
IndexError: list index out of range
```

## After (branch)

```
queued #1
recut #9
run 1 briefs queued: 1
run 2 same head briefs queued: 1
model: {'instanceId': 'codex', 'model': 'gpt-6.2-sol'} taskType: design action keys: ['recut:gate:o/mac-ops#9:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa']
Type: design · sol (re-cut an oversized pull request)

Pull request o/mac-ops#9 head aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa counts 800 code lines in 4 code files. One ticket may hold at most 150 code lines in 3 code files, counted the way the gate counts them.
Read the pull request with `gh pr diff 9 -R o/mac-ops`. Use as many tickets as the work needs so each one fits that cap, and chain them with Blocked by. Open each one with `ticket open --repo o/mac-ops --title "<title>" --body-file <file> --label stage:todo,type:<type>,priority:<n>`; the tool mints the key, so never type a key and never use `gh issue create`.
Start nothing, change no code, and ask no one.

```
