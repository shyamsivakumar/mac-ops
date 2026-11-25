# MO-968 runs

Proof command: `uvx -q ruff@0.14.0 check --select F,B --output-format concise evidence/event-inbox-design`

## Red on origin/main (a6205808)

```
evidence/event-inbox-design/alarm_breakdown.py:13:6: F821 Undefined name `facts`
evidence/event-inbox-design/alarm_breakdown.py:15:10: F821 Undefined name `rows`
evidence/event-inbox-design/alarm_breakdown.py:33:47: F821 Undefined name `URGENT`
evidence/event-inbox-design/empty_ticks.py:8:10: B034 `re.split` should pass `maxsplit` and `flags` as keyword arguments to avoid confusion due to unintuitive argument positions
evidence/event-inbox-design/empty_ticks.py:12:7: B007 Loop control variable `t` not used within loop body
evidence/event-inbox-design/empty_ticks.py:12:9: B007 Loop control variable `tz` not used within loop body
evidence/event-inbox-design/empty_ticks.py:12:14: B007 Loop control variable `h` not used within loop body
evidence/event-inbox-design/latency.py:1:56: F401 [*] `statistics` imported but unused
evidence/event-inbox-design/replay_wakes.py:11:8: F401 [*] `statistics` imported but unused
evidence/event-inbox-design/replay_wakes.py:59:11: F841 Local variable `i` is assigned to but never used
evidence/event-inbox-design/replay_wakes.py:59:14: F841 Local variable `last` is assigned to but never used
evidence/event-inbox-design/replay_wakes.py:61:5: F841 Local variable `now` is assigned to but never used
evidence/event-inbox-design/replay_wakes.py:63:9: F841 Local variable `pending` is assigned to but never used
evidence/event-inbox-design/t0_replay.py:18:6: F821 Undefined name `facts`
evidence/event-inbox-design/t0_replay.py:52:73: F821 Undefined name `URGENT`
evidence/event-inbox-design/t0_replay.py:53:58: F821 Undefined name `ALL5`
Found 16 errors.
[*] 2 fixable with the `--fix` option (5 hidden fixes can be enabled with the `--unsafe-fixes` option).
exit 1
```

## Green on c8d1dd46

```
All checks passed!
exit 0
```

## Outputs before and after

Both versions ran on the same copy of the journal and ticks.log (SHA-1 prefix of stdout).

| script | a6205808 | c8d1dd46 |
|---|---|---|
| alarm_breakdown.py | cb32239594 | cb32239594 |
| empty_ticks.py | 3f1ea88817 | 3f1ea88817 |
| replay_wakes.py | df8d857592 | df8d857592 |
| t0_replay.py | 9348aff083 | 9348aff083 |

`latency.py` calls live `gh` and was not run.
