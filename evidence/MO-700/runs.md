# MO-700 runs

## Replay of the 2026-11-19 merges (gh and thread reads only, close and board writes stubbed)

```
MO    #656: merged earlier, close failed, board item raised
#651: board item, no recorded gate PASS
#656: close attempt, failed, one board item -> shyamsivakumar/mac-ops#649
#634: board item, no recorded gate PASS
#635: board item, no recorded gate PASS
#615: board item, no recorded gate PASS
#613: board item, no recorded gate PASS
#612: board item, no recorded gate PASS
#608: board item, no recorded gate PASS
#603: board item, no recorded gate PASS
#637: board item, no recorded gate PASS
#546: board item, no recorded gate PASS
#632: board item, no recorded gate PASS
#624: board item, no recorded gate PASS
#630: board item, no recorded gate PASS
#642: board item, no recorded gate PASS
PRs reached: 15 of 15
board items per PR: [1]
```

The replay script is not in the repository. It calls settle_merged_prs from lane_driver.py with run() limited to gh pr list, gh api GET and t3mcp thread reads. ticket close raises a stub failure and publish_decision records the item id. The recorded receipts file is read as it is, so each PR gets the verdict the live lane would read.

## Same replay on origin/main (0abe7c50), settle-since fixed at 2026-11-19T19:30:52Z as in the live ledger

```
#651: NOTHING
#656: NOTHING
#634: NOTHING
#635: NOTHING
#615: NOTHING
#613: NOTHING
#612: NOTHING
#608: NOTHING
#603: NOTHING
#637: NOTHING
#546: NOTHING
#632: NOTHING
#624: NOTHING
#630: NOTHING
#642: NOTHING
PRs reached: 0 of 15
board items per PR: [0]
```

Run today, the old code's ten-PR window (the ten highest PR numbers) no longer holds #656 either, which the live lane did attempt at the time. Today's window is later than the live one, so the count of 0 of 15 is a floor for the old code, and the live ledger shows exactly one attempt (#656).

## Forecast of the first live pass (run 2026-11-20 about 03:45Z, writes stubbed)

Inputs: the open issues of the four lane repos from `gh issue list`, the merged PRs of the last 3 days from `gh pr list`, a copy of the real lanes ledger, the real dispatch receipts and live thread reads. `ticket close` was replaced by the read-only close checklist (`close_check.run_check`) so the forecast says whether the checklist would pass. Nothing was closed, published or fast-forwarded.

The window holds 94 merged mac-ops PRs, 71 SRW, 3 FFBT and 1 CTL. Of those, 69 mac-ops, 70 SRW and all 3 FFBT PRs ref a ticket that is already closed, 22 mac-ops PRs have no `Refs` line, and 3 PRs are already keyed in the ledger. Two PRs ref an open ticket and are not keyed. The 11 tickets of 2026-11-19 are closed, so the 15 PRs of the ticket cause nothing now.

For each of the two:

- mac-ops #682 (ticket #675, merged 2026-11-20T03:31:26Z by the lane merge pass, gate PASS on head 2c5833f8): one `ticket close` attempt. The close checklist would PASS (every blocking item passed), so the ticket would close and main would fast-forward. The ledger had no `after-merge` entry for it yet because the merge landed two minutes before the ledger's last write.
- mac-ops #588 (ticket #507, merged 2026-11-19T02:53:15Z): no close attempt. Item `lane-merged-unreviewed-MO-588` on the owner board (`~/Code/coordinator/mac-ops-owner.json`). Reason `none`: the gate reply on the merged head ends `CHECK: PASS` and `VERDICT: PASS` but has no `PROVIDES: PASS` line, which `ticket close` also requires.

First pass total: 1 close attempt (would pass), 1 board item, 0 items on `decisions.json`.

## Why 14 of the 15 had no usable gate PASS

`gate_verdict` was read on the exact merged head of each PR, with the real receipts and thread replies. All 15 were merged by `shyamsivakumar` (the gate thread and Shyam use the same GitHub login), so `mergedBy` does not tell them apart. The receipts do.

- Gate said VERDICT: FAIL on the merged head, merged anyway: #608, #637, #546, #642. These are merges over a FAIL.
- No gate attempt on the merged head: #612 (no receipt at all) and #615 (only a FAIL on an earlier head). Merged by hand.
- Gate PASS (CHECK and VERDICT lines) but no PROVIDES line: #634, #635, #603, #632, #624, #630. Verdict `none`. The gate brief did not ask for a PROVIDES line until #682 merged today, so no gate before that wrote one. `ticket close` refuses these too (`ticket` line 1767 calls `complete_pass` with provides required), so reading them as not passed is the same decision `ticket close` makes.
- Gate PASS on the merged head but no recorded base: #651 and #613. Verdict `absent` (`lane_driver.py` line 450: `base:<thread>` receipt must equal the PR base). `base:` receipts began with #651 (`git log -S` finds the check in `da151fc5`, merged 2026-11-19 11:27 PT); 125 of 2,496 gate receipts have one. A merge before that has no recorded base, by design.
- #656: gate PASS with a recorded base. This is the one the lane attempted.

So no PR that a gate PASSed with a recorded base was read as unreviewed. The item text did say "no recorded gate PASS" for all of them, which was wrong for the PROVIDES and base cases. This change makes the item's reason name which case it is (`absent`, `none`, `FAIL`, `SPLIT` or `running`).
