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
