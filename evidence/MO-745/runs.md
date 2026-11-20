# MO-745 runs

Both runs use a temp COORDQ_DIR and a temp COORD_JOURNAL_DIR. The case is `build-here`: a stage:todo ticket in a build-here repo is not started (and one skip line is logged), and a failing PR in a build-here repo raises a board card and sends nothing.

## Branch (code commit 26d1fa2023a928e906a45f92d3c1837f388e9a5d)
```
PASS send-integrity
PASS root-workspace
PASS worktree-base-ref
PASS consolidation-guard
PASS script-results
PASS start-routing
PASS dead-run-recovery
PASS gate-pipeline
PASS merged-restart
PASS merge-pass
PASS gate-round-cap
PASS decisions-board-guard
PASS no-parking
PASS turncap
PASS watchdog
PASS zero-merge
PASS board-integrity
PASS api-budget
PASS ff-drift
PASS cycle-health
PASS stall
PASS alarm-mute
PASS router-build
PASS router-blocked
PASS key-mint
PASS credit-block
PASS close-evidence
PASS build-here
```

## origin/main code with the new selftest.py (origin/main 165c9f80)
```
PASS send-integrity
PASS root-workspace
PASS worktree-base-ref
PASS consolidation-guard
PASS script-results
PASS start-routing
PASS dead-run-recovery
PASS gate-pipeline
PASS merged-restart
PASS merge-pass
PASS gate-round-cap
PASS decisions-board-guard
PASS no-parking
PASS turncap
FAIL watchdog: expected ['alarm-mute', 'api-budget', 'board-integrity', 'build-here', 'close-evidence', 'consolidation-guard', 'credit-block', 'cycle-health', 'dead-run-recovery', 'decisions-board-guard', 'ff-drift', 'gate-pipeline', 'gate-round-cap', 'key-mint', 'merge-pass', 'merged-restart', 'no-parking', 'root-workspace', 'router-blocked', 'router-build', 'script-results', 'send-integrity', 'stall', 'start-routing', 'turncap', 'watchdog', 'worktree-base-ref', 'zero-merge'], got ['alarm-mute', 'api-budget', 'board-integrity', 'close-evidence', 'consolidation-guard', 'credit-block', 'cycle-health', 'dead-run-recovery', 'decisions-board-guard', 'ff-drift', 'gate-pipeline', 'gate-round-cap', 'key-mint', 'merge-pass', 'merged-restart', 'no-parking', 'root-workspace', 'router-blocked', 'router-build', 'script-results', 'send-integrity', 'stall', 'start-routing', 'turncap', 'watchdog', 'worktree-base-ref', 'zero-merge']
PASS zero-merge
PASS board-integrity
PASS api-budget
PASS ff-drift
PASS cycle-health
PASS stall
PASS alarm-mute
PASS router-build
PASS router-blocked
PASS key-mint
PASS credit-block
PASS close-evidence
FAIL build-here: lane_candidates() takes from 2 to 3 positional arguments but 4 were given
```

No refill dry run was made: the task forbids running the refill. The skip line is asserted by the selftest instead.
