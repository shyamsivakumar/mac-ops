# MO-177 audit decisions

- Ticket: https://github.com/shyamsivakumar/mac-ops/issues/113
- Run: `ticket:shyamsivakumar/mac-ops#113:a1`
- Base: `origin/main`
- Scope: `empryo/bin/emp-hub:gate_report`; no routing, engine, installation or merge execution changes.

## Decision: locate the final report before judging it

**Observed evidence.** `emp call emp_thread_read` activity captures show the original SRW-846 review ended with assistant reports at positions 5/6, a `dynamic_tool` named Show at 7, and `run_finished` at 8. SRW-790 ended with its CHECK/PASS report at 18, a `dynamic_tool` at 19, and `run_finished` at 20. Both later received a manual restatement request and a second run. The replay intentionally truncates at the first run's completion, not the successful restatement.

**Root cause demonstrated before editing.** Running `replay.py` separately against each captured original run printed `(False, 'the latest run left no report')` and raised AssertionError. `trailing_reports` stops at the post-report tool item before reaching the report; the verdict parser itself is correct. This is hub report selection, not an engine defect.

**Choice.** In `gate_report` only, bound items to the latest run's start, then trim non-message activity after the final message before applying the existing trailing-report selection and disagreement check. Preserve the user-message boundary. This ignores tool activity, not later assistant messages, and cannot reuse a previous run's PASS when the latest run has no report.

**Alternatives rejected.** Searching backwards for any passing verdict would hide a later FAIL or missing verdict. Filtering out every tool item would combine progress messages with final reports across tool boundaries. Changing `trailing_reports` globally would affect other hub consumers. Trusting reportItemIds does not work: the failing original runs recorded an empty reportItemIds list.

**Invariants.** `judge_review`, CHECK head-SHA binding, exact last nonempty verdict line, completed-run requirement, adjacent-report disagreement refusal, review provenance and freshness checks remain unchanged. No existing test or fixture changes.

## Proof and review

- Original activity captures: `emp call emp_thread_read` with `view: activity`, `limit: 100`, and complete item text for the two thread IDs above. Captures remain temporary; no production hub is imported, launched, restarted or drained.
- `python3 evidence/MO-177/replay.py <SRW-846 activity JSON> <SRW-790 activity JSON>`: both original runs now PASS; eleven synthetic cases preserve final-message, FAIL, CHECK SHA, missing CHECK, user/run boundaries and disagreement refusals. Full output: [replay.log](replay.log). The script executes only selected function definitions, never hub initialization.
- `heavy python3 -m unittest -v verification.check_hub_auto_merge verification.check_hub_merge_evidence tests.test_hub_install`: `Ran 62 tests in 11.267s` / `OK`. Existing suites unchanged. Full output: [hub-tests.log](hub-tests.log). Targeted hub merge/install suites only: the single-instance proof launches real hub processes and the turn-budget proof starts its socket server; neither was run under the task's no-hub-execution restriction.
- `git diff --check`: clean.
- One in-session read-only `code-reviewer` round using `subscriptions/claude-opus-5-5` on `origin/main...477b783549d251cb5a2d699735ba8980418c8be1`: no critical or major findings; `VERDICT: PASS`. Proofs not independently rerun. Minor evidence timing mismatch corrected to the committed log; baseline replay failures and capture filenames recorded in replay.log. Temporary captures are intentionally not committed: obtain them again through `emp_thread_read` for the IDs below. The replay asserts ordinal 1 so a truncated recent-run window cannot silently replay a later run.

## Rollback and residual risk

Revert the PR to restore the previous selection behavior. Installation and production merge remain coordinator-approved separate steps. Timestamp scoping uses the same persisted ISO UTC item/run timestamps the hub writes; report text and verdict parsing are untouched. Review noted two out-of-scope residual issues: other trailing_reports consumers still miss post-tool reports, and now_iso reads the clock twice, which can cause a boundary-time false refusal (fail closed). No existing tests, fixtures or proofs were modified.

Capture again with `emp call emp_thread_read` and arguments `{"threadId":"emp:ad767a88-f2b8-437f-a7eb-707815acba22","view":"activity","limit":100,"runLimit":50}` into `mo177-srw846.json`, and the same arguments with thread ID `emp:f1a2acb1-ef83-41cc-a2df-ca424d93de0e` into `mo177-srw790.json`. Omit maxCharsPerItem so report text is not clipped. Pass both files to replay.py.
