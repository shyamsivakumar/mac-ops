# MO-700: why merged PRs left their tickets open

## Result

On 2026-11-19, 14 of the 15 PRs had no `after-merge:` entry in the lane
ledger because `settle_merged_prs` never looked at them. The 15th (#656)
was looked at, and its close failed on the close checklist. Two defects in
`coordinator/overnight/lane_driver.py` on `origin/main` (`0abe7c50`) explain
all 15. Nothing in `coordinator/bin/close_check.py` or the gate brief is
the cause.

## Cause 1: a cutoff fixed at the lane's first run (13 PRs)

Line 1288 stores `settle-since` in the ledger once, as the time of the first
settle pass, and line 1290 skips every merged PR older than it. The ledger
holds `settle-since = 2026-11-19T19:30:52Z`. Settling was added by #651,
which merged at 19:27:02Z, so the first pass ran four minutes later. These
13 PRs merged before that time and are skipped on every pass forever:

#651, #634, #635, #615, #613, #612, #608, #603, #637, #546, #624, #630, #642.

Traced example, #635 (ticket #633): merged 2026-11-19T18:33:52Z with
`Refs #633` in the body. Line 1286 lists it, line 1290 compares its
`mergedAt` to `since` and continues, so line 1295 (the `Refs` and open
ticket test) is never reached and no ledger key, journal event or board item
is written. Ticket #633 kept `stage:started` until Shyam closed it by hand.

## Cause 2: the window is the ten highest PR numbers (#632)

Line 1286 asks `gh pr list --state merged --limit 10`. That list is ordered
by when the PR was created, not when it merged. #632 was created early, sat
through three gate rounds, and merged at 22:57:30Z. At that moment 17 merged
PRs had higher numbers (634 to 668), so #632 was never in the ten returned.
The settle passes before and after its merge never saw it. Its ticket (#530)
stayed open.

## The one attempt: #656 for #649

#656 merged at 21:22:49Z, after the cutoff and inside the window, so
line 1305 called `close_after_merge`. `ticket close` failed on the checklist
(`scope: fail`, `proof file: fail`, see the comment on #649). Line 1270
catches the error and raises `lane-close-failed-MO-656`, but the item did
not carry the failing lines, and line 1306 printed "ticket closed and main
fast-forwarded" for a close that failed. The title of most of the 11 tickets'
PRs was `MO: ...` with no minted key; settle never reads the title, so that
only affects whether a close can pass, which this ticket leaves unchanged.

## What this change does

- `settle_merged_prs` reads merged PRs with
  `--search merged:>=<date>` and `--limit 100`, and skips any older than
  `SETTLE_LOOKBACK_DAYS` (3). The window no longer depends on the first run
  or on PR numbers. A PR is attempted once, keyed by its ledger entry, so a
  failed close is not repeated.
- `close_after_merge` returns whether the close worked. The pass prints
  "close failed, board item raised" otherwise.
- `close_failed_item` takes the `: fail` lines of the checklist output and
  puts them in the item's reason. The item id is per PR, so a PR has one
  item.
- A merged PR with no recorded gate PASS still raises one
  `lane-merged-unreviewed` item and closes nothing, as before.
- `merged_restart` in `coordinator/overnight/selftest.py` now checks the
  window arguments and that the close-failed item names the failing line.
  No case was added, so `EXPECTED` is unchanged.

## Replay

`runs.md` replays the 15 PRs through the changed path with GitHub and thread
reads only. All 15 reach a close attempt or one board item. The same replay
on `origin/main` reaches none.
