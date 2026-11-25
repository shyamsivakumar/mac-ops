# MO-985 runs

## Proof command

```text
PYTHONDONTWRITEBYTECODE=1 HOME=/nonexistent python3 -c "<ticket proof>"
```

### origin/main (5574760f)

```text
AssertionError: body line accepted
exit 1
```

### branch head

```text
exit 0
```

## Selftest case publisher_status_outcomes

```text
origin/main code, new case:
AssertionError: expected ['skip'], got ['candidate']
exit 1
branch:
publisher_status_outcomes ok
exit 0
```

## Outcome table (Refs #10 in body, newest status, PASS gate verdict)

FIX stands for a repo that is not on macPublisher; it counts as a publisher once the head has an agent-check status, the same rule coordq uses.

| repo | status | body line | gate_candidates | act_on_pr | builder messages |
|---|---|---|---|---|---|
| SRW | success | present | candidate | merge | 0 |
| SRW | success | absent | candidate | merge | 0 |
| SRW | failure | present | skip | no merge | 1 |
| SRW | failure | absent | skip | no merge | 1 |
| SRW | error | present | skip | no merge | 0 |
| SRW | error | absent | skip | no merge | 0 |
| SRW | pending | present | skip | no merge | 0 |
| SRW | pending | absent | skip | no merge | 0 |
| SRW | missing | present | skip | no merge | 0 |
| SRW | missing | absent | skip | no merge | 0 |
| FIX | success | present | candidate | merge | 0 |
| FIX | success | absent | candidate | merge | 0 |
| FIX | failure | present | none | no merge | 1 |
| FIX | failure | absent | none | no merge | 1 |
| FIX | error | present | none | no merge | 0 |
| FIX | error | absent | none | no merge | 0 |
| FIX | pending | present | none | no merge | 0 |
| FIX | pending | absent | none | no merge | 0 |
| FIX | missing | present | candidate | merge | 0 |
| FIX | missing | absent | none | no merge | 1 |

A SRW pull request with no ticket link gates after success and skips for every other status, with or without the body line (same run with the body set to the empty string).

## Real rollup shape (SRW#2578, head 259443a1, read with `gh pr view --json statusCheckRollup`)

The rollup has one StatusContext per context, with `context`, `state`, `startedAt` and no `completedAt`. GitHub keeps only the newest status of a context there, while the REST list the gate reads holds every status, newest first:

```text
REST statuses (checks[0] is the newest):
2026-11-25T18:56:06Z  srw/agent-check  success
2026-11-25T18:54:17Z  srw/agent-check  pending
rollup entry:
{"__typename": "StatusContext", "context": "srw/agent-check", "startedAt": "2026-11-25T18:56:06Z", "state": "SUCCESS"}
```

SRW#2577, #2576, #2575 and #2572 show the same pair: two REST statuses (success newer than pending), one rollup entry with the newest. If a rollup ever held two entries of one context, `publisher_status` takes the larger `startedAt` (or `completedAt` for a check run).

## Unread checks on the board

`checks[(repo, number)][1]` is the reason the checks could not be read. The board then strips the body line and empties the rollup, and passes `repo=None` to `pr_action`, so an unread SRW pull request keeps the old outcome (`check-missing`, action `check`) instead of waiting. The selftest case asserts both: `repo=None` gives `("check-missing", "check")`, a known-missing SRW status gives `("check-missing", "none")`.
