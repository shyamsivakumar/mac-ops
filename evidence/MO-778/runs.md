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
VERDICT: PASS

voter order (2, 1, 0):
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: a finding stays when 2 agree on file, line within 5 and severity.
PROVIDES: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
CHECK: FAIL e2adfac8d754ec1f09bba7b92731ab594fb6b55d
VERDICT: PASS

Traceback (most recent call last):
  File "/Users/shyamsivakumar/Code/mac-ops/.claude/worktrees/agent-a4b182d2c039a2066/evidence/MO-778/prove_merge.py", line 74, in <module>
    show(pr, by_pr[pr][:3])
  File "/Users/shyamsivakumar/Code/mac-ops/.claude/worktrees/agent-a4b182d2c039a2066/evidence/MO-778/prove_merge.py", line 60, in show
    for row, report in zip(picked, reports, strict=True):
TypeError: zip() takes no keyword arguments
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
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: only 1 ended with a readable verdict.
VERDICT: FAIL
lane reads: verdict=FAIL complete_pass=False

--- one voter CHECK FAIL: merged CHECK FAIL, findings still voted
Merged gate review of 3 reports on e2adfac8d754ec1f09bba7b92731ab594fb6b55d: a finding stays when 2 agree on file, line within 5 and severity.
PROVIDES: PASS e2adfac8d754ec1f09bba7b92731ab594fb6b55d
CHECK: FAIL e2adfac8d754ec1f09bba7b92731ab594fb6b55d
VERDICT: PASS
lane reads: verdict=PASS complete_pass=False

```

## 3. lane_driver.gate_verdict with voters unlaunched, in flight, dead and CHECK FAIL (prove_lane.py, temp receipts, fake threads)

```
--- primary done PASS, voters 2 and 3 not launched yet
lane verdict: running

--- primary done, voter 2 launched, voter 3 not
lane verdict: running

--- all launched, voter 3 still running
lane verdict: running

--- all three PASS
lane verdict: PASS

--- one voter dead (no reply): merge of two
lane verdict: FAIL
Merged gate review of 2 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: a finding stays when 2 agree on file, line within 5 and severity.
[major] a.py:10 t
PROVIDES: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CHECK: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
VERDICT: FAIL

--- two voters dead: FAIL, not the primary alone
lane verdict: FAIL
Merged gate review of 3 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: only 1 ended with a readable verdict.
VERDICT: FAIL

--- one voter CHECK FAIL
lane verdict: none
Merged gate review of 3 reports on aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: a finding stays when 2 agree on file, line within 5 and severity.
PROVIDES: PASS aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CHECK: FAIL aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
VERDICT: PASS

--- control arm: no voters recorded, primary alone as today
lane verdict: PASS

```

## 4. cmd_gatekeep with a fake candidate, temp COORDQ_DIR and COORD_JOURNAL_DIR (prove_gatekeep.py)

```
== dry run, arm treatment (vote3)
2026-11-26 18:47:29 would queue gate:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa reviewer claudeAgent claude-sonnet-5-5
2026-11-26 18:47:29 would queue vote:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:2 reviewer claudeAgent claude-sonnet-5-5
2026-11-26 18:47:29 would queue vote:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:3 reviewer claudeAgent claude-sonnet-5-5
queue items after dry run: 0
== dry run, arm control
2026-11-26 18:47:29 would queue gate:o/r#2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa reviewer claudeAgent claude-sonnet-5-5
queue items after dry run: 0
== temp-queue run, arm treatment
2026-11-26 18:47:29 queued gate:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa reviewer claudeAgent claude-sonnet-5-5
2026-11-26 18:47:29 queued vote:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:2 reviewer claudeAgent claude-sonnet-5-5
2026-11-26 18:47:29 queued vote:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:3 reviewer claudeAgent claude-sonnet-5-5
== temp-queue run, arm control
2026-11-26 18:47:29 queued gate:o/r#2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa reviewer claudeAgent claude-sonnet-5-5
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
