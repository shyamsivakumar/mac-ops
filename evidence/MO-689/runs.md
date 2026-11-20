# MO-689 run output

The runs the ticket's acceptance asks for. They live here, apart from the check table in check-proof.md, so the close checklist reads only the checks.

## Scorecard runs

Code head these runs used: `37c7c5c193348561e2b682b2a4996249d99eeee6` (the commits after it change only this proof file). The check proof in check-proof.md ran on the same head. Runs were made at 2026-11-19 17:41 PST.

### Acceptance 2: fixture replay

```
$ cp evidence/MO-689/fixture-events.jsonl $D/events-2026-11.jsonl
$ scorecard --date 2026-11-12 --journal-dir $D --out-dir $D/out --no-github
Factory scorecard 2026-11-12 (America/Los_Angeles), journal coverage full, 0 GitHub calls
[headline]
  accepted_tickets: 1
[guardrails]
  change_failure: unknown (GitHub reads skipped (--no-github))
  lead_time: {"p50_minutes":122.0,"p90_minutes":122.0,"tickets":1}
  audit_disagreement: unknown (no audit yet)
[cost]
  human_touches: unknown (GitHub reads skipped (--no-github))
[flow]
  merges_github: unknown (GitHub reads skipped (--no-github))
  merges_journal: 1
  launches: 4
  launches_per_accepted: 4.0
  gate_launches_per_merge: 3.0
  gate_heads: 2
  duplicate_gate_heads: 1
  fix_rounds: 1
  prs_at_round_cap: 0
  launch_failures: 0
  dropped: 0
  verdict_mix: {"PASS":1,"FAIL":1,"SPLIT":0}
[machine]
  peak_concurrent_threads: 7
  minutes_over_cap: 550.0
[board]
  alarms_raised: 1
  alarms_withdrawn: 1
  alarms_open_at_end: []
[reconcile]
  unknown (GitHub reads skipped (--no-github))
unknown metrics (5): cost.human_touches, flow.merges_github, guardrails.audit_disagreement, guardrails.change_failure, reconcile
```

The fixture holds one ticket: a gate FAIL on head A, a fix, a gate launch on head B twice, a PASS on head B, a merge and the close. Expected: 2 gate heads, 1 duplicate gate head, 1 fix round, 1 merge, 1 accepted ticket. The report shows gate_heads 2, duplicate_gate_heads 1, fix_rounds 1, merges_journal 1, accepted_tickets 1. GitHub-dependent metrics are unknown because the fixture run uses --no-github.

### Acceptance 3 and 4: the real day, 2026-11-19

```
$ scorecard backfill --since 2026-11-13 --journal-dir $T
backfill: 22494 events since 2026-11-13 written to /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T//sc.NC83/events-backfill.jsonl (0 earlier rows kept): dropped 18, launch_failed 57, launched 8044, slots 14375
$ scorecard --date 2026-11-19 --journal-dir $T --out-dir $O
Factory scorecard 2026-11-19 (America/Los_Angeles), journal coverage none, 2 GitHub calls
[headline]
  accepted_tickets: unknown (no journal)
[guardrails]
  change_failure: unknown (window open)
  lead_time: unknown (no journal)
  audit_disagreement: unknown (no audit yet)
[cost]
  human_touches: unknown (no journal)
[flow]
  merges_github: 80
  merges_journal: unknown (no journal)
  launches: 568
  launches_per_accepted: unknown (no journal)
  gate_launches_per_merge: unknown (no journal)
  gate_heads: unknown (no journal)
  duplicate_gate_heads: unknown (no journal)
  fix_rounds: unknown (no journal)
  prs_at_round_cap: unknown (no journal)
  launch_failures: 24
  dropped: 8
  verdict_mix: unknown (no journal)
[machine]
  peak_concurrent_threads: 6
  minutes_over_cap: unknown (backfill readings are samples, not changes (0 readings above the cap))
[board]
  alarms_raised: unknown (no journal)
  alarms_withdrawn: unknown (no journal)
  alarms_open_at_end: unknown (no journal)
[reconcile]
  GitHub merges 80, matched to a journal merge 0
  on GitHub, not in journal: 80
  in journal, not on GitHub: 0
unknown metrics (17): board.alarms_open_at_end, board.alarms_raised, board.alarms_withdrawn, cost.human_touches, flow.duplicate_gate_heads, flow.fix_rounds, flow.gate_heads, flow.gate_launches_per_merge, flow.launches_per_accepted, flow.merges_journal, flow.prs_at_round_cap, flow.verdict_mix, guardrails.audit_disagreement, guardrails.change_failure, guardrails.lead_time, headline.accepted_tickets, machine.minutes_over_cap
```

