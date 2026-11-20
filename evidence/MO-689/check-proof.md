# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `5b83dd7084f091b5affd7177f5d226cec0602db0`
Working tree clean when the checks ran: yes
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: coordinator/bin/journal.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/journal.py` | passed |  |
| python syntax: coordinator/bin/scorecard | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/scorecard` | passed |  |
| python syntax: coordinator/overnight/alarms.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/alarms.py` | passed |  |
| python syntax: coordinator/overnight/lane_driver.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/lane_driver.py` | passed |  |
| python syntax: coordinator/overnight/selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/selftest.py` | passed |  |
| python syntax: scripts/mac_ops_fast_check.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/mac_ops_fast_check.py` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/bin/scorecard coordinator/pi/bin/coord-tick` | passed | 76 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | passed | 1 modules, no issues |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-nuheuq_7 -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-nuheuq_7/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_alarm_panel | `python3 -m unittest tests.test_alarm_panel` | passed |  |
| tests: tests.test_lane_decisions_board | `python3 -m unittest tests.test_lane_decisions_board` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.

## Scorecard runs

Code head these runs used: `5b83dd7084f091b5affd7177f5d226cec0602db0`. The check above ran on the same head. Runs were made at 2026-11-19 17:32 PST.

### Acceptance 2: fixture replay

```
$ cp evidence/MO-689/fixture-events.jsonl $D/events-2026-11.jsonl
$ scorecard --date 2026-11-12 --journal-dir $D --out-dir $D/out --no-github
Factory scorecard 2026-11-12 (America/Los_Angeles), journal 4/24 hours, 0 GitHub calls
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
  minutes_over_cap: 10.0
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
backfill: 22490 events since 2026-11-13 written to /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T//sc.pruf/events-backfill.jsonl: dropped 18, launch_failed 57, launched 8042, slots 14373
$ scorecard --date 2026-11-19 --journal-dir $T --out-dir $O
Factory scorecard 2026-11-19 (America/Los_Angeles), journal 0/24 hours, 2 GitHub calls
[headline]
  accepted_tickets: unknown (no live journal events on 2026-11-19 (no journal yet))
[guardrails]
  change_failure: unknown (window open)
  lead_time: unknown (no live journal events on 2026-11-19 (no journal yet))
  audit_disagreement: unknown (no audit yet)
[cost]
  human_touches: unknown (no live journal events on 2026-11-19 (no journal yet))
[flow]
  merges_github: 78
  merges_journal: unknown (no live journal events on 2026-11-19 (no journal yet))
  launches: 566
  launches_per_accepted: unknown (no live journal events on 2026-11-19 (no journal yet))
  gate_launches_per_merge: unknown (no live journal events on 2026-11-19 (no journal yet))
  gate_heads: unknown (no live journal events on 2026-11-19 (no journal yet))
  duplicate_gate_heads: unknown (no live journal events on 2026-11-19 (no journal yet))
  fix_rounds: unknown (no live journal events on 2026-11-19 (no journal yet))
  prs_at_round_cap: unknown (no live journal events on 2026-11-19 (no journal yet))
  launch_failures: 24
  dropped: 8
  verdict_mix: unknown (no live journal events on 2026-11-19 (no journal yet))
[machine]
  peak_concurrent_threads: 6
  minutes_over_cap: unknown (backfill readings are samples, not changes (0 readings above the cap))
[board]
  alarms_raised: unknown (no live journal events on 2026-11-19 (no journal yet))
  alarms_withdrawn: unknown (no live journal events on 2026-11-19 (no journal yet))
  alarms_open_at_end: unknown (no live journal events on 2026-11-19 (no journal yet))
[reconcile]
  GitHub merges 78, matched to a journal merge 0
  on GitHub, not in journal: 78
  in journal, not on GitHub: 0
