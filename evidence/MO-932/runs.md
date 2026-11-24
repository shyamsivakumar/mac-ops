# MO-932 runs (review round at 40c0bc033c465e1bd24d0980aad6085cd4b9bcb8)

## Ticket proof command
Red on origin/main: ModuleNotFoundError: No module named 'inbox_replay' (exit 1).
Green on the head: exit 0.

## inbox eval (replay_cases) with the review cases
Red, previous inbox_replay.py (ec4370f2) with the new selftest, exit 1:
```
TypeError: '<' not supported between instances of 'str' and 'float'   (row {"ts":"x","event":"merged"} aborts replay)
```
Green on 40c0bc033c465e1bd24d0980aad6085cd4b9bcb8, exit 0:
```
inbox eval ok
```
