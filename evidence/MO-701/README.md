# MO-701 evidence

Head under test: see the Checked commit line in check-proof.md.

## Totals

The 16 modules that load coordinator/bin/coordq or coordinator/bin/ticket (found by grepping tests/ for the loaders) ran 391 tests on origin/main 0abe7c50 with 29 failures and 6 errors (35 failing names, counting each subTest). After the fixes the same 16 modules run 391 tests with 0 failures and 0 errors. Command for both: heavy python3 -m unittest followed by the 16 module names. The module count on da70cd7d was 12 with 16 failing names; main moved since, and the counts above are for 0abe7c50.

The modules: test_answer_format, test_close_check, test_coordq_action_key, test_coordq_capacity, test_coordq_message_dedupe, test_gate_fast_forward, test_gate_reviewer_quota, test_gatekeep_backstop_reviewer, test_gatekeep_retry_limit, test_lane_duplicate_suppression, test_prompt_paths, test_reviewer_vendor_split, test_tick_external_call_bounds, test_ticket_gate_live, test_ticket_section_headings, test_ticket_text_blockers.

## Failing names, verdict and fix

Every verdict is that the test was stale or read live state. No code under coordinator/ changed.

1. test_reviewer_vendor_split: test_vendor_split (11 subTests), test_unknown_routes (4 subTests), test_unknown_builder_fallback. Verdict: the test read the live providers-blocked.json under ~/Code/coordinator/queue, where openai-api and anthropic-api are blocked, so the reviewer fell to the codex or claudeAgent entry. Overlaps #679 (tests touching live state). Fix: setUpModule points COORDQ_DIR at a temp dir for the module.
2. test_gate_reviewer_quota: test_vendor_routing, test_quota_exhaustion_excludes_builder. Verdict: same live block file. Fix: same temp COORDQ_DIR.
3. test_gate_reviewer_quota: test_failed_thread_queues_once. Verdict: stale. PR #695 made gatekeep call gate_candidates(config, lane_ledger()), and the test stub took one argument. Fix: the stub accepts the second argument.
4. test_gatekeep_retry_limit: test_a_block_after_the_selection_is_not_queued_on_a_fresh_head (reported twice, a failure and its cleanup error). Verdict: stale for the same PR #695. Fix: the wrapper passes the ledger argument through.
5. test_gatekeep_backstop_reviewer: test_the_candidate_uses_the_backstop_reviewer, test_the_backstop_line_is_logged_once, test_a_builder_with_a_known_model_keeps_its_reviewer, test_a_minimax_builder_gets_astra, test_two_runs_queue_one_gate. Verdict: stale. The expected reviewer was codex gpt-6-astra. PR #478 made API Astra first, PR #528 moved to gpt-6.2-astra, and PR #552 put it in models.json as openai-api openai/gpt-6.2-astra. Fix: the expected selection and log text name that entry.
6. test_gatekeep_backstop_reviewer: test_the_backstop_line_is_logged_once_for_two_issues, test_a_pull_request_without_a_passing_check_is_not_gated, test_no_skip_is_reported, test_a_gated_head_is_not_stuck. Verdict: stale. PR #251 made the builder thread come from the ticket key (builder_thread_for_issue), PR #546 made an unreadable changed-file list defer the gate, and PR #510 reads the proof file through gh. The fake gh knew none of these, so two tests hit an unexpected endpoint and the proof read went to the live gh gateway (overlaps #679, the contents/evidence/.../check-proof.md calls). Fix, minimum for these tests only: stub builder_thread_for_issue and gate_proof, give the pull request changed_files 0 with an empty files answer, and let the fake gh accept the optional keyword.
7. test_ticket_text_blockers: test_text_blockers_refuse_the_start, test_native_blocker_refusal_keeps_its_own_text, test_force_skips_the_text_blockers, test_a_ticket_without_the_hold_starts, test_the_start_proceeds_with_the_notice_on_stderr, test_force_skips (one failure and errors from the same cause). Verdict: stale. PR #666 removed the minimax builder entry, so builder:minimax is an unknown alias. Fix: the fixture uses builder:router and expects the router alias.

## Selection by the fast check

scripts/mac_ops_fast_check.py now has LOADED_SCRIPTS (coordinator/bin/coordq and coordinator/bin/ticket). When either is among the changed files, every tests/ module whose source names that script as a quoted path part is selected, and the existing import closure adds the modules that import those. Trial with only coordinator/bin/coordq changed (a trailing newline, then restored), from the --plan output: tests/test_answer_format.py, test_coordq_action_key.py, test_coordq_capacity.py, test_coordq_message_dedupe.py, test_gate_fast_forward.py, test_gate_reviewer_quota.py, test_gatekeep_backstop_reviewer.py, test_gatekeep_retry_limit.py, test_lane_duplicate_suppression.py, test_prompt_paths.py, test_reviewer_vendor_split.py, test_tick_external_call_bounds.py, test_ticket_gate_live.py, test_ticket_text_blockers.py (and the changed test files). A ticket-only trial also selects test_close_check.py and test_ticket_section_headings.py.

## Finding outside the 16

tests.test_install_coordinator test_the_repository_board_config_carries_no_merge_policy fails on main: PR #656 added merge manual for digitized/Concerning to coordinator/config/tickets.json, and PR #474 had the test assert no repo carries a merge key. It does not load coordq or ticket and is not selected by this change, so it is left alone and reported.
