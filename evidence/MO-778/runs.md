# MO-778 runs

Branch mo778-gate-vote. Real reports were read read-only from SRW gate threads named in the dispatch receipts (`t3_thread_read`). The 40 newest FAIL reports held 0 parseable finding lines: today's gate prose has no JSON block and no `[severity] path:line` lines. That is why a voter's brief gets `JSON_VERDICT_ASK`.

## 1. merge_reports on real SRW FAIL reports (3 heads of one PR as 3 voters, two voter orders)

Findings were lifted from the prose by prove_merge.py into the JSON block voters will emit. Hashes rewritten to the first head.

```
### 2702: heads ['e2adfac8', '199c1c07', '9ec50189']
voter order (0, 1, 2):
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: a finding stays when 2 agree on file, line within 5 and severity.
PROVIDES: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
CHECK: FAIL e2adfac8d754ec1f09bba7b92731ab594fb6b55d
VERDICT: FAIL

voter order (2, 1, 0):
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: a finding stays when 2 agree on file, line within 5 and severity.
PROVIDES: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
CHECK: FAIL e2adfac8d754ec1f09bba7b92731ab594fb6b55d
VERDICT: FAIL

  voter e2adfac8: FAIL, findings [major] bot2/trade_machine.js:482; [major] scripts/bot2_two_lane_admission_proof.cjs:271
  voter 199c1c07: FAIL, findings [major] bot2/trade_machine.js:3546; [major] scripts/bot2_two_lane_admission_proof.cjs:174
  voter 9ec50189: FAIL, findings 
### 2649: heads ['db9ca9a2', '65d89375', 'e62b6a4f']
voter order (0, 1, 2):
Merged gate review of 3 reports on db9ca9a2bd902fb14c645bcd04eef90d5495061e: a finding stays when 2 agree on file, line within 5 and severity.
2 reports ended FAIL without a finding line the merge could read.
PROVIDES: PASS db9ca9a2bd902fb14c645bcd04eef90d5495061e
CHECK: FAIL db9ca9a2bd902fb14c645bcd04eef90d5495061e
VERDICT: FAIL

voter order (2, 1, 0):
Merged gate review of 3 reports on db9ca9a2bd902fb14c645bcd04eef90d5495061e: a finding stays when 2 agree on file, line within 5 and severity.
2 reports ended FAIL without a finding line the merge could read.
PROVIDES: PASS db9ca9a2bd902fb14c645bcd04eef90d5495061e
CHECK: FAIL db9ca9a2bd902fb14c645bcd04eef90d5495061e
VERDICT: FAIL

  voter db9ca9a2: FAIL, findings 
  voter 65d89375: FAIL, findings [major] alpaca_paper_execution.js:14734
  voter e62b6a4f: FAIL, findings 
```

## 2. the 2-of-3 rule, window of 5, severity match, dead voters (prove_window.py)

```
--- two agree, line 271 vs 274 (within 5), same severity: FAIL
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: a finding stays when 2 agree on file, line within 5 and severity.
[major] scripts/bot2_two_lane_admission_proof.cjs:271 major at scripts/bot2_two_lane_admission_proof.cjs
PROVIDES: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
CHECK: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
VERDICT: FAIL
lane reads: verdict=FAIL complete_pass=False

--- 271 vs 277 (6 apart): no agreement, PASS
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: a finding stays when 2 agree on file, line within 5 and severity.
PROVIDES: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
CHECK: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
VERDICT: PASS
lane reads: verdict=PASS complete_pass=True

--- same line, major vs minor: no agreement, PASS
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: a finding stays when 2 agree on file, line within 5 and severity.
PROVIDES: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
CHECK: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
VERDICT: PASS
lane reads: verdict=PASS complete_pass=True

--- two agree on a minor only: kept, still PASS
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: a finding stays when 2 agree on file, line within 5 and severity.
[minor] bot2/trade_machine.js:482 minor at bot2/trade_machine.js
PROVIDES: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
CHECK: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
VERDICT: PASS
lane reads: verdict=PASS complete_pass=True

--- one voter died without a verdict: merge of two, both must agree
Merged gate review of 2 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: a finding stays when 2 agree on file, line within 5 and severity.
[major] scripts/bot2_two_lane_admission_proof.cjs:271 major at scripts/bot2_two_lane_admission_proof.cjs
PROVIDES: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
CHECK: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
VERDICT: FAIL
lane reads: verdict=FAIL complete_pass=False

--- two voters dead: fewer than 2 readable, FAIL not the primary alone
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: only 1 carried a verdict with its own CHECK and PROVIDES lines for this head.
VERDICT: FAIL
lane reads: verdict=FAIL complete_pass=False

--- bare VERDICT: PASS without its own CHECK and PROVIDES lines is not counted, and no line is borrowed
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: only 1 carried a verdict with its own CHECK and PROVIDES lines for this head.
VERDICT: FAIL
lane reads: verdict=FAIL complete_pass=False

--- valid voters 1 and 2, voter 3 bare PASS: merge of 2, lines are voter 1 and 2's own
Merged gate review of 2 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: a finding stays when 2 agree on file, line within 5 and severity.
PROVIDES: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
CHECK: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
VERDICT: PASS
lane reads: verdict=PASS complete_pass=True

--- one voter CHECK FAIL: merged CHECK FAIL, findings still voted
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: a finding stays when 2 agree on file, line within 5 and severity.
PROVIDES: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
CHECK: FAIL e2adfac8d754ec1f09bba7b92731ab594fb6b55d
VERDICT: FAIL
lane reads: verdict=FAIL complete_pass=False

```

## 3. lane_driver.gate_verdict with voters unlaunched, in flight, dead and CHECK FAIL (prove_lane.py, temp receipts, fake threads)