unknown metrics (17): board.alarms_open_at_end, board.alarms_raised, board.alarms_withdrawn, cost.human_touches, flow.duplicate_gate_heads, flow.fix_rounds, flow.gate_heads, flow.gate_launches_per_merge, flow.launches_per_accepted, flow.merges_journal, flow.prs_at_round_cap, flow.verdict_mix, guardrails.audit_disagreement, guardrails.change_failure, guardrails.lead_time, headline.accepted_tickets, machine.minutes_over_cap
```

GitHub calls for this report: 2 (rows with caller `scorecard` in the gateway usage log before and after: 84, 86). The limit is 60. One owner-wide search per kind (merged PRs, closed issues) serves all 12 configured repos, plus one revert search for days at least 7 days old.

Live journal files in the default journal dir touched by these runs: 0 (the backfill and the report wrote to temp dirs only).

#### Independent recount of the merges

Boundary: local America/Los_Angeles day, 2026-11-19T00:00:00-08:00 to 2026-11-20T00:00:00-08:00 (08:00Z to 08:00Z). The report counts through `gh search prs --merged --merged-at`; the recount uses `gh pr list --state merged --search "merged:<range>"` per repo, a different GitHub endpoint.

```
digitized/Concerning: 1
shyamsivakumar/CineJar: 1
shyamsivakumar/catalouge: 1
shyamsivakumar/fantasy-football-toolkit: 0
shyamsivakumar/mac-ops: 27
shyamsivakumar/openscan: 5
shyamsivakumar/recoup: 0
shyamsivakumar/sams-llm-wiki: 4
shyamsivakumar/scrapers: 0
shyamsivakumar/scripture-scroll: 0
shyamsivakumar/strategy-replay-workbench: 29
shyamsivakumar/tunerise: 10
gh pr list total: 78
report merges_github: 78
match: True
earliest mergedAt: 2026-11-19T09:28:41Z latest: 2026-11-20T00:52:35Z
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

The real day has no live journal, so every merge is unmatched on the journal side. The matching itself was exercised with a throwaway journal of three real merged PRs and one that is not on GitHub:

```
journal merged events: 2 merged, 1 merged_outside_lane, 1 not on GitHub (#99999)
github_merges 78 matched 3 on_github_not_in_journal 75 in_journal_not_on_github ['shyamsivakumar/mac-ops#99999']
human_touches 119 merges 76 closes 43
```

#### A day at least 7 days old (change failure window closed)

```
$ scorecard --date 2026-11-10 --journal-dir $EMPTY --out-dir $D
Factory scorecard 2026-11-10 (America/Los_Angeles), journal 0/24 hours, 3 GitHub calls
[headline]
  accepted_tickets: unknown (no live journal events on 2026-11-10 (no journal yet))
[guardrails]
  change_failure: {"reverted":[],"merges":47}
  lead_time: unknown (no live journal events on 2026-11-10 (no journal yet))
  audit_disagreement: unknown (no audit yet)
[flow]
  merges_github: 47
  merges_journal: unknown (no live journal events on 2026-11-10 (no journal yet))
unknown metrics (20): board.alarms_open_at_end, board.alarms_raised, board.alarms_withdrawn, cost.human_touches, flow.dropped, flow.duplicate_gate_heads, flow.fix_rounds, flow.gate_heads, flow.gate_launches_per_merge, flow.launch_failures, flow.launches, flow.launches_per_accepted, flow.merges_journal, flow.prs_at_round_cap, flow.verdict_mix, guardrails.audit_disagreement, guardrails.lead_time, headline.accepted_tickets, machine.minutes_over_cap, machine.peak_concurrent_threads
```

That is 3 GitHub calls: merged PRs, closed issues and the revert search. The revert match was exercised on synthetic data (a `Revert "<title>"` title, a `Reverts <repo>#N` body, and a revert outside the 7 day window): it flagged the first two and not the third. No revert-titled PR in the configured repos matches that form today.

#### Existing tests

This change adds a new CLI and a lane hook. The overnight selftest in the fast check covers the lane. The twelve coordq and ticket test modules fail the same 16 ways on origin/main (see the MO-688 proof) and are not touched by this diff.
