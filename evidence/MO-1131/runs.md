# MO-1131 runs

Proof command (ticket body): a fake t3mcp (`COORDQ_T3MCP`) logs each tool it is called with.
`coordq.call("t3_thread_send", ...)` runs once with the thread settled and once not settled.

## origin/main (red)

```text
AssertionError: (['t3_thread_send'], ['t3_thread_send'])
```

## Branch (green)

Exit code 0. The settled thread logs `t3_thread_read`, `t3_thread_organize`, `t3_thread_send`;
the unsettled thread logs `t3_thread_read`, `t3_thread_send`.

## Failure paths (branch, `t3_call` faked)

```text
unsettle fails: (0, '{}') ['t3_thread_read', 't3_thread_organize', 't3_thread_send']
read fails: (0, '{}') ['t3_thread_read', 't3_thread_send']
send with no thread id: (0, '{}') ['t3_thread_send']
```

A failed unsettle or read is logged and the send still goes out. The 70 coordq and lane
unittest cases (`test_coordq_action_key`, `test_coordq_capacity`, `test_coordq_message_dedupe`,
`test_lane_duplicate_suppression`) and every selftest case pass.
