# MO-1186 (#809) runs

## Which call the unpatched tests hit

`coordq.call("t3_thread_list", {"allProjects": True, "limit": 100, "statuses": LIVE_STATUSES, "includeSubagents": False})`,
reached through `cmd_start` -> `drain()` -> `active_thread_ids()` (coordq line 416).
`subprocess.run([T3MCP, "call", tool, "-"])` then raises `FileNotFoundError: 't3mcp'` on the M1.
The queue items in `tests.test_coordq_action_key` are `t3_thread_send`, but `drain` lists active threads first, so the list call is the one that fails.

## Proof command

`PATH=/usr/bin:/bin python3 -m unittest tests.test_coordq_action_key` (temp COORDQ_DIR and COORD_JOURNAL_DIR)

Before (origin/main 0d8dc6e5):

    Ran 13 tests in 0.072s
    FAILED (errors=9)      FileNotFoundError: [Errno 2] No such file or directory: 't3mcp'

After (branch):

    Ran 13 tests in 1.138s
    OK

## M1 run (Host: Shyams-MacBook-Pro.local), `remote_fast_check.sh --remote mo809-fake-t3mcp 310304694e7b030ea869dbac320542234d5ffdad`

No t3mcp error remains. The isolation row is red on 4 tests with other causes, not fixed here:

- tests.test_retrospective.TestRetrospectiveHash.test_same_head_different_rounds_share_hash (ERROR)
- tests.test_retrospective.TestRetrospectiveHash.test_srw61_round1_base_from_checks (ERROR)
- tests.test_scorecard_policy.TestScorecardReviewPolicy.test_legacy_policy_reaches_replay (ERROR): FileNotFoundError '/Users/shyamsivakumar/.herdr-projects/data/tasks/llmwiki/10/task.json'
- tests.test_heavy_host_headroom.HostHeadroomTests.test_a_deeply_nested_file_keeps_the_default_floor (FAIL): RecursionError not raised

The other fast-check rows on the M1 passed.