GitHub calls for this report: 2 (rows with caller `scorecard` in the gateway usage log before and after: 103, 105). The limit is 60. One owner-wide search per kind (merged PRs, closed issues) serves all 12 configured repos, plus one revert search for days at least 7 days old.

Live journal files in the default journal dir touched by these runs: 0 (the backfill and the report wrote to temp dirs only).

#### Independent recount of the merges

Boundary: local America/Los_Angeles day, 2026-11-19T00:00:00-08:00 to 2026-11-20T00:00:00-08:00 (08:00Z to 08:00Z). The report counts through `gh search prs --merged --merged-at`; the recount uses `gh pr list --state merged --search "merged:<range>"` per repo, a different GitHub endpoint.

```
digitized/Concerning: 1
shyamsivakumar/CineJar: 1
shyamsivakumar/catalouge: 1
shyamsivakumar/fantasy-football-toolkit: 0
shyamsivakumar/mac-ops: 28
shyamsivakumar/openscan: 5
shyamsivakumar/recoup: 0
shyamsivakumar/sams-llm-wiki: 4
shyamsivakumar/scrapers: 0
shyamsivakumar/scripture-scroll: 0
shyamsivakumar/strategy-replay-workbench: 30
shyamsivakumar/tunerise: 10
gh pr list total: 80
report merges_github: 80
match: True
earliest mergedAt: 2026-11-19T09:28:41Z latest: 2026-11-20T01:38:06Z
merged on the UTC day 2026-11-19: 73
```

The two counts match. The 66 in the ticket was a count taken earlier on 2026-11-19, before more PRs merged that afternoon; the day was not over when this ran.

#### Backfilled peak concurrency source lines

```
peak: 6 cap: 6
from drain `at cap n/m` lines and the `(was n/m)` on starts, not the refill's count
  dispatch.log:41559 (drain at cap n/m) -> 2026-11-19 03:19:43 at cap 6/6, 1 waiting
  dispatch.log:41598 (drain at cap n/m) -> 2026-11-19 03:34:04 at cap 6/6, 2 waiting
  dispatch.log:41599 (drain at cap n/m) -> 2026-11-19 03:34:07 at cap 6/6, 2 waiting
  dispatch.log:41602 (drain at cap n/m) -> 2026-11-19 03:34:41 at cap 6/6, 1 waiting
  dispatch.log:42265 (drain at cap n/m) -> 2026-11-19 08:31:11 at cap 6/6, 1 waiting
```

Only drain's `at cap n/m, K waiting` lines and the `(was n/m)` on starts are read. The refill's `refill skipped: at cap n/m` lines are not read: that count is live threads plus queued items, not threads.

#### Reconcile logic with a synthetic journal

The real day has no live journal, so every merge is unmatched on the journal side. The matching itself was exercised with a throwaway journal of three real merged PRs, one that is not on GitHub, and one slots event from the day before so the journal counts as running the whole day:

```
journal merged events: 2 merged, 1 merged_outside_lane, 1 not on GitHub (#99999)
github_merges 80 matched 3 on_github_not_in_journal 77 in_journal_not_on_github ['shyamsivakumar/mac-ops#99999']
human_touches 122 merges 78 closes 44
```

### Review follow-ups, run on the same head

#### Partial journal coverage is unknown, never a zero

