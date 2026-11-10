# MO-147 hub turn budget and gate provenance

Refs MO-147. Base: `5ce521a275460cd6550b570c2e3d327042aa8f52`.

## Safety and design

Read both requested design-review final messages (Sol `emp:5f87a9a7`, GLM
`emp:e4bda223`); both said `VERDICT: ADOPT WITH CHANGES`. Implemented their
minimal hub scope, not the coordinator retry/model-approval policy.

No production install, restart, cancellation, resume, or paid provider call.
Proof loads the hub under a fresh temporary HOME, binds a second Unix socket,
and launches real `/bin/sleep 3600` children through a fake ACP adapter.
GitHub reads in the dry-run proof are stubbed; merge planning, review gating,
revision inputs and the RPC handler are the actual hub code. Only the normal
proof advances its isolated hub clock. The wall-clock proof waits 601 actual
seconds with zero clock offset. No TCP port or preview server is needed.

Root-cause reproduction before editing: the new total-budget oracle returned
`None` rather than `turn ran over 10 min`; active-tool handling returned early
and there was no total execution clock. The existing run `startedAt` cannot
be used because it includes provider-slot queueing.

The implementation stays in the owning runtime/launch/run/stall/review-gate
functions. The existing cancellation grace timer is fenced to its execution
clock so it cannot kill a later resumed run. No parallel cancellation or resume
path was added. `finish_run` remains the sole run finalizer and slot releaser.

Pending permission questions defer expiry even if already over budget,
including while the answer send is blocked. Wait time remains charged, not
subtracted: after the answer is sent and removed from pending, the next reaper
check can cancel an expired turn. An unanswered question defers indefinitely.

## Commands and output

- `python3 verification/check_hub_turn_budget.py`: six disposable-socket tests;
  full hub log, failed run record, fallback and normal merge dry-run JSON in
  `mo-147-hub-proof.log` beside this file.
- `python3 -u verification/check_hub_turn_budget.py --wall-clock`: real
  600-second override with a long sleep and a second queued thread: PASS after
  601 actual seconds (zero clock offset), one cancellation and release, failed
  run persisted, queued execution clock zero, final provider slot empty. Full
  output is in `mo-147-wall-clock.log` beside this file.
- `python3 scripts/mac_ops_fast_check.py`: passed. TLC: 3380 generated states,
  888 distinct states, no error; selected checks are not the full suite.
- `python3 -m unittest discover -s tests -v`: 51 tests in 0.376s, `OK`.
- Python `ast.parse` of `empryo/bin/emp-hub` and JSON parsing of routing: PASS.
- `git diff --check`: PASS.

The proof asserts the failed run error/status, one cancellation and slot
release, persisted run record, zero queue budget, a fresh clock on resend,
thread override through `resume_turn` and persisted drain/reload, pending
permission behavior (including a blocked answer send), old-timer fencing,
7200 default and legacy-store fallback, invalid launch arguments rejected,
and actual recorded fallback model/runId in `emp_thread_merge` dryRun. It also
proves changing provenance alone leaves `revision_inputs` unchanged.

Model provenance is limited to the last run's persisted model, including
reported fallback notices. It is not a guarantee of all models that contributed
to context or an unreported engine switch. Approval remains coordinator policy.

## In-session review

Dispatched `code-reviewer` on `subscriptions/claude-opus-4-6` against the base
above, with the task scope and builder proof outputs. It inspected the owning
functions, callers, new proof and docs; did not independently rerun proofs.
No critical or major findings. Non-blocking comments: fractional-minute display
for non-minute overrides (intentional rather than truncating the budget), numeric
JSON-RPC ids in the disposable adapter (valid JSON-RPC), and the doc's `N min`
notation (N may be fractional). No additional code change was needed.

A second dispatch of the same in-session reviewer inspected the final files
and complete 601-second wall-clock and dry-run logs: no findings; proofs not
independently rerun. Last verdict:

`VERDICT: PASS`

The installed hub remains unchanged. Rollback after a future approved install:
restore the previous `emp-hub` and restart only with coordinator approval.
A separate Claude Opus gate is still required before merge/deployment.