```
--- primary done PASS, voters 2 and 3 not launched yet
lane verdict: running; ledger keys []

--- primary done, voter 2 launched, voter 3 not
lane verdict: running; ledger keys []

--- all launched, voter 3 still running
lane verdict: running; ledger keys []

--- all three PASS
lane verdict: PASS; ledger keys []

--- one voter dead (no reply): merge of two
lane verdict: FAIL; ledger keys []
Merged gate review of 2 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: a finding stays when 2 agree on file, line within 5 and severity.
[major] a.py:10 t
PROVIDES: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CHECK: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
VERDICT: FAIL

--- two voters dead: FAIL, not the primary alone
lane verdict: FAIL; ledger keys []
Merged gate review of 3 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: only 1 carried a verdict with its own CHECK and PROVIDES lines for this head.
VERDICT: FAIL

--- one voter CHECK FAIL
lane verdict: FAIL; ledger keys []
Merged gate review of 3 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: a finding stays when 2 agree on file, line within 5 and severity.
PROVIDES: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CHECK: FAIL aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
VERDICT: FAIL

--- control arm: no voters recorded, primary alone as today
lane verdict: PASS; ledger keys []

--- primary done 1 h ago, voter 3 never launched: still waiting
lane verdict: running; ledger keys []

--- primary done 3 h ago, voter 3 never launched: merge of 2
lane verdict: FAIL; ledger keys []
Merged gate review of 2 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: a finding stays when 2 agree on file, line within 5 and severity.
[major] a.py:10 t
PROVIDES: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CHECK: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
VERDICT: FAIL

--- primary done 3 h ago, neither voter launched: FAIL, not the primary alone
lane verdict: FAIL; ledger keys []
Merged gate review of 1 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: only 1 carried a verdict with its own CHECK and PROVIDES lines for this head.
VERDICT: FAIL

--- primary and voter 2 done, voter 3 in flight 1 h after the primary replied: still running
lane verdict: running; ledger keys []

--- primary and voter 2 done, voter 3 in flight 3 h after the primary replied: merge of 2
lane verdict: FAIL; ledger keys []
Merged gate review of 2 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: a finding stays when 2 agree on file, line within 5 and severity.
[major] a.py:10 t
PROVIDES: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CHECK: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
VERDICT: FAIL

--- primary done, both voters in flight 3 h later: FAIL, not the primary alone
lane verdict: FAIL; ledger keys []
Merged gate review of 1 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: only 1 carried a verdict with its own CHECK and PROVIDES lines for this head.
VERDICT: FAIL

--- primary ended with no reply, voters in flight, first tick: running, wait recorded
lane verdict: running; ledger keys ['vote-wait:']

--- same, 3 h after the stored time, voters 2 and 3 finished: merge of the two valid voters
lane verdict: FAIL; ledger keys ['vote-wait:']
Merged gate review of 2 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: a finding stays when 2 agree on file, line within 5 and severity.
[major] a.py:10 t
PROVIDES: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CHECK: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
VERDICT: FAIL

--- same, 3 h after the stored time, voters still in flight: FAIL
lane verdict: FAIL; ledger keys ['vote-wait:']
Merged gate review of 1 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: only 0 carried a verdict with its own CHECK and PROVIDES lines for this head.
VERDICT: FAIL

```

## 4. cmd_gatekeep with a fake candidate, temp COORDQ_DIR and COORD_JOURNAL_DIR (prove_gatekeep.py)

```
== dry run, arm treatment (vote3)
2026-11-26 20:29:48 would queue gate:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa reviewer claudeAgent claude-sonnet-5-5
2026-11-26 20:29:48 would queue vote:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:2 reviewer claudeAgent claude-sonnet-5-5
2026-11-26 20:29:48 would queue vote:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:3 reviewer claudeAgent claude-sonnet-5-5
queue items after dry run: 0
== dry run, arm control
2026-11-26 20:29:48 would queue gate:o/r#2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa reviewer claudeAgent claude-sonnet-5-5
queue items after dry run: 0
== temp-queue run, arm treatment
2026-11-26 20:29:48 queued gate:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa reviewer claudeAgent claude-sonnet-5-5
2026-11-26 20:29:48 queued vote:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:2 reviewer claudeAgent claude-sonnet-5-5
2026-11-26 20:29:48 queued vote:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:3 reviewer claudeAgent claude-sonnet-5-5
== temp-queue run, arm control
2026-11-26 20:29:48 queued gate:o/r#2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa reviewer claudeAgent claude-sonnet-5-5
1 gate:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa | T-778 review #1 aaaaaaaa | arm treatment
2 vote:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:2 | T-778 review #1 aaaaaaaa vote 2 | arm treatment
3 vote:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:3 | T-778 review #1 aaaaaaaa vote 3 | arm treatment
4 gate:o/r#2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa | T-778 review #2 aaaaaaaa | arm control
gatedHeads keys: ['gate:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'gate:o/r#2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa']
voter 1: ['Review the changed files in this order: coordinator/bin/coordq, coordinator/overnight/lane_driver.py, coordinator/bin/gate_vote.py, evidence/MO-778/runs.md']
voter 2: ['Review the changed files in this order: coordinator/bin/gate_vote.py, coordinator/overnight/lane_driver.py, coordinator/bin/coordq, evidence/MO-778/runs.md']
voter 3: ['Review the changed files in this order: coordinator/bin/coordq, coordinator/bin/gate_vote.py, evidence/MO-778/runs.md, coordinator/overnight/lane_driver.py']
voters recorded on items: [3, None, None, None]
json ask in every voter: True
lane sees voter threads for: ['T2', 'T3']
```

Before (origin/main): no vote path exists. Gatekeep queues one gate per head, the same as the control rows above.
