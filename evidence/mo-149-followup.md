# MO-149 review blockers and approved follow-up

Refs MO-149. Base: `debbe637b07cbae40daadf244089ef539ccc7094`.

## Original reviewer findings (exact)

- major | `verification/check_hub_turn_budget.py:25,103` | The user asked for the existing hub tests to pass, but the log shows this file fails 6 of 6. It fails at the AST loader check (`tree.body[-1]` must be a bare `main()` call), and its fixture also needs `release_slot`/`SLOTS` and a queued provider turn, which this task removes. The file is untouched against base, which is correct. | Get Shyam to approve exact edits to its loader and fixture, and to replacing the provider-queue test. Do not add the removed code back as a shim.
- major | `evidence/mo-149-hub-proof.md:26` | The real 601-second wall-clock proof (`--wall-clock`) is still running and has no result. | Add its full output to the log before handoff.

## Exact-edit authorization

> Approved under Shyam's standing rule (2026-11-10 13:52 PT, "do reecommended on everything else"): builders may edit existing tests only as far as the ticket's stated behaviour change needs, list each changed line in the PR, and the Opus gate checks it. This ticket's stated change is removing the hub's per-provider `limits` gate. So you may make exactly the edit you described to verification/check_hub_turn_budget.py: the SourceFileLoader loader at lines 7 and 23-30, engine-release instrumentation at 103-107 and 126, and the concurrent-turn/drain-queue cases replacing the provider-queue cases at 198-232 and 351-386. Keep every other assertion. List the changed lines in the PR under this note.

## Resolution

The canonical MO-147 proof now loads the guarded source module with SourceFileLoader, records engine releases, and checks concurrent same-provider turns plus drain-only queue clocks. All five unaffected test methods are byte-identical to base. Resume run-count/record-count and full persisted wall-clock run-record equality assertions remain. The interim separate uncapped runner was removed after moving its coverage (including routing/turnLimits assertions) into the canonical proof; no parallel fixture or shim remains.

`evidence/mo-149-followup-proof.log`: startup 5 OK; canonical budget/provenance 7 OK; repository tests 51 OK; py_compile exit 0. The previously recorded real 601-second run passed in `evidence/mo-149-wall-clock.log`; the fresh canonical `python3 -u verification/check_hub_turn_budget.py --wall-clock` also passed (exit 0, 10m 1s), with its complete `SECOND HUB` output in `evidence/mo-149-canonical-wall-clock.log`. The second review's sole major blocker is therefore resolved; `evidence/mo-149-followup-review-2.md` is preserved as historical evidence.

Final third review: `evidence/mo-149-review-final.md`, **VERDICT: PASS**, no critical/major findings; not independently rerun. Minor request to include command/exit/duration in the canonical wall log is addressed; interleaved concurrent output is explicitly noted and otherwise unchanged. The PR body includes the approval and a zero-context diff listing every changed existing-test line.

No install, production drain, restart or installed-binary invocation. Push and PR are explicitly requested; deployment is not authorized.
