# MO-633 oracle and nop results

Harbor 0.26.0, each run through `heavy`, no model agent. Oracle applies the merged diff; nop changes nothing (the parent commit plus the PR's test files). Round 2 regenerated every task folder (Interface section, cleaned instructions, groups) and re-ran oracle and nop on every kept task.

| Task | Type | Group | Held out | Oracle reward | Nop reward |
| --- | --- | --- | --- | --- | --- |
| mac-ops-619 | bugfix | test_prompt_paths | no | 1 | 0 |
| mac-ops-618 | bugfix | test_prompt_paths | no | 1 | 0 |
| mac-ops-608 | feature | mac-ops-608 | no | 1 | 0 |
| mac-ops-486 | bugfix | mac-ops-486 | yes | 1 | 0 |
| mac-ops-340 | bugfix | mac-ops-340 | no | 1 | 0 |
| mac-ops-315 | bugfix | test_ticket_text_blockers | no | 1 | 0 |
| mac-ops-312 | bugfix | mac-ops-312 | no | 1 | 0 |
| mac-ops-273 | bugfix | mac-ops-273 | no | 1 | 0 |
| mac-ops-223 | feature | test_ticket_text_blockers | no | 1 | 0 |
| srw-1324 | feature | srw-1324 | no | 1 | 0 |

Tasks that share a test file carry one `group` (mac-ops-619 and mac-ops-618 share test_prompt_paths; mac-ops-315 and mac-ops-223 share test_ticket_text_blockers), so the scorer can treat them as one cluster. The held-out flag is `sha256(group) % 4 == 0`, so a cluster is held out or not as a whole; only mac-ops-486 is held out.

## Dropped in round 1 (oracle reward 0, tests need the Mac)

- mac-ops-547, 457, 308: the tests call `t3mcp`.
- mac-ops-509: the test expects a RecursionError at the Mac's recursion depth.
- mac-ops-474: the install smoke check runs `/opt/homebrew/bin/python3`.
- mac-ops-471: the test needs an authenticated `gh`.

## Dropped in round 2 (design review)

- mac-ops-231: its ticket (#207) is a pull request, not an issue; the real ticket (#163) belongs to another task.
- srw-142: its ticket is the PR itself (a closing note), and the test regex-matches the literal source of the fix.
- srw-1309: the ticket points at a branch and evidence files that are not in the snapshot, and the facade method the test calls cannot be derived from the ticket.
- srw-727: the test asserts the `x-bot2-secret` header and the fetch option names, which only the approval step named; that step tells the agent to copy `BOT2_WEBHOOK_SECRET` between production Railway services, so the step is removed and the task cannot be graded.
- mac-ops-597: a re-cut ticket that carries earlier review rounds and refers to PR #585.
- mac-ops-542: the test asserts the exact wording of the answer-format sentence, which the ticket does not give.
- mac-ops-569: the tests assert exact rule sentences (the question rule for Shyam) in config files, which the ticket does not give.
- mac-ops-510: one test asserts the literal source `run(selftest, timeout=60)` in `scripts/mac_ops_fast_check.py`.

## How instructions are cleaned

`build_tasks.py` drops the Gate, Finish, CI, Rollback, Approval, Data/secrets, Addition, Left for later, Closing and similar sections, drops sentences that say "no new unit tests", "stop and report" or ask for pasted output or a PR body line, and refuses a ticket that is a pull request, that was updated after the merge and states the fix, or that names a production secret step. The Interface section lists the names and signatures the tests use that the parent commit lacks or has with a different signature (names and signatures only).

herdr-projects and sams-llm-wiki are not covered: herdr-projects is a Rust build with Linear tickets, and sams-llm-wiki was not triaged.