```
$ same fixture without its first row (the journal then starts 09:00 on 2026-11-12)
$ scorecard --date 2026-11-12 --journal-dir $D --out-dir $D/out --no-github
Factory scorecard 2026-11-12 (America/Los_Angeles), journal coverage partial, 0 GitHub calls
[headline]
  accepted_tickets: unknown (journal started 09:00 into the day)
[flow]
  merges_github: unknown (GitHub reads skipped (--no-github))
  merges_journal: unknown (journal started 09:00 into the day)
  launches: unknown (journal started 09:00 into the day and no backfill)
  launches_per_accepted: unknown (journal started 09:00 into the day)
  gate_launches_per_merge: unknown (journal started 09:00 into the day)
  gate_heads: unknown (journal started 09:00 into the day)
  duplicate_gate_heads: unknown (journal started 09:00 into the day)
  fix_rounds: unknown (journal started 09:00 into the day)
  prs_at_round_cap: unknown (journal started 09:00 into the day)
  launch_failures: unknown (journal started 09:00 into the day and no backfill)
  dropped: unknown (journal started 09:00 into the day and no backfill)
  verdict_mix: unknown (journal started 09:00 into the day)
[machine]
  peak_concurrent_threads: unknown (journal started 09:00 into the day and no backfill)
  minutes_over_cap: unknown (journal started 09:00 into the day and no backfill)
[board]
unknown metrics (23): board.alarms_open_at_end, board.alarms_raised, board.alarms_withdrawn, cost.human_touches, flow.dropped, flow.duplicate_gate_heads, flow.fix_rounds, flow.gate_heads, flow.gate_launches_per_merge, flow.launch_failures, flow.launches, flow.launches_per_accepted, flow.merges_github, flow.merges_journal, flow.prs_at_round_cap, flow.verdict_mix, guardrails.audit_disagreement, guardrails.change_failure, guardrails.lead_time, headline.accepted_tickets, machine.minutes_over_cap, machine.peak_concurrent_threads, reconcile
```

The full fixture above starts with a slots event on 2026-11-11 at 20:00 (over the cap). The carried state is the seed for peak and minutes over cap, so minutes_over_cap is 550.0: 540 minutes carried from midnight to 09:00 plus the 10 minutes in the day.

#### A GitHub failure is final: exit 1, no day JSON

```
$ PATH=$FAKE_GH:$PATH scorecard --date 2026-11-19 --journal-dir $EMPTY --out-dir $O ; echo exit $?; ls $O
exit 1
Factory scorecard 2026-11-19 (America/Los_Angeles), journal coverage none, 1 GitHub calls
[headline]
  accepted_tickets: unknown (no journal)
  unknown (GitHub read failed: gh search prs failed: HTTP 403: API rate limit exceeded)
unknown metrics (23): board.alarms_open_at_end, board.alarms_raised, board.alarms_withdrawn, cost.human_touches, flow.dropped, flow.duplicate_gate_heads, flow.f
scorecard: GitHub read failed: gh search prs failed: HTTP 403: API rate limit exceeded; the report for 2026-11-19 was not written
day JSON files written: 0
```

The decision: a report whose GitHub reads failed is not written, so a day JSON always means a complete report, and the lane retries.

#### Backfill keeps earlier days and fails clearly

```
$ scorecard backfill --since 2026-11-18 --journal-dir $J
backfill: 9030 events since 2026-11-18 written to /var/folders/d3/kwh8z2bj1rlgy6fill.jsonl (0 earlier rows kept): dropped 10, launch_failed 30, launched 3323, slots 5667
$ scorecard backfill --since 2026-11-19 --journal-dir $J
backfill: 1209 events since 2026-11-19 written to /var/folders/d3/kwh8z2bj1rlgy6/bf.qptV/events-backfill.jsonl (7821 earlier rows kept): dropped 8, launch_failed 24, launched 568, slots 609
$ scorecard backfill --since 2026-11-19 --dispatch-log /nonexistent/dispatch.log --journal-dir $J ; echo exit $?
scorecard: the dispatch log /nonexistent/dispatch.log does not exist
exit 1
```

