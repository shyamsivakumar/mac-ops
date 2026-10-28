# mac-ops evals

The governor and controller are measured on safety and liveness under
replayed load, against the current policy in this repository. Older llmwiki
simulations are history, not proof of the installed controller. Method:
[outcome evaluation method](https://github.com/shyamsivakumar/sams-llm-wiki/blob/main/source/docs/explanation/outcome-evaluation-method.md)
(llmwiki). Lifecycles: [governor](state-charts/governor.md),
[controller](state-charts/controller.md).

## Ship and score (2026-10-28)

Ship working changes fast. Every metric on this page is a **scorecard**: run
it on every merge and deploy, publish numerators and denominators, and use the
result to choose the next fix. Scorecards do **not** block merge or deploy.

Only **hard stops** block merge or deploy:

- The repository or installed runtime **does not build or start**, including
  formal checks that encode safety invariants.
- **Health fails or the supervisor crashes** during required smoke checks.
- **Data or machine safety breaks**: replayed behavior violates the hard
  safety rules below (for example admitting on stale or critical telemetry,
  unsafe resume, or more than one active controller).

Everything else (liveness timing, trace coverage, nightly audit gaps,
advisory judge output) is reported and steers the next fix. Do not wait for
datasets or pilots that do not exist yet; ship with what is available and
record what the live scorecard must confirm next.

**Status.** Proposed in LMW-25 (2026-10-28), adapted here for ship-and-score.
Every threshold is a proposal until a pilot confirms it; nothing below is
current policy or achieved performance. **Terms.** Jev is TypeSafe AI's
bounded judge model, called through DeepEval's `JevEval`. A Noul is a
yes-or-no question, a Score picks one of ordered levels, a Choice picks one of
fixed options with stated credit. **Judge status.** Every judge question on
this page is advisory. None can block until it is calibrated against human
labels and given its own threshold, as the method page describes. Judge cost
assumes $0.042 per million input tokens, output free.

## Dataset

At least 100 named traces: recorded telemetry from the overload incident and
from healthy recovery, plus labeled synthetic edge traces for stale or missing
readings, swap and compressor divergence, pause failure, PID reuse, concurrent
claims, wait and release, critical pressure and restart recovery. Synthetic
traces are reported apart from recorded load. Keep 20 recorded traces sealed
with the independent replay runner; builders develop against the rest.

## How it runs

Replay the real admission and controller functions with a fake clock and
captured process-control effects.

## Hard stops (safety replay)

These Boolean properties are **hard stops**. Zero violations across all
replayed events is required to merge or deploy controller or admission
changes. Each planted violation (for example stale-reading admission or a
dropped pause retry) must fail the run.

- No admission on stale or critical telemetry.
- No increase above policy.
- Failed pauses are retried.
- No unsafe resume.
- Correct workload identity.
- Exactly one controller.
- Exit status, stdin and cleanup preserved.

The current README's floor and one-slot-growth policy is the policy under test.

## Scorecards

Report these on every merge and deploy; use misses to prioritize the next
fix. They do not block ship.

**Liveness.** Fraction of eligible traces where every eligible queued job
starts and every eligible paused job resumes after a sustained healthy window,
within H + 2T seconds, where H is the configured recovery window and T the tick
interval, both frozen from config before the run. Report violations with trace
id and measured delay.

**Trace suite.** Pass rate on named traces and model invariants; separate
numerators for recorded versus synthetic traces.

**Conformance.** Trace-to-code conformance drift (report mismatches; fix in follow-up).

**Operational checks.** Results of authorized installed-service checks before
operational acceptance. Simulation cannot satisfy native board start and wake
enforcement, so that check stays a separate installed scorecard.

**Nightly telemetry audit.** Findings and open gaps from the audit run.

## No judge

These properties are Boolean and timing checks. Optional advisory triage of
incident prose only. Required judging cost for hard stops and scorecards:
zero.

## When checks run

| When | Hard stops | Scorecards |
| --- | --- | --- |
| Task, review | Safety replay, touched paths | Full replay if available |
| Merge, deploy | TLC checks; zero violations | Liveness, pass rates, drift |
| Ops acceptance | Builds, starts, no crash | Service and wake checks |
| Nightly | — | Telemetry audit |

## Owner and first definition of done

The controller policy owner, with an independent replay runner. Done when
every named trace and model invariant passes on current code on the
development partition, each planted violation fails, the H + 2T bound is
stated in seconds on the scorecard, and hard-stop versus scorecard roles match
this page.
