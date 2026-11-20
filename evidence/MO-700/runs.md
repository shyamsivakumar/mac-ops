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

## Forecast rerun on the fixed code (head de024f75), every PR merged in the last 3 days

Same read-only setup as the forecast above. The settle path on this head runs the close checklist itself when a close fails, so the board item quotes the blocking items (fail, and skipped that is required), never a passing line. A PR whose gate thread is still running, queued, starting or preparing is skipped with no ledger mark. A search that returns exactly 100 PRs prints a `SETTLE TRUNCATED <repo>` line. A fast-forward failure after a successful close prints a line and leaves the ledger on `closed`. A `lane-merged-unreviewed-*` card names its ticket in the title, so the board cleanup withdraws it once that ticket is closed.

Action per PR, by repository (the `ACT` rows are the only ones the pass touches):

```
window start 2026-11-17
shyamsivakumar/mac-ops (94 merged PRs)
   skip: ticket already closed 69 : 474,476,478,480,486,487,488,490,492,498,509,510,511,513,519,528,529,538,540,541,542,546,547,550,552,567,570,589,592,594,597,603,608,612,613,615,618,619,624,626,630,632,634,635,636,637,641,642,644,646,650,651,654,655,656,658,661,666,668,683,684,690,692,694,695,696,697,698,699
   skip: no Refs line 22 : 481,483,484,485,512,515,516,518,522,523,563,564,569,571,572,573,574,578,586,587,606,691
   ACT (ticket #507) 1 : 588
   ACT (ticket #675) 1 : 682
   skip: already settled in the ledger 1 : 686
shyamsivakumar/strategy-replay-workbench (71 merged PRs)
   skip: ticket already closed 70 : 1240,1244,1245,1247,1249,1250,1252,1253,1254,1256,1258,1259,1260,1262,1263,1265,1270,1271,1274,1275,1276,1277,1279,1281,1282,1290,1291,1293,1294,1295,1296,1300,1301,1302,1304,1306,1308,1309,1320,1324,1325,1326,1337,1338,1340,1347,1348,1350,1356,1357,1358,1359,1360,1361,1363,1366,1367,1368,1369,1372,1373,1374,1375,1376,1377,1379,1382,1383,1384,1385
   skip: already settled in the ledger 1 : 1370
shyamsivakumar/fantasy-football-toolkit (3 merged PRs)
   skip: ticket already closed 3 : 521,522,525
shyamsivakumar/catalouge (1 merged PRs)
   skip: already settled in the ledger 1 : 132
```

First pass total after the fix: 1 `ticket close` attempt (mac-ops #682 for ticket #675, the checklist would pass), 1 board item (`lane-merged-unreviewed-MO-588` on the owner board `~/Code/coordinator/mac-ops-owner.json`, reason `none`: the gate reply on the merged head has no PROVIDES line), 0 items on `decisions.json`, 0 truncation lines (94 is under the cap of 100). The 15 PRs of 2026-11-19 sit in the "ticket already closed" row, because the tickets were closed by hand.

The "why the 14 lack a PASS" breakdown in the forecast above is unchanged by the fixes: they change what the item says and when it is raised, not which gate verdict each head has.

## Cap raised to 300

A read-only `gh pr list --state merged --search merged:>=<7 days ago> --limit 300` on mac-ops returned 261 PRs, so gh pages past 100 and the new cap of 300 is honoured. mac-ops merges about 30 PRs a day, so the 3-day window holds about 100 to 130 and stays well under 300. The `SETTLE TRUNCATED` line fires at exactly 300.
