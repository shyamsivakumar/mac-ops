# MO-923 runs

## Ticket proof command

Run on origin/main (820e81b8) and on the branch. The command is the one in the ticket body, with the loader path set to the file under test.

On origin/main:

    AttributeError: module 'ov' has no attribute 'read_blocker_states'

On the branch: exit 0.

## Selftest case (board-integrity, extended)

Fails on origin/main with `AttributeError: module 'overnight_runner' has no attribute 'read_blocker_states'`; passes on the branch. The case covers a full answer, a partial answer (gh exits nonzero, `RepoError.stdout` holds the good rows, the unresolved number stays unmet), an unreadable answer (reason names the repository), and `blockers_for` giving "still open" / "could not be read".

## Live read-only board, 2026-11-23

Command: `overnight board --json --root <scratch>` with `COORDINATOR_GH_USAGE_LOG` set to a scratch file. Before is the installed overnight; after is this worktree. The Mac was not otherwise touched.

| | before | after |
|---|---|---|
| SRW stage:todo tickets | 116 | 116 |
| SRW blocked | 106 | 81 |
| SRW free | 10 | 35 |
| SRW "could not be read" entries | 39 (28 tickets) | 1 (1 ticket, #1319 names #1309, which GitHub does not resolve as an issue) |
| closed-list warning | "cut off at 500" | none |
| sams-llm-wiki blocked | 2 | 2 |
| gh calls (usage log rows) | 63 | 57 |
| of which closed-list reads | 20 graphql `issue list` rows before, 12 after (8 fewer) | 2 BlockerStates graphql rows added |

25 SRW tickets became free. Three of them, with the real state of each blocker:

- SRW #1336 named SRW-1225: closed issue #1335 (found by the exact title-key search).
- SRW #1566 named #1564 and #1565: both CLOSED.
- SRW #1582 named #1580 and #1581: both CLOSED.

The 81 tickets still blocked name a blocker that is open ("is still open" 86 times).

GitHub answers a missing or pull-request number with a partial GraphQL answer and a nonzero gh exit (checked live with #1216 closed, #1217 and #1218 unresolved). The good row #1216 survives in the new read.
