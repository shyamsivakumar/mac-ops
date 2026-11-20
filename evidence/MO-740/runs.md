# MO-740 runs

Code commit: 322ba5be45144bd00fa68565675c7035649cbef8. Journal: ~/Library/Logs/coordinator/events-2026-11.jsonl.
The live coordinator and other builders append real rows to the journal all day, so its line count and mtime move.
The fake-signature count (rows whose head is a fixture sha, the quarantine script's rule) is the invariant.

## The reader of the live queue

The selftest eval gate_pipeline (coordinator/overnight/selftest.py:572) patched lane.RECEIPTS but not lane.QUEUE.
lane_driver.gatekeep_gave_up then read the hardcoded live queue.json, so the result depended on live state.
An audit hook (open events under Code/coordinator/queue) on the origin/main copy logged that read, plus models.py
providers-blocked.json (27 reads in unittest) and overnight slot_cap config.json. On this branch the same hook logs zero
reads of the live queue in the selftest and in all three unittest runs. The original gh pr view 169 refusal could not be
reproduced: the live queue no longer holds the receipts and gatedHeads that caused it.

## python3 -m unittest, three runs (679 tests each)

| Run | Journal lines before -> after | Journal mtime after | Fake-signature rows before -> after | Live queue files |
| --- | --- | --- | --- | --- |
| 1 | 2512 -> 2535 | 12:18:21 | 316 -> 318 | unchanged |
| 2 | 2535 -> 2550 | 12:25:32 | 318 -> 318 | unchanged |
| 3 | 2550 -> 2616 | 12:40:23 | 318 -> 318 | unchanged |

Run 1 shows +2 fake-signature rows. They are two merge_held rows for mac-ops#544 stamped 12:16:55, before run 1's tests
started (it ran 63 s and ended 12:18:38), so another builder's unisolated run wrote them. Runs 2 and 3 added none.
Live queue file list before and after every run: config.json dispatch-receipts.json dispatch.last dispatch.log gatekeep-stuck.txt gatekeep.log gh-login mo-1050-body.md providers-blocked.json providers-blocked.json.lock providers-blocked.lock queue.json queue.lock refill-state.json refill.last refill.lock (plus .ruff_cache). No findings/ directory appeared.
Each run failed one test, test_gate_reviewer_quota.test_vendor_routing, which also fails on origin/main
(a block written by test_failed_thread_queues_once carries over to it inside that module). It is not touched here.

## Fast check

Journal fake-signature rows 318 before and 318 after. Queue file list unchanged. Result: passed
(evidence/MO-740/check-proof.md names commit 322ba5be). The isolation step passed with 0 mac-ops-test usage rows,
skips.log unchanged, and no refused gh call. Only this one fast check was run, as the coordinator cut the proof to one.

## Quarantine script, on COPIES of the live journal (never run on the live one)

Rule: any string in a row (head, or a sha inside data) that is one hex character x40, or 8 x one character then 32 x another.
Copy of 2514 rows: dry run matched 316, kept 2198. By event: gate_queued 109, gate_verdict 98, fix_sent 40, merged 21,
merge_held 15, round_cap 15, ticket_closed 11, close_failed 7. Apply on the copy: backup, 316-row quarantine file,
2198-row journal; 2198 + 316 = 2514 and the sorted rows of backup equal kept plus quarantined. Second run: 0 matched.