#### The lane hook runs the scorecard detached

Run against a stub scorecard script that sleeps 2 seconds and then fails or succeeds, with the real `daily_scorecard` code and real Popen, ps and kill:

```
SCORECARD 2026-11-18 try 1 started as pid 26211
launch took 0.00s
{'scorecard:2026-11-18': {'tries': 1, 'done': False, 'pid': 26211, 'started': 1795138885.341803}}
SCORECARD 2026-11-18 try 1 ended without a report, see <tmp>/log
SCORECARD 2026-11-18 try 2 started as pid 26436
{'scorecard:2026-11-18': {'tries': 2, 'done': False, 'pid': 26436, 'started': 1795138887.866915}}
SCORECARD 2026-11-18 written
{'scorecard:2026-11-18': {'tries': 2, 'done': True, 'pid': None, 'started': 1795138887.866915}}
{'scorecard:2026-11-18': {'tries': 2, 'done': True, 'pid': None, 'started': 1795138887.866915}}
SCORECARD 2026-11-18 try 1 started as pid 26587
SCORECARD 2026-11-18 try 1 killed after 1s
{'scorecard:2026-11-18': {'tries': 1, 'done': False, 'pid': None, 'started': 1795138892.892182}}
SCORECARD 2026-11-18 try 2 started as pid 26634
SCORECARD 2026-11-18 try 2 ended without a report, see <tmp>/log
SCORECARD 2026-11-18 try 3 started as pid 26890
SCORECARD 2026-11-18 try 3 ended without a report, see <tmp>/log
{'scorecard:2026-11-18': {'tries': 3, 'done': False, 'pid': None, 'started': 1795138896.3254569}}
```

The first call returns at once (launch took 0.00s) with the pid and start time in the ledger. A later pass sees the process ended without a day JSON, counts it, and starts the next try; the day JSON ends the retries; a run past the age limit (shortened to 1 s here, 10 minutes in the code) is killed; and the tries stop at 3.

## Revert window boundary

Code head these runs used: `ac9e36ae932312a7e33d0b7bfbb8e4737781a73c`, the head `check-proof-2.md` names. Run at 2026-11-19 18:54 PST.

A day's change failure is final once the report day's end plus 7 days has passed. The day ends at local midnight, so 2026-11-11 is final from 2026-11-19 00:00 and 2026-11-12 is final from 2026-11-20 00:00. Before the fix both days counted as final on 2026-11-19, because the test was 7 whole days since the day began.

```
$ scorecard --date 2026-11-11 --journal-dir $EMPTY --out-dir $D | grep -E 'Factory|change_failure'
Factory scorecard 2026-11-11 (America/Los_Angeles), journal coverage none, 3 GitHub calls
  change_failure: {"reverted":[],"merges":152}
$ scorecard --date 2026-11-12 --journal-dir $EMPTY --out-dir $D | grep -E 'Factory|change_failure'
Factory scorecard 2026-11-12 (America/Los_Angeles), journal coverage none, 2 GitHub calls
  change_failure: unknown (window open)
unknown metrics (21): board.alarms_open_at_end, board.alarms_raised, board.alarms_withdrawn, cost.human_touches, flow.dropped, flow.duplicate_gate_heads, flow.fix_rounds, flow.gate_heads, flow.gate_launches_per_merge, flow.launch_failures, flow.launches, flow.launches_per_accepted, flow.merges_journal, flow.prs_at_round_cap, flow.verdict_mix, guardrails.audit_disagreement, guardrails.change_failure, guardrails.lead_time, headline.accepted_tickets, machine.minutes_over_cap, machine.peak_concurrent_threads
```

2026-11-11 reads its revert window (3 GitHub calls: merged PRs, closed issues, the revert search) and finds no revert. 2026-11-12 is `unknown (window open)` (2 calls) until 2026-11-20 00:00 PT.
