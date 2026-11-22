# MO-1147 runs

## Proof command

`python3 -m unittest tests.test_ladder_outcomes`

On origin/main (68e2e951):

```text
ModuleNotFoundError: No module named 'tests.test_ladder_outcomes'
FAILED (errors=1)
```

On the branch:

```text
Ran 9 tests in 0.013s
OK
```

## Which outcome signals exist (checked 22 Nov, read-only)

| Check | Source | Signal on this Mac |
| --- | --- | --- |
| reverted | main commits via `gh api repos/R/commits` containing `This reverts commit <merge sha>` after the decision | Works. 10 of 32 rows are merged after the decision, all `false`. Revert PRs exist only for #198 (mac-ops), #77 (SRW, a different change) and #43 (tunerise), none tied to a labeled decision |
| main_broke | commit status `srw/agent-check` (Mac-published) on the merge commit | SRW only. mac-ops main has no status and no check runs, FFBT has only `Vercel` (not Mac-published, ignored), tunerise and digitized/Concerning have none. 4 rows scored, all `false` |
| rollback_or_incident | journal events named rollback, rolled_back or incident | No signal. The journal (events-2026-11.jsonl, events-backfill.jsonl) has 23 event names and none is a rollback or incident; alarms carry no repo or PR. All 32 rows are `null` |
| recut | journal `recut` rows for the PR after the decision, or `ticket_started` after `ticket_closed` (the scorecard `restarted` rule) | Works for repos the journal covers. 4 rows scored, all `false`; null when the journal has no row for the subject, and null when the chosen answer is itself a re-cut |

`scorecard` computes `restarted` as a ticket whose latest `ticket_started` is later than its `ticket_closed`; the recut check reuses that rule.

## Real fetch (read-only, output to scratch)

`python3 evals/ladder/outcomes.py fetch --labels ~/Code/coordinator/evals/hillclimb --out <scratch>/outcomes.jsonl`

```text
rows=32
reverted: true=0 false=10 null=22
main_broke: true=0 false=4 null=28
rollback_or_incident: true=0 false=0 null=32
recut: true=0 false=4 null=28
```

32 of 133 labels name a PR or ticket (the rest have no row). No check came back `true`, so no label is outcome-incorrect yet. `rollback_or_incident` is all-null because no source emits one.

## Score with the outcome column (dev split only, scratch copy of labels, 5 repeats)

| Arm | Baseline | n | Lift | outcome_correct arm | outcome_correct baseline | Cases with an outcome |
| --- | --- | --- | --- | --- | --- | --- |
| recorded | random | 73 | 42.19 | 25/25 (100%) | 10/21 (47.6%) | 7 of 73 |
| first-option | random | 73 | 2.47 | 19/21 (90.5%) | 10/21 (47.6%) | 7 of 73 |

Coverage is low because most labeled options (re-cut, take it over) fit neither approve nor reject and stay unscored. The final split was not run.
