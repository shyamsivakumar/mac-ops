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
